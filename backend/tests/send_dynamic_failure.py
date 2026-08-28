import argparse
import hashlib
import hmac
import json
import random
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import uuid4

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class FailureScenario:
    name: str
    error_code: str
    error_description: str
    error_source: str
    error_step: str
    error_reason: str


SCENARIOS = {
    "incorrect_otp": FailureScenario(
        name="incorrect_otp",
        error_code="BAD_REQUEST_ERROR",
        error_description=(
            "Payment authentication failed"
        ),
        error_source="bank",
        error_step="payment_authentication",
        error_reason="incorrect_otp",
    ),
    "insufficient_funds": FailureScenario(
        name="insufficient_funds",
        error_code="BAD_REQUEST_ERROR",
        error_description=(
            "Customer has insufficient funds"
        ),
        error_source="customer",
        error_step="payment_authorization",
        error_reason="insufficient_funds",
    ),
    "expired_card": FailureScenario(
        name="expired_card",
        error_code="BAD_REQUEST_ERROR",
        error_description="Payment method has expired",
        error_source="customer",
        error_step="payment_authorization",
        error_reason="expired_card",
    ),
    "gateway_timeout": FailureScenario(
        name="gateway_timeout",
        error_code="GATEWAY_ERROR",
        error_description="Payment gateway timed out",
        error_source="gateway",
        error_step="payment_processing",
        error_reason="gateway_timeout",
    ),
    "unknown_failure": FailureScenario(
        name="unknown_failure",
        error_code="UNKNOWN_ERROR",
        error_description=(
            "Unexpected payment provider failure"
        ),
        error_source="unknown",
        error_step="payment_processing",
        error_reason="unexpected_failure",
    ),
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send a dynamically generated failed-payment "
            "webhook to RecoverAI."
        )
    )

    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        help=(
            "Failure scenario. A random scenario is used "
            "when omitted."
        ),
    )

    parser.add_argument(
        "--amount-rupees",
        type=str,
        help=(
            "Payment amount in rupees. A random amount is "
            "used when omitted."
        ),
    )

    parser.add_argument(
        "--duplicate",
        action="store_true",
        help=(
            "Send the same event twice to verify "
            "idempotency."
        ),
    )

    return parser.parse_args()


def choose_scenario(
    requested_name: str | None,
) -> FailureScenario:
    if requested_name is not None:
        return SCENARIOS[requested_name]

    return random.SystemRandom().choice(
        list(SCENARIOS.values())
    )


def choose_amount_rupees(
    requested_amount: str | None,
) -> Decimal:
    if requested_amount is None:
        random_amount = random.SystemRandom().randrange(
            199,
            10001,
        )

        return Decimal(random_amount).quantize(
            Decimal("0.01")
        )

    try:
        amount = Decimal(requested_amount).quantize(
            Decimal("0.01")
        )
    except InvalidOperation as error:
        raise ValueError(
            "Amount must be a valid rupee value"
        ) from error

    if amount <= Decimal("0"):
        raise ValueError(
            "Amount must be greater than zero"
        )

    return amount


def build_payload(
    payment_id: str,
    customer_id: str,
    run_id: str,
    amount_rupees: Decimal,
    scenario: FailureScenario,
) -> dict:
    # Razorpay webhook amounts use minor currency units.
    # RecoverAI converts them at the provider boundary and
    # stores business values in rupees.
    amount_paise = int(amount_rupees * 100)

    payment_entity = {
        "id": payment_id,
        "entity": "payment",
        "amount": amount_paise,
        "currency": "INR",
        "status": "failed",
        "customer_id": customer_id,
        "error_code": scenario.error_code,
        "error_description": (
            scenario.error_description
        ),
        "error_source": scenario.error_source,
        "error_step": scenario.error_step,
        "error_reason": scenario.error_reason,
        "notes": {
            "recoverai_test_run_id": run_id,
            "scenario": scenario.name,
        },
    }

    customer_email = (
        settings.demo_customer_email.strip()
    )

    customer_contact = (
        settings.demo_customer_contact.strip()
    )

    # Empty recipient values are omitted completely.
    if customer_email:
        payment_entity["email"] = customer_email

    if customer_contact:
        payment_entity["contact"] = customer_contact

    return {
        "entity": "event",
        "account_id": f"acc_test_{run_id}",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": payment_entity,
            }
        },
        "created_at": int(time.time()),
    }

def encode_and_sign(
    payload: dict,
) -> tuple[bytes, str]:
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

    return raw_body, signature


def send_event(
    client: httpx.Client,
    webhook_url: str,
    raw_body: bytes,
    signature: str,
    provider_event_id: str,
) -> dict:
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

    print("HTTP status:", response.status_code)

    response.raise_for_status()

    result = response.json()
    print("Response:", result)

    return result


def main() -> None:
    arguments = parse_arguments()

    if settings.demo_tenant_id is None:
        raise RuntimeError(
            "DEMO_TENANT_ID is missing from backend/.env"
        )

    if not settings.razorpay_webhook_secret:
        raise RuntimeError(
            "RAZORPAY_WEBHOOK_SECRET is not configured"
        )

    run_id = uuid4().hex[:12]

    payment_id = f"pay_test_{run_id}"
    customer_id = f"cust_test_{uuid4().hex[:12]}"
    provider_event_id = f"evt_test_{uuid4().hex}"

    scenario = choose_scenario(
        arguments.scenario
    )

    amount_rupees = choose_amount_rupees(
        arguments.amount_rupees
    )

    payload = build_payload(
        payment_id=payment_id,
        customer_id=customer_id,
        run_id=run_id,
        amount_rupees=amount_rupees,
        scenario=scenario,
    )

    raw_body, signature = encode_and_sign(
        payload
    )

    webhook_url = (
        settings.backend_api_base_url.rstrip("/")
        + "/webhooks/razorpay/"
        + str(settings.demo_tenant_id)
    )

    print()
    print("Dynamic failed-payment test")
    print("Run ID:", run_id)
    print("Tenant ID:", settings.demo_tenant_id)
    print("Payment ID:", payment_id)
    print("Customer ID:", customer_id)
    print("Scenario:", scenario.name)
    print("Amount:", f"₹{amount_rupees:,.2f}")
    print("Webhook URL:", webhook_url)
    print()

    with httpx.Client(timeout=15) as client:
        send_event(
            client=client,
            webhook_url=webhook_url,
            raw_body=raw_body,
            signature=signature,
            provider_event_id=provider_event_id,
        )

        if arguments.duplicate:
            print()
            print(
                "Sending identical event again "
                "for idempotency verification..."
            )

            send_event(
                client=client,
                webhook_url=webhook_url,
                raw_body=raw_body,
                signature=signature,
                provider_event_id=provider_event_id,
            )

    print()
    print(
        "Webhook submitted. Celery will create and "
        "evaluate the recovery case."
    )


if __name__ == "__main__":
    main()