from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
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

    production_decisions = database.scalars(
        select(RecoveryDecision)
        .where(
            RecoveryDecision.tenant_id == tenant_id,
            RecoveryDecision.recovery_case_id
            == recovery_case.id,
        )
        .order_by(RecoveryDecision.created_at.asc())
    ).all()

    payment_event_conditions = [
        PaymentEvent.provider_payment_id
        == recovery_case.provider_payment_id,
    ]

    # A Payment Link payment creates a new Razorpay payment ID.
    # Match those webhooks using the provider Payment Link ID.
    for decision in production_decisions:
        if decision.provider_action_id is None:
            continue

        payment_event_conditions.append(
            PaymentEvent.payload.contains(
                {
                    "payload": {
                        "payment_link": {
                            "entity": {
                                "id": (
                                    decision.provider_action_id
                                )
                            }
                        }
                    }
                }
            )
        )

    payment_events = database.scalars(
        select(PaymentEvent)
        .where(
            PaymentEvent.tenant_id == tenant_id,
            or_(*payment_event_conditions),
        )
        .order_by(PaymentEvent.received_at.asc())
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
                    "event_type": payment_event.event_type,
                    "provider_payment_id": (
                        payment_event.provider_payment_id
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
                    status=payment_event.processing_status,
                    occurred_at=payment_event.processed_at,
                    details={
                        "payment_event_id": (
                            payment_event.id
                        ),
                        "event_type": (
                            payment_event.event_type
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
                    recovery_case.recoverable_amount_rupees
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
                    "decision_status": decision.status,
                    "recovery_probability": (
                        decision.recovery_probability
                    ),
                    "expected_recovery_rupees": (
                        decision.expected_recovery_rupees
                    ),
                    "estimated_action_cost_rupees": (
                        decision
                        .estimated_action_cost_rupees
                    ),
                    "expected_net_value_rupees": (
                        decision.expected_net_value_rupees
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
                        "decision_status": (
                            decision.status
                        ),
                        "execution_mode": (
                            decision.execution_mode
                        ),
                        "simulated": (
                            decision.execution_mode
                            == "simulated"
                        ),
                    },
                )
            )

        if decision.provider_action_id is not None:
            provider_created_at = (
                decision.executed_at
                or decision.updated_at
                or decision.created_at
            )

            events.append(
                build_event(
                    event_id=(
                        f"decision:{decision.id}:"
                        "provider-action-created"
                    ),
                    event_type="provider_action_created",
                    title="Razorpay Payment Link created",
                    description=(
                        "Razorpay Test Mode created a "
                        "Payment Link for the approved "
                        "recovery action."
                    ),
                    source="razorpay",
                    status="created",
                    occurred_at=provider_created_at,
                    details={
                        "decision_id": decision.id,
                        "execution_mode": (
                            decision.execution_mode
                        ),
                        "provider_action_id": (
                            decision.provider_action_id
                        ),
                        "provider_reference_id": (
                            decision.provider_reference_id
                        ),
                        "provider_action_url": (
                            decision.provider_action_url
                        ),
                        "current_provider_status": (
                            decision.provider_action_status
                        ),
                    },
                )
            )
            provider_response = (
                decision.provider_response
            )

            notification_details: (
                dict[str, Any] | None
            ) = None

            if isinstance(
                provider_response,
                dict,
            ):
                stored_notification = (
                    provider_response.get(
                        "recoverai_notification"
                    )
                )

                if isinstance(
                    stored_notification,
                    dict,
                ):
                    notification_details = (
                        stored_notification
                    )

            if (
                notification_details is not None
                and notification_details.get(
                    "requested"
                )
                is True
            ):
                notification_channel = (
                    notification_details.get(
                        "channel"
                    )
                )

                if not isinstance(
                    notification_channel,
                    str,
                ):
                    notification_channel = (
                        "unknown"
                    )

                notification_status = (
                    notification_details.get(
                        "status"
                    )
                )

                if not isinstance(
                    notification_status,
                    str,
                ):
                    notification_status = (
                        "request_accepted"
                    )

                events.append(
                    build_event(
                        event_id=(
                            f"decision:{decision.id}:"
                            "customer-notification-requested"
                        ),
                        event_type=(
                            "customer_notification_requested"
                        ),
                        title=(
                            f"Customer "
                            f"{notification_channel} "
                            "notification requested"
                        ),
                        description=(
                            "Razorpay accepted the request "
                            "to send the recovery Payment "
                            f"Link by {notification_channel}."
                        ),
                        source="razorpay",
                        status=notification_status,
                        occurred_at=provider_created_at,
                        details={
                            "decision_id": decision.id,
                            "provider_action_id": (
                                decision
                                .provider_action_id
                            ),
                            "notification_channel": (
                                notification_channel
                            ),
                            "notification_status": (
                                notification_status
                            ),
                            # Razorpay request acceptance
                            # does not prove inbox/device
                            # delivery.
                            "delivery_confirmed": False,
                        },
                    )
                )

        if (
            decision.provider_action_status == "paid"
            and recovery_case.recovered_at is not None
        ):
            events.append(
                build_event(
                    event_id=(
                        f"decision:{decision.id}:"
                        "provider-payment-confirmed"
                    ),
                    event_type=(
                        "provider_payment_confirmed"
                    ),
                    title="Razorpay payment confirmed",
                    description=(
                        "Razorpay confirmed that the "
                        "recovery Payment Link was paid."
                    ),
                    source="razorpay",
                    status="paid",
                    occurred_at=recovery_case.recovered_at,
                    details={
                        "decision_id": decision.id,
                        "provider_action_id": (
                            decision.provider_action_id
                        ),
                        "provider_reference_id": (
                            decision.provider_reference_id
                        ),
                        "provider_action_status": (
                            decision.provider_action_status
                        ),
                        "execution_mode": (
                            decision.execution_mode
                        ),
                        "confirmed_amount_rupees": (
                            recovery_case
                            .recovered_amount_rupees
                        ),
                        "currency": recovery_case.currency,
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
        recovered_amount = Decimal(
            str(recovery_case.recovered_amount_rupees)
        )

        intervention_cost = Decimal(
            str(recovery_case.intervention_cost_rupees)
        )

        net_recovered = (
            recovered_amount - intervention_cost
        ).quantize(Decimal("0.01"))

        events.append(
            build_event(
                event_id=(
                    f"case:{recovery_case.id}:recovered"
                ),
                event_type="payment_recovered",
                title="Revenue recovered",
                description=(
                    "RecoverAI verified the provider "
                    "payment and recorded the recovered "
                    "revenue."
                ),
                source="recovery_engine",
                status="recovered",
                occurred_at=recovery_case.recovered_at,
                details={
                    "recoverable_amount_rupees": (
                        recovery_case
                        .recoverable_amount_rupees
                    ),
                    "recovered_amount_rupees": (
                        recovery_case
                        .recovered_amount_rupees
                    ),
                    "intervention_cost_rupees": (
                        recovery_case
                        .intervention_cost_rupees
                    ),
                    "net_recovered_rupees": (
                        net_recovered
                    ),
                    "currency": recovery_case.currency,
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
                status=(
                    get_value(recovery_case.current_state)
                    or "closed"
                ),
                occurred_at=recovery_case.closed_at,
                details={
                    "final_state": (
                        recovery_case.current_state
                    ),
                    "recovered_amount_rupees": (
                        recovery_case
                        .recovered_amount_rupees
                    ),
                },
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
        "current_state": (
            get_value(recovery_case.current_state)
            or "unknown"
        ),
        "total_events": len(events),
        "events": events,
    }