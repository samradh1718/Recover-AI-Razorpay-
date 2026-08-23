import hashlib
import hmac
import json
from uuid import uuid4

import httpx

from app.core.config import settings


TENANT_ID = "11111111-1111-1111-1111-111111111111"
PAYMENT_ID = "pay_test_auto_005"

payload = {
    "entity": "event",
    "account_id": "acc_local_test",
    "event": "payment.failed",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": PAYMENT_ID,
                "entity": "payment",
                "amount": 150000,
                "currency": "INR",
                "status": "failed",
                "customer_id": "cust_auto_005",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Payment authentication failed",
                "error_source": "bank",
                "error_step": "payment_authentication",
                "error_reason": "incorrect_otp",
            }
        }
    },
    "created_at": 1787400000,
}

raw_body = json.dumps(
    payload,
    separators=(",", ":"),
).encode("utf-8")

signature = hmac.new(
    key=settings.razorpay_webhook_secret.encode("utf-8"),
    msg=raw_body,
    digestmod=hashlib.sha256,
).hexdigest()

event_id = f"evt_local_{uuid4()}"

response = httpx.post(
    (
        "http://127.0.0.1:8000"
        f"/api/v1/webhooks/razorpay/{TENANT_ID}"
    ),
    content=raw_body,
    headers={
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": event_id,
    },
    timeout=10,
)

print("Status:", response.status_code)
print("Response:", response.json())
print("Event ID:", event_id)
print("Payment ID:", PAYMENT_ID)