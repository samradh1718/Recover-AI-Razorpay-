from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_database_session
from app.models.razorpay_test_order import (
    RazorpayTestOrder,
)
from app.schemas.razorpay_test_checkout import (
    CreateRazorpayTestCheckoutRequest,
    RazorpayTestCheckoutResponse,
    RazorpayTestOrderRecordResponse,
)
from app.services.razorpay_test_failure_ingestion_service import (
    create_reconciled_failed_payment_event,
)
from app.services.razorpay_test_order_service import (
    RazorpayTestOrderConfigurationError,
    RazorpayTestOrderProviderError,
    RazorpayTestOrderValidationError,
    create_razorpay_test_order,
    reconcile_razorpay_test_order,
)
from app.workers.tasks import (
    process_payment_event_task,
)


router = APIRouter(
    prefix="/test-checkout",
    tags=["Razorpay Test Checkout"],
)

PAISE_PER_RUPEE = Decimal("100")
WHOLE_PAISE = Decimal("1")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_demo_tenant(
    tenant_id: UUID,
) -> None:
    configured_tenant_id = (
        settings.demo_tenant_id
    )

    if (
        configured_tenant_id is not None
        and tenant_id != configured_tenant_id
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail=(
                "Test Checkout is restricted "
                "to the configured demo tenant"
            ),
        )


def _raise_provider_http_error(
    error: Exception,
) -> None:
    if isinstance(
        error,
        RazorpayTestOrderValidationError,
    ):
        raise HTTPException(
            status_code=(
                status
                .HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(error),
        ) from error

    if isinstance(
        error,
        RazorpayTestOrderConfigurationError,
    ):
        raise HTTPException(
            status_code=(
                status
                .HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=str(error),
        ) from error

    if isinstance(
        error,
        RazorpayTestOrderProviderError,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=str(error),
        ) from error

    raise error


def _amount_rupees_to_paise(
    amount_rupees: Decimal,
) -> int:
    amount_paise = (
        Decimal(str(amount_rupees))
        * PAISE_PER_RUPEE
    ).quantize(
        WHOLE_PAISE,
        rounding=ROUND_HALF_UP,
    )

    return int(amount_paise)


@router.post(
    "/orders",
    response_model=(
        RazorpayTestCheckoutResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
)
def create_test_checkout_order(
    request: (
        CreateRazorpayTestCheckoutRequest
    ),
    database: Session = Depends(
        get_database_session
    ),
) -> RazorpayTestCheckoutResponse:
    """Create and persist one provider Test Order."""

    _validate_demo_tenant(
        request.tenant_id
    )

    try:
        provider_result = (
            create_razorpay_test_order(
                tenant_id=(
                    request.tenant_id
                ),
                amount_rupees=(
                    request.amount_rupees
                ),
                currency=request.currency,
                customer_reference=(
                    request
                    .customer_reference
                ),
            )
        )
    except (
        RazorpayTestOrderValidationError,
        RazorpayTestOrderConfigurationError,
        RazorpayTestOrderProviderError,
    ) as error:
        _raise_provider_http_error(
            error
        )

        raise

    order = RazorpayTestOrder(
        tenant_id=request.tenant_id,
        provider="razorpay",
        provider_order_id=str(
            provider_result[
                "provider_order_id"
            ]
        ),
        receipt=str(
            provider_result["receipt"]
        ),
        amount_rupees=Decimal(
            str(
                provider_result[
                    "amount_rupees"
                ]
            )
        ),
        currency=str(
            provider_result["currency"]
        ),
        provider_order_status=str(
            provider_result[
                "provider_order_status"
            ]
        ),
        data_source=(
            "razorpay_test_checkout"
        ),
        provider_generated=True,
        real_money=False,
        customer_reference=(
            request.customer_reference
        ),
        outcome_status="pending",
        provider_response=dict(
            provider_result[
                "provider_response"
            ]
        ),
    )

    try:
        database.add(order)
        database.commit()
        database.refresh(order)
    except SQLAlchemyError as error:
        database.rollback()

        raise HTTPException(
            status_code=(
                status
                .HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "The provider created the Test "
                "Order, but RecoverAI could not "
                "persist its local record"
            ),
        ) from error

    return RazorpayTestCheckoutResponse(
        checkout_session_id=order.id,
        provider_order_id=(
            order.provider_order_id
        ),
        provider_order_status=(
            order.provider_order_status
        ),
        razorpay_key_id=str(
            provider_result[
                "razorpay_key_id"
            ]
        ),
        amount_rupees=str(
            order.amount_rupees
        ),
        amount_paise=int(
            provider_result[
                "amount_paise"
            ]
        ),
        currency="INR",
        receipt=order.receipt,
        data_source=(
            "razorpay_test_checkout"
        ),
        provider_generated=True,
        real_money=False,
        created_at=order.created_at,
    )


@router.get(
    "/orders",
    response_model=list[
        RazorpayTestOrderRecordResponse
    ],
)
def list_test_checkout_orders(
    tenant_id: UUID = Query(...),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=200,
    ),
    database: Session = Depends(
        get_database_session
    ),
) -> list[
    RazorpayTestOrderRecordResponse
]:
    """List Test Checkout telemetry for one tenant."""

    _validate_demo_tenant(
        tenant_id
    )

    orders = database.scalars(
        select(
            RazorpayTestOrder
        )
        .where(
            RazorpayTestOrder
            .tenant_id
            == tenant_id
        )
        .order_by(
            RazorpayTestOrder
            .created_at
            .desc()
        )
        .offset(offset)
        .limit(limit)
    ).all()

    return [
        RazorpayTestOrderRecordResponse
        .model_validate(order)
        for order in orders
    ]


@router.post(
    (
        "/orders/{provider_order_id}"
        "/reconcile"
    ),
    response_model=(
        RazorpayTestOrderRecordResponse
    ),
)
def reconcile_test_checkout_order(
    provider_order_id: str,
    tenant_id: UUID = Query(...),
    database: Session = Depends(
        get_database_session
    ),
) -> RazorpayTestOrderRecordResponse:
    """Synchronise one Test Order with Razorpay.

    Signed webhooks remain the preferred production
    evidence. This provider lookup supports localhost
    demos where Razorpay cannot reach a private URL.

    A provider-confirmed failed attempt is converted
    into an idempotent PaymentEvent and submitted to
    the existing RecoverAI Celery recovery pipeline.
    """

    _validate_demo_tenant(
        tenant_id
    )

    order = database.scalar(
        select(
            RazorpayTestOrder
        )
        .where(
            RazorpayTestOrder
            .tenant_id
            == tenant_id,
            RazorpayTestOrder
            .provider
            == "razorpay",
            RazorpayTestOrder
            .provider_order_id
            == provider_order_id,
        )
    )

    if order is None:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "RecoverAI Test Order "
                "was not found"
            ),
        )

    try:
        provider_result = (
            reconcile_razorpay_test_order(
                tenant_id=tenant_id,
                provider_order_id=(
                    provider_order_id
                ),
            )
        )
    except (
        RazorpayTestOrderValidationError,
        RazorpayTestOrderConfigurationError,
        RazorpayTestOrderProviderError,
    ) as error:
        _raise_provider_http_error(
            error
        )

        raise

    provider_amount_paise = int(
        provider_result[
            "amount_paise"
        ]
    )

    expected_amount_paise = (
        _amount_rupees_to_paise(
            order.amount_rupees
        )
    )

    if (
        provider_amount_paise
        != expected_amount_paise
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "Provider order amount does "
                "not match the RecoverAI record"
            ),
        )

    provider_currency = str(
        provider_result["currency"]
    ).upper()

    if (
        provider_currency
        != order.currency.upper()
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "Provider order currency does "
                "not match the RecoverAI record"
            ),
        )

    outcome_status = str(
        provider_result[
            "outcome_status"
        ]
    ).lower()

    order.provider_order_status = (
        str(
            provider_result[
                "provider_order_status"
            ]
        )
    )

    provider_payment_id = (
        provider_result.get(
            "provider_payment_id"
        )
    )

    if isinstance(
        provider_payment_id,
        str,
    ):
        order.provider_payment_id = (
            provider_payment_id
        )

    order.outcome_status = (
        outcome_status
    )

    order.provider_response = dict(
        provider_result[
            "provider_response"
        ]
    )

    now = utc_now()

    order.updated_at = now

    if outcome_status == "paid":
        order.completed_at = now

    failure_event_id: UUID | None = None
    should_queue_failure = False

    if outcome_status == "failed":
        try:
            (
                failure_event,
                failure_event_created,
            ) = (
                create_reconciled_failed_payment_event(
                    database=database,
                    test_order=order,
                    provider_result=(
                        provider_result
                    ),
                )
            )
        except ValueError as error:
            database.rollback()

            raise HTTPException(
                status_code=(
                    status.HTTP_502_BAD_GATEWAY
                ),
                detail=(
                    "Razorpay reported a failed "
                    "attempt, but its evidence "
                    "could not be safely ingested: "
                    f"{error}"
                ),
            ) from error

        failure_event_id = (
            failure_event.id
        )

        should_queue_failure = (
            failure_event_created
            or failure_event
            .processing_status
            not in {
                "processed",
                "ignored",
                "processing",
            }
        )

        provider_snapshot = dict(
            order.provider_response
            or {}
        )

        provider_snapshot[
            "recoverai_failure_ingestion"
        ] = {
            "payment_event_id": str(
                failure_event.id
            ),
            "event_type": (
                "payment.failed"
            ),
            "event_source": (
                "razorpay_server_api"
            ),
            "signed_webhook": False,
            "idempotent": True,
        }

        order.provider_response = (
            provider_snapshot
        )

    try:
        database.commit()
        database.refresh(order)
    except SQLAlchemyError as error:
        database.rollback()

        raise HTTPException(
            status_code=(
                status
                .HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Razorpay returned the Test "
                "Order evidence, but RecoverAI "
                "could not persist it"
            ),
        ) from error

    if (
        failure_event_id is not None
        and should_queue_failure
    ):
        try:
            process_payment_event_task.apply_async(
                args=[
                    str(failure_event_id)
                ],
            )
        except Exception as error:
            # The event is already persisted as received.
            # Calling reconciliation again will safely
            # attempt to enqueue the same event.
            raise HTTPException(
                status_code=(
                    status
                    .HTTP_503_SERVICE_UNAVAILABLE
                ),
                detail=(
                    "The failed provider event "
                    "was persisted, but the "
                    "recovery worker could not "
                    "be queued"
                ),
            ) from error

    return (
        RazorpayTestOrderRecordResponse
        .model_validate(order)
    )