from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_shadow_decision import (
    AIShadowDecision,
)
from app.models.recovery_case import RecoveryCase
from app.models.recovery_decision import RecoveryDecision
from app.services.ollama_shadow_service import (
    generate_shadow_recommendation,
)


MONEY_PRECISION = Decimal("0.01")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_value(value: Any) -> str | None:
    if value is None:
        return None

    return str(
        getattr(value, "value", value)
    )


def hours_until(
    deadline: datetime,
) -> int:
    if deadline.tzinfo is None:
        deadline = deadline.replace(
            tzinfo=timezone.utc
        )

    remaining_seconds = (
        deadline - utc_now()
    ).total_seconds()

    return max(
        0,
        int(remaining_seconds // 3600),
    )


def build_shadow_input(
    recovery_case: RecoveryCase,
) -> dict[str, Any]:
    return {
        "failure_category": enum_value(
            recovery_case.failure_category
        ),
        "recoverable_amount_rupees": str(
            recovery_case.recoverable_amount_rupees
        ),
        "currency": recovery_case.currency,
        "current_state": enum_value(
            recovery_case.current_state
        ),
        "case_state_version": (
            recovery_case.state_version
        ),
        "attempt_count": recovery_case.attempt_count,
        "communication_count": (
            recovery_case.communication_count
        ),
        "hours_until_deadline": hours_until(
            recovery_case.recovery_deadline_at
        ),
    }


def get_action_cost(
    production_decision: RecoveryDecision,
    action: str,
) -> Decimal | None:
    production_action = (
        production_decision.final_action
        or production_decision.recommended_action
    )

    if enum_value(production_action) == action:
        return Decimal(
            production_decision
            .estimated_action_cost_rupees
        ).quantize(MONEY_PRECISION)

    for alternative in (
        production_decision.alternatives or []
    ):
        if alternative.get("action") != action:
            continue

        cost = alternative.get(
            "estimated_action_cost_rupees"
        )

        if cost is None:
            return None

        return Decimal(str(cost)).quantize(
            MONEY_PRECISION
        )

    return None


def sanitized_provider_response(
    provider_response: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model": provider_response.get("model"),
        "done": provider_response.get("done"),
        "done_reason": provider_response.get(
            "done_reason"
        ),
        "total_duration": provider_response.get(
            "total_duration"
        ),
        "prompt_eval_count": provider_response.get(
            "prompt_eval_count"
        ),
        "eval_count": provider_response.get(
            "eval_count"
        ),
        "recommendation": recommendation,
    }


def run_ai_shadow_decision(
    database: Session,
    production_decision_id: UUID,
) -> dict[str, str | bool | int | None]:
    production_decision = database.get(
        RecoveryDecision,
        production_decision_id,
    )

    if production_decision is None:
        raise ValueError(
            "Production recovery decision was not found"
        )

    recovery_case = database.get(
        RecoveryCase,
        production_decision.recovery_case_id,
    )

    if recovery_case is None:
        raise ValueError(
            "Recovery case was not found"
        )

    existing_shadow = database.execute(
        select(AIShadowDecision).where(
            AIShadowDecision.production_decision_id
            == production_decision.id,
            AIShadowDecision.model_name
            == settings.ollama_model,
            AIShadowDecision.prompt_version
            == settings.ollama_prompt_version,
        )
    ).scalar_one_or_none()

    if (
        existing_shadow is not None
        and existing_shadow.status == "completed"
    ):
        return {
            "status": "already_completed",
            "shadow_decision_id": str(
                existing_shadow.id
            ),
            "agrees_with_production": (
                existing_shadow
                .agrees_with_production
            ),
        }

    input_snapshot = build_shadow_input(
        recovery_case
    )

    if existing_shadow is None:
        shadow_decision = AIShadowDecision(
            tenant_id=production_decision.tenant_id,
            recovery_case_id=recovery_case.id,
            production_decision_id=(
                production_decision.id
            ),
            case_state_version=(
                production_decision
                .case_state_version
            ),
            model_name=settings.ollama_model,
            prompt_version=(
                settings.ollama_prompt_version
            ),
            status="pending",
            reason_codes=[],
            input_snapshot=input_snapshot,
        )

        database.add(shadow_decision)
        database.commit()
        database.refresh(shadow_decision)

    else:
        shadow_decision = existing_shadow
        shadow_decision.status = "pending"
        shadow_decision.error_message = None
        shadow_decision.input_snapshot = (
            input_snapshot
        )
        database.commit()

    shadow_decision_id = shadow_decision.id

    try:
        generation_result = (
            generate_shadow_recommendation(
                input_snapshot=input_snapshot
            )
        )

        recommendation = (
            generation_result.recommendation
        )

        recommended_action = (
            recommendation.recommended_action
        )

        probability = Decimal(
            str(recommendation.recovery_probability)
        )

        recoverable_amount = Decimal(
            recovery_case.recoverable_amount_rupees
        )

        expected_recovery = (
            recoverable_amount * probability
        ).quantize(MONEY_PRECISION)

        estimated_cost = get_action_cost(
            production_decision=production_decision,
            action=recommended_action,
        )

        expected_net_value = (
            (
                expected_recovery - estimated_cost
            ).quantize(MONEY_PRECISION)
            if estimated_cost is not None
            else None
        )

        production_action = enum_value(
            production_decision.final_action
            or production_decision
            .recommended_action
        )

        agrees_with_production = (
            production_action
            == recommended_action
        )

        recommendation_json = (
            recommendation.model_dump(
                mode="json"
            )
        )

        stored_shadow = database.get(
            AIShadowDecision,
            shadow_decision_id,
        )

        if stored_shadow is None:
            raise RuntimeError(
                "Shadow decision record disappeared"
            )

        stored_shadow.status = "completed"
        stored_shadow.recommended_action = (
            recommended_action
        )
        stored_shadow.recovery_probability = (
            probability
        )
        stored_shadow.expected_recovery_rupees = (
            expected_recovery
        )
        stored_shadow.estimated_action_cost_rupees = (
            estimated_cost
        )
        stored_shadow.expected_net_value_rupees = (
            expected_net_value
        )
        stored_shadow.explanation = (
            recommendation.explanation
        )
        stored_shadow.reason_codes = (
            recommendation.reason_codes
        )
        stored_shadow.response_json = (
            sanitized_provider_response(
                provider_response=(
                    generation_result
                    .provider_response
                ),
                recommendation=recommendation_json,
            )
        )
        stored_shadow.agrees_with_production = (
            agrees_with_production
        )
        stored_shadow.latency_ms = (
            generation_result.latency_ms
        )
        stored_shadow.error_message = None

        database.commit()

        return {
            "status": "completed",
            "shadow_decision_id": str(
                stored_shadow.id
            ),
            "production_decision_id": str(
                production_decision.id
            ),
            "recommended_action": (
                recommended_action
            ),
            "agrees_with_production": (
                agrees_with_production
            ),
            "latency_ms": (
                generation_result.latency_ms
            ),
        }

    except Exception as error:
        database.rollback()

        failed_shadow = database.get(
            AIShadowDecision,
            shadow_decision_id,
        )

        if failed_shadow is not None:
            failed_shadow.status = "failed"
            failed_shadow.error_message = str(
                error
            )[:1000]
            database.commit()

        raise