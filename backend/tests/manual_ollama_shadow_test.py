import json

from app.services.ollama_shadow_service import (
    generate_shadow_recommendation,
)


input_snapshot = {
    "failure_category": "mandate_or_authorization",
    "recoverable_amount_rupees": "1500.00",
    "currency": "INR",
    "current_state": "DETECTED",
    "attempt_count": 0,
    "communication_count": 0,
    "hours_until_deadline": 168,
}

result = generate_shadow_recommendation(
    input_snapshot=input_snapshot,
)

print("Model:")
print(result.provider_response.get("model"))

print("\nLatency:")
print(f"{result.latency_ms} ms")

print("\nValidated recommendation:")
print(
    json.dumps(
        result.recommendation.model_dump(
            mode="json"
        ),
        indent=2,
    )
)