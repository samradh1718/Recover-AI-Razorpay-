import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from uuid import uuid4

import httpx

from app.core.config import settings


TENANT_ID = "11111111-1111-1111-1111-111111111111"

WEBHOOK_URL = (
    "http://127.0.0.1:8000"
    f"/api/v1/webhooks/razorpay/{TENANT_ID}"
)


@dataclass
class PaymentScenario:
    name: str
    amount_paise: int
    error_code: str
    error_reason: str
    error_source: str
    should_recover: bool


SCENARIOS = [
    PaymentScenario(
        name="insufficient_funds",
        amount_paise=249900,
        error_code="BAD_REQUEST_ERROR",
        error_reason="insufficient_funds",
        error_source="customer",
        should_recover=True,
    ),
    PaymentScenario(
        name="expired_card",
        amount_paise=79900,
        error_code="BAD_REQUEST_ERROR",
        error_reason="expired_card",
        error_source="customer",
        should_recover=False,
    ),
    PaymentScenario(
        name="incorrect_otp",
        amount_paise=150000,
        error_code="BAD_REQUEST_ERROR",
        error_reason="incorrect_otp",
        error_source="bank",
        should_recover=True,
    ),
    PaymentScenario(
        name="gateway_timeout",
        amount_paise=500000,
        error_code="GATEWAY_ERROR",
        error_reason="gateway_timeout",
        error_source="gateway",
        should_recover=True,
    ),
    PaymentScenario(
        name="unknown_failure",
        amount_paise=129900,
        error_code="UNKNOWN_ERROR",
        error_reason="unexpected_failure",
        error_source="unknown",
        should_recover=False,
    ),
]


def send_webhook(
    client: httpx.Client,
    payload: dict,
) -> dict:
    raw_body = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    signature = hmac.new(
        key=settings.razorpay_webhook_secret.encode(
            "utf-8"
        ),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    provider_event_id = f"evt_batch_{uuid4()}"

    response = client.post(
        WEBHOOK_URL,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": provider_event_id,
        },
    )

    response.raise_for_status()

    return response.json()


def build_failed_payload(
    payment_id: str,
    scenario: PaymentScenario,
) -> dict:
    return {
        "entity": "event",
        "account_id": "acc_local_batch",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": scenario.amount_paise,
                    "currency": "INR",
                    "status": "failed",
                    "customer_id": (
                        f"cust_{scenario.name}"
                    ),
                    "error_code": scenario.error_code,
                    "error_description": (
                        f"Batch test: {scenario.name}"
                    ),
                    "error_source": (
                        scenario.error_source
                    ),
                    "error_step": (
                        "payment_authentication"
                    ),
                    "error_reason": (
                        scenario.error_reason
                    ),
                }
            }
        },
        "created_at": int(time.time()),
    }


def build_captured_payload(
    payment_id: str,
    scenario: PaymentScenario,
) -> dict:
    return {
        "entity": "event",
        "account_id": "acc_local_batch",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": scenario.amount_paise,
                    "currency": "INR",
                    "status": "captured",
                    "captured": True,
                    "customer_id": (
                        f"cust_{scenario.name}"
                    ),
                }
            }
        },
        "created_at": int(time.time()),
    }


def main() -> None:
    batch_id = uuid4().hex[:8]

    generated_payments: list[
        tuple[str, PaymentScenario]
    ] = []

    print(f"\nStarting recovery batch: {batch_id}\n")

    with httpx.Client(timeout=15) as client:
        for index, scenario in enumerate(
            SCENARIOS,
            start=1,
        ):
            payment_id = (
                f"pay_batch_{batch_id}_{index:02d}"
            )

            response = send_webhook(
                client=client,
                payload=build_failed_payload(
                    payment_id=payment_id,
                    scenario=scenario,
                ),
            )

            generated_payments.append(
                (payment_id, scenario)
            )

            print(
                f"FAILED  | {payment_id} "
                f"| {scenario.name} "
                f"| ₹{scenario.amount_paise / 100:.2f} "
                f"| queued={response.get('queued')}"
            )

        print(
            "\nWaiting for failed events "
            "to create recovery cases...\n"
        )

        time.sleep(5)

        for payment_id, scenario in generated_payments:
            if not scenario.should_recover:
                continue

            response = send_webhook(
                client=client,
                payload=build_captured_payload(
                    payment_id=payment_id,
                    scenario=scenario,
                ),
            )

            print(
                f"CAPTURED | {payment_id} "
                f"| expected recovery "
                f"| queued={response.get('queued')}"
            )

    print("\nBatch webhooks submitted successfully.")
    print(
        "Wait for both Celery workers to finish processing."
    )
    print(
        "The AI shadow worker may take "
        "approximately two minutes.\n"
    )


if __name__ == "__main__":
    main()