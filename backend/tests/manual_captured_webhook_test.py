import argparse
import hashlib
import hmac
import json
from time import time
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import RecoveryCase


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send a simulated captured-payment webhook "
            "for the latest unrecovered case."
        )
    )

    parser.add_argument(
        "--payment-id",
        help=(
            "Optional provider payment ID. The latest "
            "unrecovered case is used when omitted."
        ),
    )

    return parser.parse_args()


def find_target_case(
    payment_id: str | None,
) -> tuple[str, str, str, int]:
    with SessionLocal() as database:
        query = select(
            RecoveryCase.tenant_id,
            RecoveryCase.provider_payment_id,
            RecoveryCase.provider_customer_id,
            RecoveryCase.original_amount_minor,
        ).where(
            RecoveryCase.provider_payment_id.is_not(None),
            RecoveryCase.recovered_at.is_(None),
        )

        if payment_id is not None:
            query = query.where(
                RecoveryCase.provider_payment_id
                == payment_id
            )

        match = database.execute(
            query
            .order_by(
                RecoveryCase.created_at.desc()
            )
            .limit(1)
        ).one_or_none()

        database.rollback()

    if match is None:
        target = payment_id or "latest unrecovered case"

        raise RuntimeError(
            f"No recovery case was found for {target}"
        )

    tenant_id = str(match[0])
    provider_payment_id = str(match[1])

    customer_id = (
        str(match[2])
        if match[2] is not None
        else f"cust_test_{uuid4().hex[:12]}"
    )

    amount_minor = int(match[3])

    return (
        tenant_id,
        provider_payment_id,
        customer_id,
        amount_minor,
    )


def main() -> None:
    arguments = parse_arguments()

    if not settings.razorpay_webhook_secret:
        raise RuntimeError(
            "RAZORPAY_WEBHOOK_SECRET is not configured"
        )

    (
        tenant_id,
        payment_id,
        customer_id,
        amount_minor,
    ) = find_target_case(
        arguments.payment_id
    )

    timestamp = int(time())

    payload = {
        "entity": "event",
        "account_id": (
            f"acc_test_{uuid4().hex[:12]}"
        ),
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": amount_minor,
                    "currency": "INR",
                    "status": "captured",
                    "captured": True,
                    "customer_id": customer_id,
                    "error_code": None,
                    "error_description": None,
                    "error_source": None,
                    "error_step": None,
                    "error_reason": None,
                    "created_at": timestamp,
                }
            }
        },
        "created_at": timestamp,
    }

    raw_body = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    signature = hmac.new(
        key=(
            settings
            .razorpay_webhook_secret
            .encode("utf-8")
        ),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    provider_event_id = (
        f"evt_test_captured_{uuid4().hex}"
    )

    webhook_url = (
        settings.backend_api_base_url.rstrip("/")
        + "/webhooks/razorpay/"
        + tenant_id
    )

    print()
    print("Simulated captured-payment webhook")
    print("Tenant ID:", tenant_id)
    print("Payment ID:", payment_id)
    print("Customer ID:", customer_id)
    print(
        "Amount:",
        f"₹{amount_minor / 100:,.2f}",
    )
    print("Webhook URL:", webhook_url)
    print()

    response = httpx.post(
        webhook_url,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": (
                provider_event_id
            ),
        },
        timeout=15,
    )

    print("HTTP status:", response.status_code)
    print("Response:", response.json())

    response.raise_for_status()

    print()
    print(
        "This is a local processor simulation. "
        "Razorpay Payment Link reconciliation remains "
        "the provider-realistic recovery proof."
    )


if __name__ == "__main__":
    main()