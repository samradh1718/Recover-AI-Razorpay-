from decimal import Decimal
from typing import Any
from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.ml_shadow_decision import (
    MLShadowDecision,
)
from app.models.recovery_case import RecoveryCase
from app.models.recovery_decision import RecoveryDecision


def get_enum_value(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "value"):
        return str(value.value)

    return str(value)


def list_ml_shadow_decisions(
    database: Session,
    tenant_id: UUID,
    offset: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = database.execute(
        select(
            MLShadowDecision,
            RecoveryDecision,
            RecoveryCase,
        )
        .join(
            RecoveryDecision,
            RecoveryDecision.id
            == MLShadowDecision.production_decision_id,
        )
        .join(
            RecoveryCase,
            RecoveryCase.id
            == MLShadowDecision.recovery_case_id,
        )
        .where(
            MLShadowDecision.tenant_id == tenant_id
        )
        .order_by(
            MLShadowDecision.created_at.desc()
        )
        .offset(offset)
        .limit(limit)
    ).all()

    results: list[dict[str, Any]] = []

    for (
        shadow_decision,
        production_decision,
        recovery_case,
    ) in rows:
        production_action = (
            production_decision.final_action
            or production_decision.recommended_action
        )

        results.append(
            {
                "id": shadow_decision.id,
                "recovery_case_id": (
                    shadow_decision.recovery_case_id
                ),
                "production_decision_id": (
                    shadow_decision.production_decision_id
                ),
                "provider_payment_id": (
                    recovery_case.provider_payment_id
                ),
                "failure_category": get_enum_value(
                    recovery_case.failure_category
                ),
                "model_name": (
                    shadow_decision.model_name
                ),
                "model_version": (
                    shadow_decision.model_version
                ),
                "calibration_method": (
                    shadow_decision.calibration_method
                ),
                "status": shadow_decision.status,
                "production_action": get_enum_value(
                    production_action
                ),
                "ml_selected_action": (
                    shadow_decision.selected_action
                ),
                "raw_probability": (
                    shadow_decision.raw_probability
                ),
                "calibrated_probability": (
                    shadow_decision.calibrated_probability
                ),
                "expected_recovery_rupees": (
                    shadow_decision
                    .expected_recovery_rupees
                ),
                "estimated_action_cost_rupees": (
                    shadow_decision
                    .estimated_action_cost_rupees
                ),
                "expected_net_value_rupees": (
                    shadow_decision
                    .expected_net_value_rupees
                ),
                "agrees_with_production": (
                    shadow_decision
                    .agrees_with_production
                ),
                "alternatives": (
                    shadow_decision.alternatives or []
                ),
                "latency_ms": (
                    shadow_decision.latency_ms
                ),
                "error_message": (
                    shadow_decision.error_message
                ),
                "created_at": (
                    shadow_decision.created_at
                ),
            }
        )

    return results


def get_ml_shadow_summary(
    database: Session,
    tenant_id: UUID,
) -> dict[str, Any]:
    completed_condition = (
        MLShadowDecision.status == "completed"
    )

    summary = database.execute(
        select(
            func.count(
                MLShadowDecision.id
            ).label("total_evaluations"),
            func.sum(
                case(
                    (
                        MLShadowDecision.status
                        == "completed",
                        1,
                    ),
                    else_=0,
                )
            ).label("completed_count"),
            func.sum(
                case(
                    (
                        MLShadowDecision.status
                        == "failed",
                        1,
                    ),
                    else_=0,
                )
            ).label("failed_count"),
            func.sum(
                case(
                    (
                        MLShadowDecision.status
                        == "invalid",
                        1,
                    ),
                    else_=0,
                )
            ).label("invalid_count"),
            func.sum(
                case(
                    (
                        MLShadowDecision.status
                        == "pending",
                        1,
                    ),
                    else_=0,
                )
            ).label("pending_count"),
            func.sum(
                case(
                    (
                        MLShadowDecision
                        .agrees_with_production.is_(True),
                        1,
                    ),
                    else_=0,
                )
            ).label("agreement_count"),
            func.sum(
                case(
                    (
                        MLShadowDecision
                        .agrees_with_production.is_(False),
                        1,
                    ),
                    else_=0,
                )
            ).label("disagreement_count"),
            func.avg(
                case(
                    (
                        completed_condition,
                        MLShadowDecision.raw_probability,
                    ),
                    else_=None,
                )
            ).label("average_raw_probability"),
            func.avg(
                case(
                    (
                        completed_condition,
                        MLShadowDecision
                        .calibrated_probability,
                    ),
                    else_=None,
                )
            ).label(
                "average_calibrated_probability"
            ),
            func.avg(
                case(
                    (
                        completed_condition,
                        MLShadowDecision
                        .expected_net_value_rupees,
                    ),
                    else_=None,
                )
            ).label(
                "average_expected_net_value_rupees"
            ),
            func.avg(
                case(
                    (
                        completed_condition,
                        MLShadowDecision.latency_ms,
                    ),
                    else_=None,
                )
            ).label("average_latency_ms"),
            func.max(
                MLShadowDecision.created_at
            ).label("latest_evaluation_at"),
        )
        .where(
            MLShadowDecision.tenant_id == tenant_id
        )
    ).one()

    agreement_count = int(
        summary.agreement_count or 0
    )

    disagreement_count = int(
        summary.disagreement_count or 0
    )

    compared_count = (
        agreement_count + disagreement_count
    )

    agreement_rate_percent = (
        round(
            100 * agreement_count / compared_count,
            2,
        )
        if compared_count > 0
        else 0.0
    )

    def decimal_or_none(
        value:Any,
        precision:Decimal,
    ) -> Decimal | None:
        if value is None:
            return None
        
        return Decimal(str(value)).quantize(
            precision,
            rounding=ROUND_HALF_UP,
        )

    return {
        "total_evaluations": int(
            summary.total_evaluations or 0
        ),
        "completed_count": int(
            summary.completed_count or 0
        ),
        "failed_count": int(
            summary.failed_count or 0
        ),
        "invalid_count": int(
            summary.invalid_count or 0
        ),
        "pending_count": int(
            summary.pending_count or 0
        ),
        "agreement_count": agreement_count,
        "disagreement_count": disagreement_count,
        "agreement_rate_percent": (
            agreement_rate_percent
        ),
        "average_raw_probability": decimal_or_none(
            summary.average_raw_probability,
            Decimal("0.0001"),
        ),
        "average_calibrated_probability": (
            decimal_or_none(
                summary
                .average_calibrated_probability,
                Decimal("0.0001")
            )
        ),
        "average_expected_net_value_rupees": (
            decimal_or_none(
                summary
                .average_expected_net_value_rupees,
                Decimal("0.0001")
            )
        ),
        "average_latency_ms": (
            round(float(summary.average_latency_ms))
            if summary.average_latency_ms
            is not None
            else None
        ),
        "latest_evaluation_at": (
            summary.latest_evaluation_at
        ),
    }