from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_shadow_decision import AIShadowDecision
from app.models.recovery_case import RecoveryCase
from app.models.recovery_decision import RecoveryDecision


def enum_value(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "value"):
        return str(value.value)

    return str(value)


def get_ai_shadow_summary(
    database: Session,
    tenant_id: UUID,
) -> dict[str, Any]:
    statement = select(
        func.count(AIShadowDecision.id).label(
            "total_evaluations"
        ),
        func.count(AIShadowDecision.id)
        .filter(AIShadowDecision.status == "completed")
        .label("completed_count"),
        func.count(AIShadowDecision.id)
        .filter(AIShadowDecision.status == "failed")
        .label("failed_count"),
        func.count(AIShadowDecision.id)
        .filter(AIShadowDecision.status == "invalid")
        .label("invalid_count"),
        func.count(AIShadowDecision.id)
        .filter(AIShadowDecision.status == "pending")
        .label("pending_count"),
        func.count(AIShadowDecision.id)
        .filter(
            AIShadowDecision.agrees_with_production.is_(True)
        )
        .label("agreement_count"),
        func.count(AIShadowDecision.id)
        .filter(
            AIShadowDecision.agrees_with_production.is_(False)
        )
        .label("disagreement_count"),
        func.avg(AIShadowDecision.latency_ms)
        .filter(AIShadowDecision.latency_ms.is_not(None))
        .label("average_latency_ms"),
        func.max(AIShadowDecision.created_at).label(
            "latest_evaluation_at"
        ),
    ).where(
        AIShadowDecision.tenant_id == tenant_id
    )

    row = database.execute(statement).one()

    agreement_total = (
        row.agreement_count + row.disagreement_count
    )

    agreement_rate = (
        round(
            (row.agreement_count / agreement_total) * 100,
            2,
        )
        if agreement_total > 0
        else 0.0
    )

    average_latency = (
        round(float(row.average_latency_ms), 2)
        if row.average_latency_ms is not None
        else None
    )

    return {
        "total_evaluations": row.total_evaluations,
        "completed_count": row.completed_count,
        "failed_count": row.failed_count,
        "invalid_count": row.invalid_count,
        "pending_count": row.pending_count,
        "agreement_count": row.agreement_count,
        "disagreement_count": row.disagreement_count,
        "agreement_rate_percent": agreement_rate,
        "average_latency_ms": average_latency,
        "latest_evaluation_at": row.latest_evaluation_at,
    }


def list_ai_shadow_decisions(
    database: Session,
    tenant_id: UUID,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    statement = (
        select(
            AIShadowDecision,
            RecoveryDecision.recommended_action.label(
                "production_recommended_action"
            ),
            RecoveryDecision.final_action.label(
                "production_final_action"
            ),
            RecoveryCase.provider_payment_id,
            RecoveryCase.failure_category,
        )
        .join(
            RecoveryDecision,
            RecoveryDecision.id
            == AIShadowDecision.production_decision_id,
        )
        .join(
            RecoveryCase,
            RecoveryCase.id
            == AIShadowDecision.recovery_case_id,
        )
        .where(
            AIShadowDecision.tenant_id == tenant_id
        )
        .order_by(
            AIShadowDecision.created_at.desc()
        )
        .offset(offset)
        .limit(limit)
    )

    rows = database.execute(statement).all()
    results: list[dict[str, Any]] = []

    for row in rows:
        shadow = row.AIShadowDecision

        production_action = (
            row.production_final_action
            or row.production_recommended_action
        )

        results.append(
            {
                "id": shadow.id,
                "recovery_case_id": shadow.recovery_case_id,
                "production_decision_id": (
                    shadow.production_decision_id
                ),
                "provider_payment_id": (
                    row.provider_payment_id
                ),
                "failure_category": enum_value(
                    row.failure_category
                ),
                "model_name": shadow.model_name,
                "prompt_version": shadow.prompt_version,
                "status": shadow.status,
                "production_action": enum_value(
                    production_action
                ),
                "ai_recommended_action": (
                    shadow.recommended_action
                ),
                "agrees_with_production": (
                    shadow.agrees_with_production
                ),
                "recovery_probability": (
                    shadow.recovery_probability
                ),
                "expected_recovery_rupees": (
                    shadow.expected_recovery_rupees
                ),
                "estimated_action_cost_rupees": (
                    shadow.estimated_action_cost_rupees
                ),
                "expected_net_value_rupees": (
                    shadow.expected_net_value_rupees
                ),
                "explanation": shadow.explanation,
                "reason_codes": shadow.reason_codes or [],
                "latency_ms": shadow.latency_ms,
                "error_message": shadow.error_message,
                "created_at": shadow.created_at,
            }
        )

    return results