from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)
from typing import Any
from uuid import UUID, uuid4

import httpx

from app.core.config import settings


RAZORPAY_ORDERS_URL = (
    "https://api.razorpay.com/v1/orders"
)

RAZORPAY_ORDER_ID_PREFIX = "order_"

MONEY = Decimal("0.01")
PAISE_PER_RUPEE = Decimal("100")
WHOLE_PAISE = Decimal("1")


class RazorpayTestOrderError(Exception):
    """Base exception for Test Checkout orders."""


class RazorpayTestOrderConfigurationError(
    RazorpayTestOrderError
):
    """Raised when Test Checkout is not safely configured."""


class RazorpayTestOrderValidationError(
    RazorpayTestOrderError
):
    """Raised when an order request is invalid."""


class RazorpayTestOrderProviderError(
    RazorpayTestOrderError
):
    """Raised when Razorpay rejects or fails an order request."""


def _validate_test_checkout_configuration() -> tuple[str, str]:
    if not settings.razorpay_test_checkout_enabled:
        raise RazorpayTestOrderConfigurationError(
            "Razorpay Test Checkout is disabled"
        )

    if settings.razorpay_mode != "test":
        raise RazorpayTestOrderConfigurationError(
            "Razorpay Test Checkout requires Test Mode"
        )

    key_id = settings.razorpay_key_id.strip()
    key_secret = settings.razorpay_key_secret.strip()

    if not key_id.startswith("rzp_test_"):
        raise RazorpayTestOrderConfigurationError(
            "Razorpay Test Checkout requires an rzp_test key ID"
        )

    if not key_secret:
        raise RazorpayTestOrderConfigurationError(
            "Razorpay Test Checkout key secret is missing"
        )

    maximum_amount = (
        settings.razorpay_test_checkout_max_amount_rupees
    )

    if maximum_amount <= 0:
        raise RazorpayTestOrderConfigurationError(
            "Razorpay Test Checkout maximum amount must be positive"
        )

    return key_id, key_secret


def _normalise_amount(
    amount_rupees: Decimal | int | float | str,
) -> Decimal:
    try:
        amount = Decimal(str(amount_rupees)).quantize(
            MONEY,
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError) as error:
        raise RazorpayTestOrderValidationError(
            "Amount must be a valid rupee value"
        ) from error

    if amount <= Decimal("0.00"):
        raise RazorpayTestOrderValidationError(
            "Amount must be greater than zero"
        )

    maximum_amount = Decimal(
        str(
            settings
            .razorpay_test_checkout_max_amount_rupees
        )
    ).quantize(MONEY)

    if amount > maximum_amount:
        raise RazorpayTestOrderValidationError(
            "Amount exceeds the configured Test Checkout limit of "
            f"INR {maximum_amount}"
        )

    return amount


def _rupees_to_paise(amount_rupees: Decimal) -> int:
    amount_paise = (
        amount_rupees * PAISE_PER_RUPEE
    ).quantize(
        WHOLE_PAISE,
        rounding=ROUND_HALF_UP,
    )

    return int(amount_paise)


def _decode_provider_response(
    response: httpx.Response,
) -> Any:
    try:
        return response.json()
    except ValueError:
        return {
            "raw_response": response.text[:1000],
        }


def _provider_error_message(
    response_body: Any,
    fallback: str,
) -> str:
    if not isinstance(response_body, dict):
        return fallback

    provider_error = response_body.get("error")

    if not isinstance(provider_error, dict):
        return fallback

    description = provider_error.get("description")

    if not isinstance(description, str):
        return fallback

    clean_description = description.strip()

    if not clean_description:
        return fallback

    return clean_description[:500]


def _build_receipt() -> str:
    return f"recoverai_test_{uuid4().hex[:20]}"


def _validate_provider_order_id(
    provider_order_id: str,
) -> str:
    clean_order_id = provider_order_id.strip()

    if (
        not clean_order_id.startswith(
            RAZORPAY_ORDER_ID_PREFIX
        )
        or len(clean_order_id) > 128
    ):
        raise RazorpayTestOrderValidationError(
            "A valid Razorpay Order ID is required"
        )

    return clean_order_id


def _provider_get(
    *,
    url: str,
    operation_name: str,
) -> dict[str, Any]:
    key_id, key_secret = (
        _validate_test_checkout_configuration()
    )

    try:
        response = httpx.get(
            url,
            auth=(key_id, key_secret),
            timeout=(
                settings.razorpay_api_timeout_seconds
            ),
        )
    except httpx.TimeoutException as error:
        raise RazorpayTestOrderProviderError(
            f"Razorpay {operation_name} request timed out"
        ) from error
    except httpx.RequestError as error:
        raise RazorpayTestOrderProviderError(
            "Unable to connect to the Razorpay Orders API"
        ) from error

    response_body = _decode_provider_response(
        response
    )

    if response.is_error:
        fallback_message = (
            f"Razorpay {operation_name} request failed "
            f"with HTTP {response.status_code}"
        )

        raise RazorpayTestOrderProviderError(
            _provider_error_message(
                response_body=response_body,
                fallback=fallback_message,
            )
        )

    if not isinstance(response_body, dict):
        raise RazorpayTestOrderProviderError(
            f"Razorpay returned an invalid {operation_name} "
            "response"
        )

    return response_body


def _safe_order_snapshot(
    provider_order: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": provider_order.get("id"),
        "entity": provider_order.get("entity"),
        "amount": provider_order.get("amount"),
        "amount_paid": provider_order.get(
            "amount_paid"
        ),
        "amount_due": provider_order.get(
            "amount_due"
        ),
        "currency": provider_order.get("currency"),
        "receipt": provider_order.get("receipt"),
        "status": provider_order.get("status"),
        "attempts": provider_order.get("attempts"),
        "created_at": provider_order.get(
            "created_at"
        ),
        "notes": provider_order.get("notes"),
    }


def _safe_payment_snapshot(
    provider_payment: dict[str, Any],
) -> dict[str, Any]:
    # Deliberately excludes customer email, contact, card and
    # bank details. Reconciliation needs status evidence only.
    return {
        "id": provider_payment.get("id"),
        "entity": provider_payment.get("entity"),
        "order_id": provider_payment.get("order_id"),
        "amount": provider_payment.get("amount"),
        "currency": provider_payment.get("currency"),
        "status": provider_payment.get("status"),
        "method": provider_payment.get("method"),
        "captured": provider_payment.get("captured"),
        "amount_refunded": provider_payment.get(
            "amount_refunded"
        ),
        "refund_status": provider_payment.get(
            "refund_status"
        ),
        "error_code": provider_payment.get(
            "error_code"
        ),
        "error_description": provider_payment.get(
            "error_description"
        ),
        "error_source": provider_payment.get(
            "error_source"
        ),
        "error_step": provider_payment.get(
            "error_step"
        ),
        "error_reason": provider_payment.get(
            "error_reason"
        ),
        "created_at": provider_payment.get(
            "created_at"
        ),
    }


def _payment_priority(
    provider_payment: dict[str, Any],
) -> tuple[int, int]:
    status = str(
        provider_payment.get("status") or ""
    ).lower()

    priority = {
        "captured": 50,
        "authorized": 40,
        "refunded": 30,
        "failed": 20,
        "created": 10,
    }.get(status, 0)

    created_at = provider_payment.get("created_at")

    return (
        priority,
        created_at if isinstance(created_at, int) else 0,
    )


def _select_payment_attempt(
    *,
    provider_order_id: str,
    payment_collection: dict[str, Any],
) -> dict[str, Any] | None:
    raw_items = payment_collection.get("items")

    if not isinstance(raw_items, list):
        raise RazorpayTestOrderProviderError(
            "Razorpay returned an invalid order payments response"
        )

    valid_items = [
        item
        for item in raw_items
        if isinstance(item, dict)
        and item.get("order_id") == provider_order_id
        and isinstance(item.get("id"), str)
    ]

    if not valid_items:
        return None

    return max(
        valid_items,
        key=_payment_priority,
    )


def _outcome_status(
    *,
    provider_order_status: str,
    selected_payment: dict[str, Any] | None,
) -> str:
    order_status = provider_order_status.lower()

    if order_status == "paid":
        return "paid"

    if selected_payment is None:
        return "pending"

    payment_status = str(
        selected_payment.get("status") or ""
    ).lower()

    if payment_status == "captured":
        return "paid"

    if payment_status == "authorized":
        return "authorized"

    if payment_status == "refunded":
        return "refunded"

    if payment_status == "failed":
        return "failed"

    return "pending"


def create_razorpay_test_order(
    *,
    tenant_id: UUID,
    amount_rupees: Decimal | int | float | str,
    currency: str = "INR",
    customer_reference: str | None = None,
) -> dict[str, Any]:
    """Create one provider-generated Razorpay Test Mode order.

    The returned key ID is safe for Razorpay Checkout. The key
    secret is used only for the server-to-server request and is
    never returned.
    """

    key_id, key_secret = (
        _validate_test_checkout_configuration()
    )

    normalised_currency = currency.strip().upper()

    if normalised_currency != "INR":
        raise RazorpayTestOrderValidationError(
            "RecoverAI Test Checkout currently supports INR only"
        )

    amount = _normalise_amount(amount_rupees)
    amount_paise = _rupees_to_paise(amount)
    receipt = _build_receipt()

    notes: dict[str, str] = {
        "recoverai_tenant_id": str(tenant_id),
        "recoverai_data_source": (
            "razorpay_test_checkout"
        ),
        "recoverai_provider_generated": "true",
        "recoverai_real_money": "false",
    }

    if customer_reference:
        clean_customer_reference = (
            customer_reference.strip()[:100]
        )

        if clean_customer_reference:
            notes["recoverai_customer_reference"] = (
                clean_customer_reference
            )

    request_payload: dict[str, Any] = {
        "amount": amount_paise,
        "currency": normalised_currency,
        "receipt": receipt,
        "notes": notes,
    }

    try:
        response = httpx.post(
            RAZORPAY_ORDERS_URL,
            auth=(key_id, key_secret),
            json=request_payload,
            timeout=(
                settings.razorpay_api_timeout_seconds
            ),
        )
    except httpx.TimeoutException as error:
        raise RazorpayTestOrderProviderError(
            "Razorpay Test Order request timed out"
        ) from error
    except httpx.RequestError as error:
        raise RazorpayTestOrderProviderError(
            "Unable to connect to the Razorpay Orders API"
        ) from error

    response_body = _decode_provider_response(response)

    if response.is_error:
        fallback_message = (
            "Razorpay rejected the Test Order request with HTTP "
            f"{response.status_code}"
        )

        raise RazorpayTestOrderProviderError(
            _provider_error_message(
                response_body=response_body,
                fallback=fallback_message,
            )
        )

    if not isinstance(response_body, dict):
        raise RazorpayTestOrderProviderError(
            "Razorpay returned an invalid Test Order response"
        )

    provider_order_id = response_body.get("id")
    provider_amount = response_body.get("amount")
    provider_currency = response_body.get("currency")
    provider_receipt = response_body.get("receipt")
    provider_status = response_body.get("status")

    if not isinstance(provider_order_id, str):
        raise RazorpayTestOrderProviderError(
            "Razorpay response is missing the Order ID"
        )

    if provider_amount != amount_paise:
        raise RazorpayTestOrderProviderError(
            "Razorpay returned an unexpected order amount"
        )

    if provider_currency != normalised_currency:
        raise RazorpayTestOrderProviderError(
            "Razorpay returned an unexpected order currency"
        )

    if provider_receipt != receipt:
        raise RazorpayTestOrderProviderError(
            "Razorpay returned an unexpected order receipt"
        )

    if not isinstance(provider_status, str):
        raise RazorpayTestOrderProviderError(
            "Razorpay response is missing the order status"
        )

    return {
        "provider_order_id": provider_order_id,
        "provider_order_status": provider_status,
        "razorpay_key_id": key_id,
        "amount_rupees": str(amount),
        "amount_paise": amount_paise,
        "currency": normalised_currency,
        "receipt": receipt,
        "data_source": "razorpay_test_checkout",
        "provider_generated": True,
        "real_money": False,
        "provider_response": {
            "id": provider_order_id,
            "amount": provider_amount,
            "amount_paid": response_body.get(
                "amount_paid"
            ),
            "amount_due": response_body.get(
                "amount_due"
            ),
            "currency": provider_currency,
            "receipt": provider_receipt,
            "status": provider_status,
            "attempts": response_body.get("attempts"),
            "created_at": response_body.get("created_at"),
            "notes": notes,
        },
    }


def reconcile_razorpay_test_order(
    *,
    tenant_id: UUID,
    provider_order_id: str,
) -> dict[str, Any]:
    """Fetch provider-confirmed Test Mode order evidence.

    This is a localhost-safe fallback for demonstrations where
    Razorpay cannot deliver a webhook to a private URL. Signed
    webhooks remain the preferred production source of truth.
    """

    clean_order_id = _validate_provider_order_id(
        provider_order_id
    )

    provider_order = _provider_get(
        url=f"{RAZORPAY_ORDERS_URL}/{clean_order_id}",
        operation_name="Order fetch",
    )

    returned_order_id = provider_order.get("id")

    if returned_order_id != clean_order_id:
        raise RazorpayTestOrderProviderError(
            "Razorpay returned an unexpected Order ID"
        )

    notes = provider_order.get("notes")

    if not isinstance(notes, dict):
        raise RazorpayTestOrderProviderError(
            "Razorpay order is missing RecoverAI provenance"
        )

    if (
        notes.get("recoverai_tenant_id")
        != str(tenant_id)
        or notes.get("recoverai_data_source")
        != "razorpay_test_checkout"
        or notes.get("recoverai_provider_generated")
        != "true"
        or notes.get("recoverai_real_money")
        != "false"
    ):
        raise RazorpayTestOrderProviderError(
            "Razorpay order provenance does not match RecoverAI"
        )

    provider_status = provider_order.get("status")
    provider_amount = provider_order.get("amount")
    provider_currency = provider_order.get("currency")

    if not isinstance(provider_status, str):
        raise RazorpayTestOrderProviderError(
            "Razorpay response is missing the order status"
        )

    if not isinstance(provider_amount, int):
        raise RazorpayTestOrderProviderError(
            "Razorpay response is missing the order amount"
        )

    if not isinstance(provider_currency, str):
        raise RazorpayTestOrderProviderError(
            "Razorpay response is missing the order currency"
        )

    payment_collection = _provider_get(
        url=(
            f"{RAZORPAY_ORDERS_URL}/"
            f"{clean_order_id}/payments"
        ),
        operation_name="Order payments fetch",
    )

    selected_payment = _select_payment_attempt(
        provider_order_id=clean_order_id,
        payment_collection=payment_collection,
    )

    outcome_status = _outcome_status(
        provider_order_status=provider_status,
        selected_payment=selected_payment,
    )

    provider_payment_id: str | None = None

    if selected_payment is not None:
        payment_id = selected_payment.get("id")

        if isinstance(payment_id, str):
            provider_payment_id = payment_id

    raw_payment_items = payment_collection.get("items")
    safe_payments: list[dict[str, Any]] = []

    if isinstance(raw_payment_items, list):
        safe_payments = [
            _safe_payment_snapshot(item)
            for item in raw_payment_items
            if isinstance(item, dict)
            and item.get("order_id")
            == clean_order_id
        ]

    return {
        "provider_order_id": clean_order_id,
        "provider_order_status": provider_status,
        "provider_payment_id": provider_payment_id,
        "outcome_status": outcome_status,
        "amount_paise": provider_amount,
        "currency": provider_currency,
        "provider_generated": True,
        "real_money": False,
        "evidence_source": "razorpay_server_api",
        "provider_response": {
            "order": _safe_order_snapshot(
                provider_order
            ),
            "payments": safe_payments,
            "reconciliation": {
                "source": "razorpay_server_api",
                "signed_webhook_received": False,
                "localhost_fallback": True,
            },
        },
    }