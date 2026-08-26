from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_shadow_decision import (
    AIShadowDecision,
)
from app.models.ml_shadow_decision import (
    MLShadowDecision,
)
from app.models.payment_event import PaymentEvent
from app.models.recovery_case import RecoveryCase
from app.models.recovery_decision import RecoveryDecision


def get_value(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "value"):
        return str(value.value)

    return str(value)


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if hasattr(value, "value"):
        return value.value

    return value


def build_event(
    event_id: str,
    event_type: str,
    title: str,
    description: str,
    source: str,
    status: str,
    occurred_at: datetime,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": event_id,
        "event_type": event_type,
        "title": title,
        "description": description,
        "source": source,
        "status": status,
        "occurred_at": occurred_at,
        "details": {
            key: json_value(value)
            for key, value in details.items()
        },
    }


def get_case_audit_timeline(
    database: Session,
    tenant_id: UUID,
    case_id: UUID,
) -> dict[str, Any]:
    recovery_case = database.execute(
        select(RecoveryCase).where(
            RecoveryCase.id == case_id,
            RecoveryCase.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()

    if recovery_case is None:
        raise ValueError("Recovery case was not found")

    payment_events = database.scalars(
        select(PaymentEvent)
        .where(
            PaymentEvent.tenant_id == tenant_id,
            PaymentEvent.provider_payment_id
            == recovery_case.provider_payment_id,
        )
        .order_by(PaymentEvent.received_at.asc())
    ).all()

    production_decisions = database.scalars(
        select(RecoveryDecision)
        .where(
            RecoveryDecision.tenant_id == tenant_id,
            RecoveryDecision.recovery_case_id
            == recovery_case.id,
        )
        .order_by(RecoveryDecision.created_at.asc())
    ).all()

    ai_shadow_decisions = database.scalars(
        select(AIShadowDecision)
        .where(
            AIShadowDecision.tenant_id == tenant_id,
            AIShadowDecision.recovery_case_id
            == recovery_case.id,
        )
        .order_by(AIShadowDecision.created_at.asc())
    ).all()

    ml_shadow_decisions = database.scalars(
        select(MLShadowDecision)
        .where(
            MLShadowDecision.tenant_id == tenant_id,
            MLShadowDecision.recovery_case_id
            == recovery_case.id,
        )
        .order_by(MLShadowDecision.created_at.asc())
    ).all()

    events: list[dict[str, Any]] = []

    for payment_event in payment_events:
        events.append(
            build_event(
                event_id=(
                    f"payment:{payment_event.id}:received"
                ),
                event_type="webhook_received",
                title="Payment webhook received",
                description=(
                    f"Received {payment_event.event_type} "
                    "from the payment provider."
                ),
                source="razorpay",
                status="completed",
                occurred_at=payment_event.received_at,
                details={
                    "payment_event_id": payment_event.id,
                    "provider_event_id": (
                        payment_event.provider_event_id
                    ),
                    "event_type": (
                        payment_event.event_type
                    ),
                    "processing_status": (
                        payment_event.processing_status
                    ),
                },
            )
        )

        if payment_event.processed_at is not None:
            events.append(
                build_event(
                    event_id=(
                        f"payment:{payment_event.id}:processed"
                    ),
                    event_type="webhook_processed",
                    title="Payment event processed",
                    description=(
                        "The webhook was validated and "
                        "processed by the recovery pipeline."
                    ),
                    source="worker",
                    status=(
                        payment_event.processing_status
                    ),
                    occurred_at=(
                        payment_event.processed_at
                    ),
                    details={
                        "payment_event_id": (
                            payment_event.id
                        ),
                        "processing_error": (
                            payment_event.processing_error
                        ),
                    },
                )
            )

    events.append(
        build_event(
            event_id=f"case:{recovery_case.id}:created",
            event_type="case_created",
            title="Recovery case detected",
            description=(
                "A revenue recovery case was created "
                "from the failed payment."
            ),
            source="recovery_engine",
            status="DETECTED",
            occurred_at=recovery_case.created_at,
            details={
                "failure_category": (
                    recovery_case.failure_category
                ),
                "recoverable_amount_rupees": (
                    recovery_case
                    .recoverable_amount_rupees
                ),
                "currency": recovery_case.currency,
                "recovery_deadline_at": (
                    recovery_case.recovery_deadline_at
                ),
            },
        )
    )
    for decision in production_decisions:
        production_action = (
                decision.final_action
                or decision.recommended_action
        )

        events.append(
            build_event(
                event_id=(
                    f"decision:{decision.id}:created"
                ),
                event_type="production_decision",
                title="Production decision generated",
                description=(
                    "The bounded rules and policy engine "
                    "selected a recovery action."
                ),
                source="rules_engine",
                status=(
                    get_value(decision.policy_result)
                    or "pending"
                ),
                occurred_at=decision.created_at,
                details={
                    "decision_id": decision.id,
                    "recommended_action": (
                        decision.recommended_action
                    ),
                    "final_action": production_action,
                    "policy_result": (
                        decision.policy_result
                    ),
                    "decision_status": (
                        decision.status
                    ),
                    "recovery_probability": (
                        decision.recovery_probability
                    ),
                    "expected_recovery_rupees": (
                        decision
                        .expected_recovery_rupees
                    ),
                    "estimated_action_cost_rupees": (
                        decision
                        .estimated_action_cost_rupees
                    ),
                    "expected_net_value_rupees": (
                        decision
                        .expected_net_value_rupees
                    ),
                    "reason_codes": (
                        decision.reason_codes
                    ),
                    "model_source": (
                        decision.model_source
                    ),
                    "scheduled_for": (
                        decision.scheduled_for
                    ),
                },
            )
        )

        if decision.scheduled_for is not None:
            events.append(
                build_event(
                    event_id=(
                        f"decision:{decision.id}:scheduled"
                    ),
                    event_type="action_scheduled",
                    title="Recovery action scheduled",
                    description=(
                        f"{get_value(production_action)} "
                        "was scheduled for execution."
                    ),
                    source="rules_engine",
                    status="scheduled",
                    occurred_at=decision.created_at,
                    details={
                        "decision_id": decision.id,
                        "action": production_action,
                        "scheduled_for": (
                            decision.scheduled_for
                        ),
                    },
                )
            )

        if decision.executed_at is not None:
            events.append(
                build_event(
                    event_id=(
                        f"decision:{decision.id}:executed"
                    ),
                    event_type="action_executed",
                    title="Recovery action executed",
                    description=(
                        f"Executed "
                        f"{get_value(production_action)}."
                    ),
                    source="action_worker",
                    status="executed",
                    occurred_at=decision.executed_at,
                    details={
                        "decision_id": decision.id,
                        "action": production_action,
                        "current_decision_status": (
                            decision.status
                        ),
                    },
                )
            )

    for shadow_decision in ml_shadow_decisions:
        events.append(
            build_event(
                event_id=(
                    f"ml-shadow:{shadow_decision.id}"
                ),
                event_type="ml_shadow_decision",
                title="CatBoost shadow evaluation",
                description=(
                    "CatBoost ranked the policy-allowed "
                    "recovery actions."
                ),
                source="catboost",
                status=shadow_decision.status,
                occurred_at=shadow_decision.created_at,
                details={
                    "shadow_decision_id": (
                        shadow_decision.id
                    ),
                    "selected_action": (
                        shadow_decision.selected_action
                    ),
                    "calibrated_probability": (
                        shadow_decision
                        .calibrated_probability
                    ),
                    "expected_net_value_rupees": (
                        shadow_decision
                        .expected_net_value_rupees
                    ),
                    "agrees_with_production": (
                        shadow_decision
                        .agrees_with_production
                    ),
                    "latency_ms": (
                        shadow_decision.latency_ms
                    ),
                    "model_version": (
                        shadow_decision.model_version
                    ),
                },
            )
        )

    for shadow_decision in ai_shadow_decisions:
        events.append(
            build_event(
                event_id=(
                    f"ai-shadow:{shadow_decision.id}"
                ),
                event_type="ai_shadow_decision",
                title="Ollama shadow evaluation",
                description=(
                    "The LLM generated an independent "
                    "recovery recommendation."
                ),
                source="ollama",
                status=shadow_decision.status,
                occurred_at=shadow_decision.created_at,
                details={
                    "shadow_decision_id": (
                        shadow_decision.id
                    ),
                    "recommended_action": (
                        shadow_decision
                        .recommended_action
                    ),
                    "recovery_probability": (
                        shadow_decision
                        .recovery_probability
                    ),
                    "agrees_with_production": (
                        shadow_decision
                        .agrees_with_production
                    ),
                    "reason_codes": (
                        shadow_decision.reason_codes
                    ),
                    "latency_ms": (
                        shadow_decision.latency_ms
                    ),
                    "model_name": (
                        shadow_decision.model_name
                    ),
                },
            )
        )

    if recovery_case.recovered_at is not None:
        events.append(
            build_event(
                event_id=(
                    f"case:{recovery_case.id}:recovered"
                ),
                event_type="payment_recovered",
                title="Revenue recovered",
                description=(
                    "The payment provider confirmed "
                    "successful payment capture."
                ),
                source="razorpay",
                status="recovered",
                occurred_at=recovery_case.recovered_at,
                details={
                    "recovered_amount_rupees": (
                        recovery_case
                        .recovered_amount_rupees
                    ),
                    "intervention_cost_rupees": (
                        recovery_case
                        .intervention_cost_rupees
                    ),
                },
            )
        )

    if recovery_case.closed_at is not None:
        events.append(
            build_event(
                event_id=(
                    f"case:{recovery_case.id}:closed"
                ),
                event_type="case_closed",
                title="Recovery case closed",
                description=(
                    "No additional recovery action "
                    "can be executed for this case."
                ),
                source="recovery_engine",
                status=get_value(
                    recovery_case.current_state
                ) or "closed",
                occurred_at=recovery_case.closed_at,
                details={},
            )
        )

    events.sort(
        key=lambda item: item["occurred_at"]
    )

    return {
        "case_id": recovery_case.id,
        "tenant_id": recovery_case.tenant_id,
        "provider_payment_id": (
            recovery_case.provider_payment_id
        ),
        "current_state": get_value(
            recovery_case.current_state
        ) or "unknown",
        "total_events": len(events),
        "events": events,
    }