import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment_event import (
    PaymentEvent,
)
from app.models.razorpay_test_order import (
    RazorpayTestOrder,
)


RECONCILIATION_DATA_SOURCE = (
    "razorpay_server_api"
)


def _payment_items(
    provider_result: dict[str, Any],
) -> list[dict[str, Any]]:
    provider_response = (
        provider_result.get(
            "provider_response"
        )
    )

    if not isinstance(
        provider_response,
        dict,
    ):
        raise ValueError(
            "Provider reconciliation evidence "
            "is missing"
        )

    raw_payments = provider_response.get(
        "payments"
    )

    if not isinstance(raw_payments, list):
        raise ValueError(
            "Provider payment evidence "
            "is missing"
        )

    return [
        payment
        for payment in raw_payments
        if isinstance(payment, dict)
    ]


def _find_failed_payment(
    *,
    provider_result: dict[str, Any],
    provider_payment_id: str,
    provider_order_id: str,
) -> dict[str, Any]:
    for payment in _payment_items(
        provider_result
    ):
        if (
            payment.get("id")
            == provider_payment_id
            and payment.get("order_id")
            == provider_order_id
            and str(
                payment.get("status")
                or ""
            ).lower()
            == "failed"
        ):
            return payment

    raise ValueError(
        "Confirmed failed payment evidence "
        "was not found"
    )


def _provider_event_id(
    provider_payment_id: str,
) -> str:
    return (
        "server-reconcile:"
        "payment.failed:"
        f"{provider_payment_id}"
    )


def _event_payload(
    *,
    test_order: RazorpayTestOrder,
    failed_payment: dict[str, Any],
) -> dict[str, Any]:
    provider_payment_id = str(
        failed_payment["id"]
    )

    amount_paise = failed_payment.get(
        "amount"
    )

    if not isinstance(amount_paise, int):
        raise ValueError(
            "Failed payment amount is missing"
        )

    currency = str(
        failed_payment.get("currency")
        or test_order.currency
    ).upper()

    created_at = failed_payment.get(
        "created_at"
    )

    if not isinstance(created_at, int):
        created_at = None

    payment_entity: dict[str, Any] = {
        "id": provider_payment_id,
        "entity": "payment",
        "order_id": (
            test_order.provider_order_id
        ),
        "amount": amount_paise,
        "currency": currency,
        "status": "failed",
        "method": failed_payment.get(
            "method"
        ),
        "customer_id": None,
        "error_code": failed_payment.get(
            "error_code"
        ),
        "error_description": (
            failed_payment.get(
                "error_description"
            )
        ),
        "error_source": failed_payment.get(
            "error_source"
        ),
        "error_step": failed_payment.get(
            "error_step"
        ),
        "error_reason": failed_payment.get(
            "error_reason"
        ),
        "notes": {
            "recoverai_data_source": (
                RECONCILIATION_DATA_SOURCE
            ),
            "recoverai_provider_generated": (
                "true"
            ),
            "recoverai_real_money": "false",
            "recoverai_provider_order_id": (
                test_order.provider_order_id
            ),
            "recoverai_test_order_id": str(
                test_order.id
            ),
        },
    }

    payload: dict[str, Any] = {
        "entity": "event",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": payment_entity,
            }
        },
    }

    if created_at is not None:
        payload["created_at"] = (
            created_at
        )

    return payload


def _payload_sha256(
    payload: dict[str, Any],
) -> str:
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(
        canonical_payload
    ).hexdigest()


def create_reconciled_failed_payment_event(
    *,
    database: Session,
    test_order: RazorpayTestOrder,
    provider_result: dict[str, Any],
) -> tuple[PaymentEvent, bool]:
    """Persist one idempotent provider-confirmed failed event.

    The event is generated from Razorpay's authenticated
    server API response. It is not represented as a signed
    webhook.
    """

    outcome_status = str(
        provider_result.get(
            "outcome_status"
        )
        or ""
    ).lower()

    if outcome_status != "failed":
        raise ValueError(
            "Only a confirmed failed payment "
            "can enter failure ingestion"
        )

    provider_payment_id = (
        provider_result.get(
            "provider_payment_id"
        )
    )

    if not isinstance(
        provider_payment_id,
        str,
    ):
        raise ValueError(
            "Confirmed failed payment ID "
            "is missing"
        )

    failed_payment = _find_failed_payment(
        provider_result=provider_result,
        provider_payment_id=(
            provider_payment_id
        ),
        provider_order_id=(
            test_order.provider_order_id
        ),
    )

    provider_event_id = (
        _provider_event_id(
            provider_payment_id
        )
    )

    existing_event = database.scalar(
        select(PaymentEvent).where(
            PaymentEvent.provider
            == "razorpay",
            PaymentEvent.provider_event_id
            == provider_event_id,
        )
    )

    if existing_event is not None:
        test_order.provider_payment_id = (
            provider_payment_id
        )

        test_order.latest_payment_event_id = (
            existing_event.id
        )

        return existing_event, False

    payload = _event_payload(
        test_order=test_order,
        failed_payment=failed_payment,
    )

    payment_event = PaymentEvent(
        tenant_id=test_order.tenant_id,
        provider="razorpay",
        provider_event_id=(
            provider_event_id
        ),
        event_type="payment.failed",
        provider_payment_id=(
            provider_payment_id
        ),
        payload_sha256=(
            _payload_sha256(payload)
        ),
        payload=payload,
        processing_status="received",
        processing_error=None,
    )

    database.add(payment_event)
    database.flush()

    test_order.provider_payment_id = (
        provider_payment_id
    )

    test_order.latest_payment_event_id = (
        payment_event.id
    )

    return payment_event, True