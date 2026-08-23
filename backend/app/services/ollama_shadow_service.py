import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

from app.contracts.ai_shadow import (
    AIShadowRecommendation,
)
from app.core.config import settings


SHADOW_SYSTEM_PROMPT = """
You are RecoverAI's payment recovery advisor operating
strictly in shadow mode.

You may recommend one recovery action, but you cannot
execute payments, contact customers, change case state,
schedule retries, or bypass policy controls.

Use only the supplied case attributes.

Choose exactly one action from:
- retry_payment
- send_payment_link
- request_payment_method_update
- request_customer_authorization
- human_review
- stop_recovery

The recovery_probability must be between 0 and 1.

Keep the explanation concise and evidence-based.
Return only the structured response requested by the
provided JSON schema.
""".strip()


class OllamaShadowServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ShadowGenerationResult:
    recommendation: AIShadowRecommendation
    input_snapshot: dict[str, Any]
    provider_response: dict[str, Any]
    latency_ms: int


def generate_shadow_recommendation(
    input_snapshot: dict[str, Any],
) -> ShadowGenerationResult:
    if not settings.ai_shadow_mode_enabled:
        raise OllamaShadowServiceError(
            "AI shadow mode is disabled"
        )

    request_payload = {
        "model": settings.ollama_model,
        "system": SHADOW_SYSTEM_PROMPT,
        "prompt": (
            "Evaluate this payment recovery case:\n"
            f"{json.dumps(input_snapshot, indent=2)}"
        ),
        "stream": False,
        "format": (
            AIShadowRecommendation.model_json_schema()
        ),
        "options": {
            "temperature": 0,
        },
    }

    endpoint = (
        f"{settings.ollama_base_url.rstrip('/')}"
        "/api/generate"
    )

    started_at = perf_counter()

    try:
        response = httpx.post(
            endpoint,
            json=request_payload,
            timeout=settings.ollama_timeout_seconds,
        )

        response.raise_for_status()

    except httpx.TimeoutException as error:
        raise OllamaShadowServiceError(
            "Ollama request timed out"
        ) from error

    except httpx.HTTPError as error:
        raise OllamaShadowServiceError(
            f"Ollama request failed: {error}"
        ) from error

    latency_ms = int(
        (perf_counter() - started_at) * 1000
    )

    response_body = response.json()
    generated_content = response_body.get("response")

    if not isinstance(generated_content, str):
        raise OllamaShadowServiceError(
            "Ollama response did not contain generated content"
        )

    try:
        generated_json = json.loads(generated_content)

        recommendation = (
            AIShadowRecommendation.model_validate(
                generated_json
            )
        )

    except (json.JSONDecodeError, ValueError) as error:
        raise OllamaShadowServiceError(
            "Ollama returned an invalid shadow recommendation"
        ) from error

    return ShadowGenerationResult(
        recommendation=recommendation,
        input_snapshot=input_snapshot,
        provider_response=response_body,
        latency_ms=latency_ms,
    )