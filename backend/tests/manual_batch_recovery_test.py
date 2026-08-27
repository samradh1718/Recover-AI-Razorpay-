import argparse
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from uuid import uuid4

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class PaymentScenario:
    name: str
    amount_minor: int
    error_code: str
    error_reason: str
    error_source: str
    error_step: str
    should_recover: bool


SCENARIOS = [
    PaymentScenario(
        name="insufficient_funds",
        amount_minor=249900,
        error_code="BAD_REQUEST_ERROR",
        error_reason="insufficient_funds",
        error_source="customer",
        error_step="payment_authorization",
        should_recover=True,
    ),
    PaymentScenario(
        name="expired_card",
        amount_minor=79900,
        error_code="BAD_REQUEST_ERROR",
        error_reason="expired_card",
        error_source="customer",
        error_step="payment_authorization",
        should_recover=False,
    ),
    PaymentScenario(
        name="incorrect_otp",
        amount_minor=150000,
        error_code="BAD_REQUEST_ERROR",
        error_reason="incorrect_otp",
        error_source="bank",
        error_step="payment_authentication",
        should_recover=True,
    ),
    PaymentScenario(
        name="gateway_timeout",
        amount_minor=500000,
        error_code="GATEWAY_ERROR",
        error_reason="gateway_timeout",
        error_source="gateway",
        error_step="payment_processing",
        should_recover=True,
    ),
    PaymentScenario(
        name="unknown_failure",
        amount_minor=129900,
        error_code="UNKNOWN_ERROR",
        error_reason="unexpected_failure",
        error_source="unknown",
        error_step="payment_processing",
        should_recover=False,
    ),
]


@dataclass(frozen=True)
class GeneratedPayment:
    payment_id: str
    customer_id: str
    scenario: PaymentScenario


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a dynamic batch of failed-payment "
            "webhooks for RecoverAI."
        )
    )

    parser.add_argument(
        "--cycles",
        type=int,
        default=1,
        help=(
            "Number of times to run all five scenarios. "
            "Example: 20 cycles creates 100 cases."
        ),
    )

    parser.add_argument(
        "--simulate-captures",
        action="store_true",
        help=(
            "Send local captured-payment simulations for "
            "recoverable scenarios."
        ),
    )

    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=5,
        help=(
            "Wait before simulated capture events."
        ),
    )

    return parser.parse_args()


def create_webhook_url() -> str:
    if settings.demo_tenant_id is None:
        raise RuntimeError(
            "DEMO_TENANT_ID is missing from backend/.env"
        )

    return (
        settings.backend_api_base_url.rstrip("/")
        + "/webhooks/razorpay/"
        + str(settings.demo_tenant_id)
    )


def send_webhook(
    client: httpx.Client,
    webhook_url: str,
    payload: dict,
) -> dict:
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
        f"evt_batch_{uuid4().hex}"
    )

    response = client.post(
        webhook_url,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": (
                provider_event_id
            ),
        },
    )

    response.raise_for_status()

    return response.json()


def build_failed_payload(
    payment: GeneratedPayment,
    batch_id: str,
) -> dict:
    scenario = payment.scenario

    return {
        "entity": "event",
        "account_id": f"acc_batch_{batch_id}",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment.payment_id,
                    "entity": "payment",
                    "amount": scenario.amount_minor,
                    "currency": "INR",
                    "status": "failed",
                    "customer_id": (
                        payment.customer_id
                    ),
                    "error_code": (
                        scenario.error_code
                    ),
                    "error_description": (
                        f"Batch test: {scenario.name}"
                    ),
                    "error_source": (
                        scenario.error_source
                    ),
                    "error_step": (
                        scenario.error_step
                    ),
                    "error_reason": (
                        scenario.error_reason
                    ),
                    "notes": {
                        "recoverai_batch_id": batch_id,
                        "scenario": scenario.name,
                    },
                }
            }
        },
        "created_at": int(time.time()),
    }


def build_captured_payload(
    payment: GeneratedPayment,
    batch_id: str,
) -> dict:
    return {
        "entity": "event",
        "account_id": f"acc_batch_{batch_id}",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment.payment_id,
                    "entity": "payment",
                    "amount": (
                        payment.scenario.amount_minor
                    ),
                    "currency": "INR",
                    "status": "captured",
                    "captured": True,
                    "customer_id": (
                        payment.customer_id
                    ),
                    "notes": {
                        "recoverai_batch_id": batch_id,
                        "simulation": (
                            "local_capture"
                        ),
                    },
                }
            }
        },
        "created_at": int(time.time()),
    }


def main() -> None:
    arguments = parse_arguments()

    if arguments.cycles < 1:
        raise ValueError(
            "--cycles must be at least 1"
        )

    if arguments.wait_seconds < 0:
        raise ValueError(
            "--wait-seconds cannot be negative"
        )

    if not settings.razorpay_webhook_secret:
        raise RuntimeError(
            "RAZORPAY_WEBHOOK_SECRET is not configured"
        )

    webhook_url = create_webhook_url()
    batch_id = uuid4().hex[:12]

    generated_payments: list[
        GeneratedPayment
    ] = []

    total_cases = (
        arguments.cycles * len(SCENARIOS)
    )

    print()
    print("Starting dynamic recovery batch")
    print("Batch ID:", batch_id)
    print("Cases:", total_cases)
    print("Webhook URL:", webhook_url)
    print()

    sequence = 0

    with httpx.Client(timeout=15) as client:
        for _ in range(arguments.cycles):
            for scenario in SCENARIOS:
                sequence += 1

                payment = GeneratedPayment(
                    payment_id=(
                        f"pay_batch_{batch_id}_"
                        f"{sequence:04d}"
                    ),
                    customer_id=(
                        f"cust_batch_{uuid4().hex[:12]}"
                    ),
                    scenario=scenario,
                )

                response = send_webhook(
                    client=client,
                    webhook_url=webhook_url,
                    payload=build_failed_payload(
                        payment=payment,
                        batch_id=batch_id,
                    ),
                )

                generated_payments.append(payment)

                print(
                    f"FAILED | {payment.payment_id} "
                    f"| {scenario.name} "
                    f"| INR "
                    f"{scenario.amount_minor / 100:,.2f} "
                    f"| queued="
                    f"{response.get('queued')}"
                )

        if arguments.simulate_captures:
            print()
            print(
                "Waiting before local capture "
                "simulations..."
            )

            time.sleep(
                arguments.wait_seconds
            )

            for payment in generated_payments:
                if not payment.scenario.should_recover:
                    continue

                response = send_webhook(
                    client=client,
                    webhook_url=webhook_url,
                    payload=build_captured_payload(
                        payment=payment,
                        batch_id=batch_id,
                    ),
                )

                print(
                    f"CAPTURED | "
                    f"{payment.payment_id} "
                    f"| queued="
                    f"{response.get('queued')}"
                )

    print()
    print("Batch webhooks submitted successfully.")
    print(
        "Celery will process the stored events."
    )

    if not arguments.simulate_captures:
        print(
            "No payment-success events were simulated."
        )


if __name__ == "__main__":
    main()