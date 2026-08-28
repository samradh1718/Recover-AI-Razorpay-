from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.models import RecoveryCase, RecoveryDecision


RAZORPAY_PAYMENT_LINK_URL = (
    "https://api.razorpay.com/v1/payment_links"
)

PAISE_PER_RUPEE = Decimal("100")
WHOLE_PAISE = Decimal("1")

MINIMUM_EXPIRY_MINUTES = 15
MAXIMUM_EXPIRY_DAYS = 180


class RazorpayPaymentLinkError(Exception):
    """Base exception for Payment Link operations."""


class RazorpayConfigurationError(
    RazorpayPaymentLinkError
):
    """Raised when Test Mode is not safely configured."""


class RazorpayProviderError(
    RazorpayPaymentLinkError
):
    """Raised when Razorpay rejects or fails a request."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def rupees_to_paise(
    amount_rupees: Decimal,
) -> int:
    """Convert database rupees to Razorpay API paise.

    The database continues storing rupees. Conversion happens
    only at the Razorpay API boundary.
    """

    amount = Decimal(
        str(amount_rupees)
    )

    if amount <= Decimal("0.00"):
        raise RazorpayPaymentLinkError(
            "Payment Link amount must be "
            "greater than zero"
        )

    amount_paise = (
        amount * PAISE_PER_RUPEE
    ).quantize(
        WHOLE_PAISE,
        rounding=ROUND_HALF_UP,
    )

    return int(amount_paise)


def build_reference_id(
    decision_id: UUID,
) -> str:
    """Create a deterministic reference below 40 characters."""

    reference_id = (
        f"rcv_{decision_id.hex}"
    )

    if len(reference_id) > 40:
        raise RazorpayPaymentLinkError(
            "Generated Payment Link reference "
            "is too long"
        )

    return reference_id


def validate_test_mode_configuration() -> None:
    """Prevent accidental use of Razorpay Live Mode."""

    if not settings.razorpay_actions_enabled:
        raise RazorpayConfigurationError(
            "Razorpay provider actions are disabled"
        )

    if settings.razorpay_mode != "test":
        raise RazorpayConfigurationError(
            "Only Razorpay Test Mode is supported"
        )

    if not settings.razorpay_key_id:
        raise RazorpayConfigurationError(
            "RAZORPAY_KEY_ID is not configured"
        )

    if not settings.razorpay_key_id.startswith(
        "rzp_test_"
    ):
        raise RazorpayConfigurationError(
            "Only an rzp_test_ Razorpay key "
            "is allowed"
        )

    if not settings.razorpay_key_secret:
        raise RazorpayConfigurationError(
            "RAZORPAY_KEY_SECRET is not configured"
        )

    if (
        settings.razorpay_api_timeout_seconds
        <= 0
    ):
        raise RazorpayConfigurationError(
            "Razorpay API timeout must be positive"
        )

    if (
        settings
        .razorpay_payment_link_expiry_minutes
        < MINIMUM_EXPIRY_MINUTES
    ):
        raise RazorpayConfigurationError(
            "Payment Link expiry must be at least "
            f"{MINIMUM_EXPIRY_MINUTES} minutes"
        )


def calculate_expire_by(
    recovery_case: RecoveryCase,
) -> int:
    """Calculate a bounded Payment Link expiry timestamp."""

    now = utc_now()

    configured_expiry = (
        now
        + timedelta(
            minutes=(
                settings
                .razorpay_payment_link_expiry_minutes
            )
        )
    )

    maximum_expiry = (
        now
        + timedelta(
            days=MAXIMUM_EXPIRY_DAYS
        )
    )

    recovery_deadline = as_utc(
        recovery_case.recovery_deadline_at
    )

    expires_at = min(
        configured_expiry,
        maximum_expiry,
        recovery_deadline,
    )

    minimum_expiry = (
        now
        + timedelta(
            minutes=MINIMUM_EXPIRY_MINUTES
        )
    )

    if expires_at < minimum_expiry:
        raise RazorpayPaymentLinkError(
            "The recovery deadline is too close "
            "to create a Payment Link"
        )

    return int(
        expires_at.timestamp()
    )


def extract_provider_error(
    response_body: Any,
    fallback: str,
) -> str:
    """Extract a safe error description from Razorpay."""

    if not isinstance(
        response_body,
        dict,
    ):
        return fallback

    error = response_body.get(
        "error"
    )

    if not isinstance(error, dict):
        return fallback

    description = error.get(
        "description"
    )

    if (
        isinstance(description, str)
        and description
    ):
        return description

    return fallback


def build_safe_provider_snapshot(
    response_body: dict[str, Any],
) -> dict[str, Any]:
    """Keep only fields required for auditing and reconciliation."""

    safe_fields = (
        "id",
        "reference_id",
        "short_url",
        "status",
        "amount",
        "amount_paid",
        "currency",
        "created_at",
        "updated_at",
        "expire_by",
        "expired_at",
    )

    return {
        field: response_body.get(field)
        for field in safe_fields
        if field in response_body
    }


def decode_provider_response(
    response: httpx.Response,
) -> Any:
    """Decode a provider response without raising JSON errors."""

    try:
        return response.json()

    except ValueError:
        return {
            "raw_response": (
                response.text[:1000]
            )
        }


def create_standard_payment_link(
    recovery_case: RecoveryCase,
    decision: RecoveryDecision,
    customer_email: str | None = None,
    customer_contact: str | None = None,
) -> dict[str, Any]:
    """Create one Standard Payment Link in Razorpay Test Mode."""

    validate_test_mode_configuration()

    currency = str(
        recovery_case.currency
        or "INR"
    ).upper()

    if currency != "INR":
        raise RazorpayPaymentLinkError(
            "Phase 1 Payment Links support INR only"
        )

    amount_paise = rupees_to_paise(
        Decimal(
            str(
                recovery_case
                .recoverable_amount_rupees
            )
        )
    )

    reference_id = build_reference_id(
        decision.id
    )

    provider_payment_id = (
        recovery_case.provider_payment_id
        or "not_available"
    )

    if isinstance(customer_email, str):
        customer_email = (
            customer_email.strip() or None
        )
    else:
        customer_email = None

    if isinstance(customer_contact, str):
        customer_contact = (
            customer_contact.strip() or None
        )
    else:
        customer_contact = None

    notifications_enabled = (
        settings
        .razorpay_customer_notifications_enabled
    )

    notification_channel = (
        settings.razorpay_notification_channel
    )

    if (
        notifications_enabled
        and notification_channel == "email"
        and customer_email is None
    ):
        raise RazorpayPaymentLinkError(
            "Customer email is required for "
            "Razorpay email notification"
        )

    if (
        notifications_enabled
        and notification_channel == "sms"
        and customer_contact is None
    ):
        raise RazorpayPaymentLinkError(
            "Customer contact is required for "
            "Razorpay SMS notification"
        )

    notify_email = (
        notifications_enabled
        and notification_channel == "email"
    )

    notify_sms = (
        notifications_enabled
        and notification_channel == "sms"
    )

    notification_requested = (
        notify_email or notify_sms
    )

    request_payload: dict[str, Any] = {
        "amount": amount_paise,
        "currency": currency,
        "accept_partial": False,
        "description": (
            "RecoverAI payment recovery for "
            f"{provider_payment_id}"
        ),
        "reference_id": reference_id,
        "expire_by": calculate_expire_by(
            recovery_case
        ),
        "notify": {
            "sms": notify_sms,
            "email": notify_email,
        },
        "notes": {
            "recoverai_case_id": str(
                recovery_case.id
            ),
            "recoverai_decision_id": str(
                decision.id
            ),
            "provider_payment_id": (
                provider_payment_id
            ),
        },
    }

    customer_payload: dict[str, str] = {}

    if customer_email is not None:
        customer_payload["email"] = (
            customer_email
        )

    if customer_contact is not None:
        customer_payload["contact"] = (
            customer_contact
        )

    if customer_payload:
        request_payload["customer"] = (
            customer_payload
        )

    try:
        response = httpx.post(
            RAZORPAY_PAYMENT_LINK_URL,
            auth=(
                settings.razorpay_key_id,
                settings.razorpay_key_secret,
            ),
            json=request_payload,
            timeout=(
                settings
                .razorpay_api_timeout_seconds
            ),
        )

    except httpx.TimeoutException as error:
        raise RazorpayProviderError(
            "Razorpay Payment Link request "
            "timed out"
        ) from error

    except httpx.RequestError as error:
        raise RazorpayProviderError(
            "Unable to connect to the Razorpay API"
        ) from error

    response_body = decode_provider_response(
        response
    )

    if response.is_error:
        fallback_message = (
            "Razorpay rejected the Payment Link "
            "request with HTTP "
            f"{response.status_code}"
        )

        provider_message = extract_provider_error(
            response_body=response_body,
            fallback=fallback_message,
        )

        raise RazorpayProviderError(
            provider_message
        )

    if not isinstance(
        response_body,
        dict,
    ):
        raise RazorpayProviderError(
            "Razorpay returned an invalid response"
        )

    provider_action_id = response_body.get(
        "id"
    )

    provider_action_url = response_body.get(
        "short_url"
    )

    provider_action_status = response_body.get(
        "status"
    )

    provider_reference_id = response_body.get(
        "reference_id"
    )

    if not isinstance(
        provider_action_id,
        str,
    ):
        raise RazorpayProviderError(
            "Razorpay response is missing "
            "Payment Link ID"
        )

    if not isinstance(
        provider_action_url,
        str,
    ):
        raise RazorpayProviderError(
            "Razorpay response is missing "
            "Payment Link URL"
        )

    if not isinstance(
        provider_action_status,
        str,
    ):
        raise RazorpayProviderError(
            "Razorpay response is missing "
            "Payment Link status"
        )

    if not isinstance(
        provider_reference_id,
        str,
    ):
        raise RazorpayProviderError(
            "Razorpay response is missing "
            "Payment Link reference ID"
        )

    if provider_reference_id != reference_id:
        raise RazorpayProviderError(
            "Razorpay returned an unexpected "
            "Payment Link reference ID"
        )

    return {
        "provider_action_id": (
            provider_action_id
        ),
        "provider_reference_id": (
            provider_reference_id
        ),
        "provider_action_url": (
            provider_action_url
        ),
        "provider_action_status": (
            provider_action_status
        ),
        "provider_response": (
            build_safe_provider_snapshot(
                response_body
            )
        ),
        "amount_paise_sent_to_provider": (
            amount_paise
        ),
        # A successful Payment Link API response means
        # Razorpay accepted the notification request.
        # It does not prove end-device delivery.
        "notification_requested": (
            notification_requested
        ),
        "notification_channel": (
            notification_channel
            if notification_requested
            else None
        ),
    }
def fetch_payment_link(
    provider_action_id: str,
) -> dict[str, Any]:
    """Fetch one Payment Link from Razorpay Test Mode."""

    validate_test_mode_configuration()

    if not provider_action_id:
        raise RazorpayPaymentLinkError(
            "Payment Link ID is required"
        )

    if not provider_action_id.startswith(
        "plink_"
    ):
        raise RazorpayPaymentLinkError(
            "Invalid Razorpay Payment Link ID"
        )

    payment_link_url = (
        f"{RAZORPAY_PAYMENT_LINK_URL}/"
        f"{provider_action_id}"
    )

    try:
        response = httpx.get(
            payment_link_url,
            auth=(
                settings.razorpay_key_id,
                settings.razorpay_key_secret,
            ),
            timeout=(
                settings
                .razorpay_api_timeout_seconds
            ),
        )

    except httpx.TimeoutException as error:
        raise RazorpayProviderError(
            "Razorpay Payment Link status request "
            "timed out"
        ) from error

    except httpx.RequestError as error:
        raise RazorpayProviderError(
            "Unable to connect to the Razorpay API"
        ) from error

    response_body = decode_provider_response(
        response
    )

    if response.is_error:
        fallback_message = (
            "Razorpay rejected the Payment Link "
            "status request with HTTP "
            f"{response.status_code}"
        )

        provider_message = extract_provider_error(
            response_body=response_body,
            fallback=fallback_message,
        )

        raise RazorpayProviderError(
            provider_message
        )

    if not isinstance(
        response_body,
        dict,
    ):
        raise RazorpayProviderError(
            "Razorpay returned an invalid "
            "Payment Link response"
        )

    returned_action_id = response_body.get(
        "id"
    )

    provider_reference_id = response_body.get(
        "reference_id"
    )

    provider_action_url = response_body.get(
        "short_url"
    )

    provider_action_status = response_body.get(
        "status"
    )

    currency = response_body.get(
        "currency"
    )

    amount_paise = response_body.get(
        "amount"
    )

    amount_paid_paise = response_body.get(
        "amount_paid"
    )

    if returned_action_id != provider_action_id:
        raise RazorpayProviderError(
            "Razorpay returned a different "
            "Payment Link ID"
        )

    if not isinstance(
        provider_reference_id,
        str,
    ):
        raise RazorpayProviderError(
            "Razorpay response is missing reference ID"
        )

    if not isinstance(
        provider_action_url,
        str,
    ):
        raise RazorpayProviderError(
            "Razorpay response is missing "
            "Payment Link URL"
        )

    if not isinstance(
        provider_action_status,
        str,
    ):
        raise RazorpayProviderError(
            "Razorpay response is missing "
            "Payment Link status"
        )

    if not isinstance(
        currency,
        str,
    ):
        raise RazorpayProviderError(
            "Razorpay response is missing currency"
        )

    if (
        isinstance(amount_paise, bool)
        or not isinstance(amount_paise, int)
    ):
        raise RazorpayProviderError(
            "Razorpay response contains "
            "an invalid amount"
        )

    if amount_paid_paise is None:
        amount_paid_paise = 0

    if (
        isinstance(amount_paid_paise, bool)
        or not isinstance(
            amount_paid_paise,
            int,
        )
    ):
        raise RazorpayProviderError(
            "Razorpay response contains "
            "an invalid paid amount"
        )

    if (
        amount_paise < 0
        or amount_paid_paise < 0
    ):
        raise RazorpayProviderError(
            "Razorpay response contains "
            "a negative amount"
        )

    return {
        "provider_action_id": (
            returned_action_id
        ),
        "provider_reference_id": (
            provider_reference_id
        ),
        "provider_action_url": (
            provider_action_url
        ),
        "provider_action_status": (
            provider_action_status
        ),
        "currency": currency.upper(),
        "amount_paise": amount_paise,
        "amount_paid_paise": (
            amount_paid_paise
        ),
        "provider_response": (
            build_safe_provider_snapshot(
                response_body
            )
        ),
    }