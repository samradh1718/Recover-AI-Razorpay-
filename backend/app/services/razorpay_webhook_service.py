import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.payment_event import PaymentEvent


class InvalidWebhookSignatureError(ValueError):
    pass


class InvalidWebhookPayloadError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def verify_razorpay_webhook_signature(
    raw_body: bytes,
    received_signature: str,
    webhook_secret: str,
) -> None:
    if not webhook_secret:
        raise RuntimeError(
            "RAZORPAY_WEBHOOK_SECRET is not configured"
        )

    expected_signature = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        expected_signature,
        received_signature,
    ):
        raise InvalidWebhookSignatureError(
            "Invalid Razorpay webhook signature"
        )


def decode_webhook_payload(
    raw_body: bytes,
) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidWebhookPayloadError(
            "Webhook body is not valid JSON"
        ) from error

    if not isinstance(payload, dict):
        raise InvalidWebhookPayloadError(
            "Webhook payload must be a JSON object"
        )

    event_type = payload.get("event")

    if not isinstance(event_type, str) or not event_type:
        raise InvalidWebhookPayloadError(
            "Webhook payload does not contain an event type"
        )

    return payload


def extract_payment_id(
    payload: dict[str, Any],
) -> str | None:
    payment_wrapper = (
        payload.get("payload", {}).get("payment", {})
    )

    payment_entity = payment_wrapper.get("entity", {})

    payment_id = payment_entity.get("id")

    if isinstance(payment_id, str):
        return payment_id

    return None


def store_razorpay_event(
    database: Session,
    tenant_id: UUID,
    provider_event_id: str,
    raw_body: bytes,
    payload: dict[str, Any],
) -> tuple[UUID, bool]:
    event_id = uuid4()

    payload_sha256 = hashlib.sha256(raw_body).hexdigest()
    event_type = str(payload["event"])
    payment_id = extract_payment_id(payload)

    statement = (
        insert(PaymentEvent)
        .values(
            id=event_id,
            tenant_id=tenant_id,
            provider="razorpay",
            provider_event_id=provider_event_id,
            event_type=event_type,
            provider_payment_id=payment_id,
            payload_sha256=payload_sha256,
            payload=payload,
            processing_status="received",
            received_at=utc_now(),
        )
        .on_conflict_do_nothing(
            constraint="uq_payment_events_provider_event_id"
        )
        .returning(PaymentEvent.id)
    )

    inserted_event_id = database.execute(
        statement
    ).scalar_one_or_none()

    database.commit()

    if inserted_event_id is not None:
        return inserted_event_id, False

    existing_event_id = database.execute(
        select(PaymentEvent.id).where(
            PaymentEvent.provider == "razorpay",
            PaymentEvent.provider_event_id
            == provider_event_id,
        )
    ).scalar_one()

    return existing_event_id, True