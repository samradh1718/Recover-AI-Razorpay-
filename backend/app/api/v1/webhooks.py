import logging
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_database_session
from app.services.razorpay_webhook_service import (
    InvalidWebhookPayloadError,
    InvalidWebhookSignatureError,
    decode_webhook_payload,
    store_razorpay_event,
    verify_razorpay_webhook_signature,
)
from app.workers.tasks import process_payment_event_task


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"],
)


@router.post(
    "/razorpay/{tenant_id}",
    status_code=status.HTTP_200_OK,
)
async def receive_razorpay_webhook(
    tenant_id: UUID,
    request: Request,
    x_razorpay_signature: Annotated[
        str | None,
        Header(alias="X-Razorpay-Signature"),
    ] = None,
    x_razorpay_event_id: Annotated[
        str | None,
        Header(alias="X-Razorpay-Event-Id"),
    ] = None,
    database: Session = Depends(
        get_database_session
    ),
) -> dict[str, str | bool]:
    logger.warning(
        "Razorpay webhook received: "
        "signature_present=%s, "
        "event_id_present=%s",
        bool(x_razorpay_signature),
        bool(x_razorpay_event_id),
    )

    if not x_razorpay_signature:
        logger.warning(
            "Razorpay webhook rejected: "
            "X-Razorpay-Signature header is missing"
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "X-Razorpay-Signature header is required"
            ),
        )

    if not x_razorpay_event_id:
        logger.warning(
            "Razorpay webhook rejected: "
            "X-Razorpay-Event-Id header is missing"
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "X-Razorpay-Event-Id header is required"
            ),
        )

    raw_body = await request.body()

    try:
        verify_razorpay_webhook_signature(
            raw_body=raw_body,
            received_signature=x_razorpay_signature,
            webhook_secret=(
                settings.razorpay_webhook_secret
            ),
        )

        payload = decode_webhook_payload(
            raw_body
        )

    except InvalidWebhookSignatureError as error:
        logger.warning(
            "Razorpay webhook rejected: "
            "invalid webhook signature"
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    except InvalidWebhookPayloadError as error:
        logger.warning(
            "Razorpay webhook rejected: "
            "invalid payload: %s",
            error,
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    except RuntimeError as error:
        logger.exception(
            "Razorpay webhook validation failed "
            "because of a server configuration error"
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(error),
        ) from error

    try:
        event_id, duplicate = store_razorpay_event(
            database=database,
            tenant_id=tenant_id,
            provider_event_id=(
                x_razorpay_event_id
            ),
            raw_body=raw_body,
            payload=payload,
        )

    except SQLAlchemyError as error:
        database.rollback()

        logger.exception(
            "Unable to store Razorpay webhook event"
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Unable to store webhook event",
        ) from error

    queued = False

    if not duplicate:
        try:
            process_payment_event_task.delay(
                str(event_id)
            )
            queued = True

        except Exception:
            # The event is already stored in PostgreSQL.
            # It can safely be queued again later.
            logger.exception(
                "Razorpay webhook event was stored "
                "but could not be queued"
            )
            queued = False

    logger.info(
        "Razorpay webhook accepted: "
        "event_id=%s, event_type=%s, "
        "duplicate=%s, queued=%s",
        event_id,
        payload["event"],
        duplicate,
        queued,
    )

    return {
        "status": (
            "duplicate"
            if duplicate
            else "received"
        ),
        "event_id": str(event_id),
        "event_type": str(
            payload["event"]
        ),
        "duplicate": duplicate,
        "queued": queued,
    }