from decimal import Decimal
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ml_shadow_decision import (
    MLShadowDecision,
)
from app.models.recovery_case import RecoveryCase
from app.models.recovery_decision import RecoveryDecision
from app.services.ml_action_ranker import (
    rank_recovery_actions,
)


MODEL_NAME = "catboost"
MODEL_VERSION = "catboost_v1_synthetic"
CALIBRATION_METHOD = "platt"


def get_action_value(action: Any) -> str | None:
    if action is None:
        return None

    if hasattr(action, "value"):
        return str(action.value)

    return str(action)


def build_result(
    shadow_decision: MLShadowDecision,
    duplicate: bool = False,
) -> dict[str, str | bool | int | None]:
    return {
        "status": shadow_decision.status,
        "shadow_decision_id": str(
            shadow_decision.id
        ),
        "production_decision_id": str(
            shadow_decision.production_decision_id
        ),
        "selected_action": (
            shadow_decision.selected_action
        ),
        "agrees_with_production": (
            shadow_decision.agrees_with_production
        ),
        "latency_ms": shadow_decision.latency_ms,
        "duplicate": duplicate,
    }


def run_ml_shadow_decision(
    database: Session,
    production_decision_id: UUID,
) -> dict[str, str | bool | int | None]:
    started_at = perf_counter()

    production_decision = database.get(
        RecoveryDecision,
        production_decision_id,
    )

    if production_decision is None:
        raise ValueError(
            "Production recovery decision was not found: "
            f"{production_decision_id}"
        )

    recovery_case = database.get(
        RecoveryCase,
        production_decision.recovery_case_id,
    )

    if recovery_case is None:
        raise ValueError(
            "Recovery case was not found: "
            f"{production_decision.recovery_case_id}"
        )

    existing_shadow_decision = database.execute(
        select(MLShadowDecision).where(
            MLShadowDecision.production_decision_id
            == production_decision.id,
            MLShadowDecision.model_name
            == MODEL_NAME,
            MLShadowDecision.model_version
            == MODEL_VERSION,
        )
    ).scalar_one_or_none()

    if (
        existing_shadow_decision is not None
        and existing_shadow_decision.status
        == "completed"
    ):
        return build_result(
            shadow_decision=existing_shadow_decision,
            duplicate=True,
        )

    if existing_shadow_decision is None:
        shadow_decision = MLShadowDecision(
            tenant_id=production_decision.tenant_id,
            recovery_case_id=recovery_case.id,
            production_decision_id=(
                production_decision.id
            ),
            case_state_version=(
                production_decision.case_state_version
            ),
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
            calibration_method=(
                CALIBRATION_METHOD
            ),
            status="pending",
            alternatives=[],
            input_snapshot={},
        )

        database.add(shadow_decision)
        database.commit()
        database.refresh(shadow_decision)
    else:
        shadow_decision = existing_shadow_decision
        shadow_decision.status = "pending"
        shadow_decision.error_message = None
        database.commit()
        database.refresh(shadow_decision)

    shadow_decision_id = shadow_decision.id

    try:
        rankings = rank_recovery_actions(
            recovery_case=recovery_case,
        )

        if not rankings:
            shadow_decision.status = "invalid"
            shadow_decision.error_message = (
                "No allowed recovery actions were found"
            )
            shadow_decision.latency_ms = round(
                (perf_counter() - started_at) * 1000
            )

            database.commit()
            database.refresh(shadow_decision)

            return build_result(shadow_decision)

        selected_action = rankings[0]

        production_action = get_action_value(
            production_decision.final_action
            or production_decision.recommended_action
        )

        ml_action = str(
            selected_action["action"]
        )

        shadow_decision.status = "completed"
        shadow_decision.selected_action = ml_action

        shadow_decision.raw_probability = Decimal(
            selected_action["raw_probability"]
        )

        shadow_decision.calibrated_probability = (
            Decimal(
                selected_action[
                    "calibrated_probability"
                ]
            )
        )

        shadow_decision.expected_recovery_rupees = (
            Decimal(
                selected_action[
                    "expected_recovery_rupees"
                ]
            )
        )

        shadow_decision.estimated_action_cost_rupees = (
            Decimal(
                selected_action[
                    "estimated_action_cost_rupees"
                ]
            )
        )

        shadow_decision.expected_net_value_rupees = (
            Decimal(
                selected_action[
                    "expected_net_value_rupees"
                ]
            )
        )

        shadow_decision.alternatives = rankings

        shadow_decision.input_snapshot = {
            "production_action": production_action,
            "failure_category": (
                recovery_case.failure_category.value
                if recovery_case.failure_category
                is not None
                else "unknown"
            ),
            "recoverable_amount_rupees": str(
                recovery_case.recoverable_amount_rupees
            ),
            "attempt_count": (
                recovery_case.attempt_count
            ),
            "communication_count": (
                recovery_case.communication_count
            ),
            "case_state": (
                recovery_case.current_state.value
                if hasattr(
                    recovery_case.current_state,
                    "value",
                )
                else str(recovery_case.current_state)
            ),
            "selected_model_features": (
                selected_action["model_features"]
            ),
        }

        shadow_decision.agrees_with_production = (
            ml_action == production_action
        )

        shadow_decision.latency_ms = round(
            (perf_counter() - started_at) * 1000
        )

        shadow_decision.error_message = None

        database.commit()
        database.refresh(shadow_decision)

        return build_result(shadow_decision)

    except Exception as error:
        database.rollback()

        failed_shadow_decision = database.get(
            MLShadowDecision,
            shadow_decision_id,
        )

        if failed_shadow_decision is not None:
            failed_shadow_decision.status = "failed"
            failed_shadow_decision.error_message = str(
                error
            )[:2000]

            failed_shadow_decision.latency_ms = round(
                (perf_counter() - started_at) * 1000
            )

            database.commit()

        raise