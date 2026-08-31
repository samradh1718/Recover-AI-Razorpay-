from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.contracts.enums import (
    RecoveryActionType,
)
from app.models.ai_shadow_decision import (
    AIShadowDecision,
)
from app.models.human_review_resolution import (
    HumanReviewResolution,
)
from app.models.ml_shadow_decision import (
    MLShadowDecision,
)
from app.models.payment_event import PaymentEvent
from app.models.recovery_case import RecoveryCase
from app.models.recovery_decision import (
    RecoveryDecision,
)


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

    if isinstance(value, dict):
        return {
            str(key): json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            json_value(item)
            for item in value
        ]

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


def get_payment_entity(
    payload: Any,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    provider_payload = payload.get("payload")

    if not isinstance(provider_payload, dict):
        return {}

    payment_container = provider_payload.get(
        "payment"
    )

    if not isinstance(payment_container, dict):
        return {}

    payment_entity = payment_container.get(
        "entity"
    )

    if not isinstance(payment_entity, dict):
        return {}

    return payment_entity


def get_payment_notes(
    payment_event: PaymentEvent,
) -> dict[str, Any]:
    payment_entity = get_payment_entity(
        payment_event.payload
    )

    notes = payment_entity.get("notes")

    if not isinstance(notes, dict):
        return {}

    return notes


def is_server_reconciled_event(
    payment_event: PaymentEvent,
) -> bool:
    notes = get_payment_notes(payment_event)

    data_source = str(
        notes.get(
            "recoverai_data_source"
        )
        or ""
    ).lower()

    evidence_source = str(
        notes.get(
            "recoverai_evidence_source"
        )
        or ""
    ).lower()

    provider_event_id = str(
        payment_event.provider_event_id
        or ""
    ).lower()

    return (
        "reconcil" in data_source
        or "server_api" in data_source
        or "razorpay_server_api"
        in evidence_source
        or "reconcil" in provider_event_id
    )


def get_provider_order_id(
    decision: RecoveryDecision,
) -> str | None:
    provider_response = (
        decision.provider_response
    )

    if not isinstance(
        provider_response,
        dict,
    ):
        return None

    order_id = provider_response.get(
        "order_id"
    )

    if not isinstance(order_id, str):
        return None

    cleaned_order_id = order_id.strip()

    return cleaned_order_id or None


def get_notification_details(
    decision: RecoveryDecision,
) -> dict[str, Any] | None:
    provider_response = (
        decision.provider_response
    )

    if not isinstance(
        provider_response,
        dict,
    ):
        return None

    notification_details = (
        provider_response.get(
            "recoverai_notification"
        )
    )

    if not isinstance(
        notification_details,
        dict,
    ):
        return None

    return notification_details


def get_case_audit_timeline(
    database: Session,
    tenant_id: UUID,
    case_id: UUID,
) -> dict[str, Any]:
    recovery_case = database.execute(
        select(RecoveryCase).where(
            RecoveryCase.id == case_id,
            RecoveryCase.tenant_id
            == tenant_id,
        )
    ).scalar_one_or_none()

    if recovery_case is None:
        raise ValueError(
            "Recovery case was not found"
        )

    production_decisions = database.scalars(
        select(RecoveryDecision)
        .where(
            RecoveryDecision.tenant_id
            == tenant_id,
            RecoveryDecision.recovery_case_id
            == recovery_case.id,
        )
        .order_by(
            RecoveryDecision.created_at.asc()
        )
    ).all()

    human_reviews = database.scalars(
        select(HumanReviewResolution)
        .where(
            HumanReviewResolution.tenant_id
            == tenant_id,
            HumanReviewResolution.recovery_case_id
            == recovery_case.id,
        )
        .order_by(
            HumanReviewResolution.created_at.asc()
        )
    ).all()

    payment_event_conditions = []

    if (
        recovery_case.provider_payment_id
        is not None
    ):
        payment_event_conditions.append(
            PaymentEvent.provider_payment_id
            == recovery_case.provider_payment_id
        )

    if (
        recovery_case
        .recovered_provider_payment_id
        is not None
    ):
        payment_event_conditions.append(
            PaymentEvent.provider_payment_id
            == recovery_case
            .recovered_provider_payment_id
        )

    # Payment Link payments have a different Razorpay
    # payment ID. Their webhook can be correlated through
    # the provider Payment Link ID stored on the decision.
    for decision in production_decisions:
        if (
            decision.provider_action_id
            is None
        ):
            continue

        payment_event_conditions.append(
            PaymentEvent.payload.contains(
                {
                    "payload": {
                        "payment_link": {
                            "entity": {
                                "id": (
                                    decision
                                    .provider_action_id
                                )
                            }
                        }
                    }
                }
            )
        )

    if payment_event_conditions:
        payment_events = database.scalars(
            select(PaymentEvent)
            .where(
                PaymentEvent.tenant_id
                == tenant_id,
                or_(
                    *payment_event_conditions
                ),
            )
            .order_by(
                PaymentEvent.received_at.asc()
            )
        ).all()
    else:
        payment_events = []

    ai_shadow_decisions = database.scalars(
        select(AIShadowDecision)
        .where(
            AIShadowDecision.tenant_id
            == tenant_id,
            AIShadowDecision.recovery_case_id
            == recovery_case.id,
        )
        .order_by(
            AIShadowDecision.created_at.asc()
        )
    ).all()

    ml_shadow_decisions = database.scalars(
        select(MLShadowDecision)
        .where(
            MLShadowDecision.tenant_id
            == tenant_id,
            MLShadowDecision.recovery_case_id
            == recovery_case.id,
        )
        .order_by(
            MLShadowDecision.created_at.asc()
        )
    ).all()

    reviews_by_source_decision = {
        review.source_decision_id: review
        for review in human_reviews
    }

    events: list[dict[str, Any]] = []

    for payment_event in payment_events:
        server_reconciled = (
            is_server_reconciled_event(
                payment_event
            )
        )

        payment_notes = get_payment_notes(
            payment_event
        )

        if server_reconciled:
            received_event_type = (
                "provider_evidence_received"
            )

            received_title = (
                "Provider evidence received"
            )

            received_description = (
                "RecoverAI obtained authenticated "
                "payment-failure evidence from the "
                "Razorpay server API."
            )

            received_source = "razorpay_api"
            evidence_source = (
                "razorpay_server_api"
            )
        else:
            received_event_type = (
                "webhook_received"
            )

            received_title = (
                "Payment webhook received"
            )

            received_description = (
                f"Received "
                f"{payment_event.event_type} "
                "from the payment provider."
            )

            received_source = "razorpay"
            evidence_source = (
                "signed_webhook"
            )

        events.append(
            build_event(
                event_id=(
                    f"payment:"
                    f"{payment_event.id}:received"
                ),
                event_type=received_event_type,
                title=received_title,
                description=(
                    received_description
                ),
                source=received_source,
                status="completed",
                occurred_at=(
                    payment_event.received_at
                ),
                details={
                    "payment_event_id": (
                        payment_event.id
                    ),
                    "provider_event_id": (
                        payment_event
                        .provider_event_id
                    ),
                    "event_type": (
                        payment_event.event_type
                    ),
                    "provider_payment_id": (
                        payment_event
                        .provider_payment_id
                    ),
                    "processing_status": (
                        payment_event
                        .processing_status
                    ),
                    "evidence_source": (
                        evidence_source
                    ),
                    "data_source": (
                        payment_notes.get(
                            "recoverai_data_source"
                        )
                    ),
                    "provider_generated": (
                        payment_notes.get(
                            "recoverai_provider_generated"
                        )
                    ),
                    "real_money": (
                        payment_notes.get(
                            "recoverai_real_money"
                        )
                    ),
                    "provider_order_id": (
                        payment_notes.get(
                            "recoverai_provider_order_id"
                        )
                    ),
                },
            )
        )

        if (
            payment_event.processed_at
            is not None
        ):
            if server_reconciled:
                processed_description = (
                    "The provider-confirmed payment "
                    "evidence was processed by the "
                    "recovery pipeline."
                )
            else:
                processed_description = (
                    "The signed payment event was "
                    "validated and processed by the "
                    "recovery pipeline."
                )

            events.append(
                build_event(
                    event_id=(
                        f"payment:"
                        f"{payment_event.id}:processed"
                    ),
                    event_type=(
                        "payment_event_processed"
                    ),
                    title=(
                        "Payment event processed"
                    ),
                    description=(
                        processed_description
                    ),
                    source="worker",
                    status=(
                        payment_event
                        .processing_status
                    ),
                    occurred_at=(
                        payment_event.processed_at
                    ),
                    details={
                        "payment_event_id": (
                            payment_event.id
                        ),
                        "provider_event_id": (
                            payment_event
                            .provider_event_id
                        ),
                        "event_type": (
                            payment_event
                            .event_type
                        ),
                        "provider_payment_id": (
                            payment_event
                            .provider_payment_id
                        ),
                        "processing_error": (
                            payment_event
                            .processing_error
                        ),
                        "evidence_source": (
                            evidence_source
                        ),
                    },
                )
            )

    events.append(
        build_event(
            event_id=(
                f"case:"
                f"{recovery_case.id}:created"
            ),
            event_type="case_created",
            title="Recovery case detected",
            description=(
                "A revenue recovery case was "
                "created from the failed payment."
            ),
            source="recovery_engine",
            status="DETECTED",
            occurred_at=(
                recovery_case.created_at
            ),
            details={
                "failed_provider_payment_id": (
                    recovery_case
                    .provider_payment_id
                ),
                "failure_category": (
                    recovery_case
                    .failure_category
                ),
                "recoverable_amount_rupees": (
                    recovery_case
                    .recoverable_amount_rupees
                ),
                "currency": (
                    recovery_case.currency
                ),
                "recovery_deadline_at": (
                    recovery_case
                    .recovery_deadline_at
                ),
                "state_version": (
                    recovery_case.state_version
                ),
            },
        )
    )

    for decision in production_decisions:
        production_action = (
            decision.final_action
            or decision.recommended_action
        )

        decision_inputs = (
            decision.decision_inputs
        )

        if not isinstance(
            decision_inputs,
            dict,
        ):
            decision_inputs = {}

        policy_delay_minutes = (
            decision_inputs.get(
                "policy_delay_minutes"
            )
        )

        effective_delay_seconds = (
            decision_inputs.get(
                "effective_delay_seconds"
            )
        )

        schedule_mode = (
            decision_inputs.get(
                "schedule_mode"
            )
        )

        if not isinstance(
            schedule_mode,
            str,
        ):
            schedule_mode = (
                "policy_delay"
                if (
                    decision.scheduled_for
                    is not None
                )
                else "not_scheduled"
            )

        is_human_decision = (
            decision.model_source
            == "human_review_v1"
        )

        if is_human_decision:
            decision_event_type = (
                "human_review_decision"
            )

            decision_title = (
                "Human Review decision generated"
            )

            decision_description = (
                "The operator resolution created "
                "an auditable production decision."
            )

            decision_source = (
                "human_reviewer"
            )
        else:
            decision_event_type = (
                "production_decision"
            )

            decision_title = (
                "Production decision generated"
            )

            decision_description = (
                "The bounded rules and policy "
                "engine selected a recovery "
                "action."
            )

            decision_source = "rules_engine"

        events.append(
            build_event(
                event_id=(
                    f"decision:"
                    f"{decision.id}:created"
                ),
                event_type=(
                    decision_event_type
                ),
                title=decision_title,
                description=(
                    decision_description
                ),
                source=decision_source,
                status=(
                    get_value(
                        decision.policy_result
                    )
                    or "pending"
                ),
                occurred_at=(
                    decision.created_at
                ),
                details={
                    "decision_id": (
                        decision.id
                    ),
                    "case_state_version": (
                        decision
                        .case_state_version
                    ),
                    "recommended_action": (
                        decision
                        .recommended_action
                    ),
                    "final_action": (
                        production_action
                    ),
                    "policy_result": (
                        decision.policy_result
                    ),
                    "decision_status": (
                        decision.status
                    ),
                    "recovery_probability": (
                        decision
                        .recovery_probability
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
                    "policy_delay_minutes": (
                        policy_delay_minutes
                    ),
                    "effective_delay_seconds": (
                        effective_delay_seconds
                    ),
                    "schedule_mode": (
                        schedule_mode
                    ),
                    "source_decision_id": (
                        decision_inputs.get(
                            "source_decision_id"
                        )
                    ),
                    "human_review_outcome": (
                        decision_inputs.get(
                            "human_review_outcome"
                        )
                    ),
                    "human_selected_action": (
                        decision_inputs.get(
                            "human_selected_action"
                        )
                    ),
                    "reviewer_id": (
                        decision_inputs.get(
                            "reviewer_id"
                        )
                    ),
                },
            )
        )

        if (
            production_action
            == RecoveryActionType.HUMAN_REVIEW
        ):
            review = (
                reviews_by_source_decision.get(
                    decision.id
                )
            )

            review_status = (
                "resolved"
                if review is not None
                else "awaiting_review"
            )

            events.append(
                build_event(
                    event_id=(
                        f"decision:"
                        f"{decision.id}:"
                        "human-review-requested"
                    ),
                    event_type=(
                        "human_review_requested"
                    ),
                    title=(
                        "Human Review requested"
                    ),
                    description=(
                        "Policy escalation paused "
                        "automatic execution and "
                        "requested an operator decision."
                    ),
                    source="policy_engine",
                    status=review_status,
                    occurred_at=(
                        decision.created_at
                    ),
                    details={
                        "source_decision_id": (
                            decision.id
                        ),
                        "case_state_version": (
                            decision
                            .case_state_version
                        ),
                        "policy_result": (
                            decision.policy_result
                        ),
                        "reason_codes": (
                            decision.reason_codes
                        ),
                        "recommended_action": (
                            decision
                            .recommended_action
                        ),
                        "review_resolved": (
                            review is not None
                        ),
                        "review_id": (
                            review.id
                            if review is not None
                            else None
                        ),
                    },
                )
            )

        if (
            decision.scheduled_for
            is not None
        ):
            if (
                schedule_mode
                == "demo_override"
            ):
                schedule_description = (
                    f"{get_value(production_action)} "
                    "was scheduled using the "
                    "demo execution-time override."
                )
            else:
                schedule_description = (
                    f"{get_value(production_action)} "
                    "was scheduled for execution."
                )

            events.append(
                build_event(
                    event_id=(
                        f"decision:"
                        f"{decision.id}:scheduled"
                    ),
                    event_type=(
                        "action_scheduled"
                    ),
                    title=(
                        "Recovery action scheduled"
                    ),
                    description=(
                        schedule_description
                    ),
                    source=(
                        "human_reviewer"
                        if is_human_decision
                        else "rules_engine"
                    ),
                    status="scheduled",
                    occurred_at=(
                        decision.created_at
                    ),
                    details={
                        "decision_id": (
                            decision.id
                        ),
                        "action": (
                            production_action
                        ),
                        "scheduled_for": (
                            decision.scheduled_for
                        ),
                        "policy_delay_minutes": (
                            policy_delay_minutes
                        ),
                        "effective_delay_seconds": (
                            effective_delay_seconds
                        ),
                        "schedule_mode": (
                            schedule_mode
                        ),
                    },
                )
            )

        if decision.executed_at is not None:
            events.append(
                build_event(
                    event_id=(
                        f"decision:"
                        f"{decision.id}:executed"
                    ),
                    event_type=(
                        "action_executed"
                    ),
                    title=(
                        "Recovery action executed"
                    ),
                    description=(
                        f"Executed "
                        f"{get_value(production_action)}."
                    ),
                    source="action_worker",
                    status="executed",
                    occurred_at=(
                        decision.executed_at
                    ),
                    details={
                        "decision_id": (
                            decision.id
                        ),
                        "action": (
                            production_action
                        ),
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

        if (
            decision.provider_action_id
            is not None
        ):
            provider_created_at = (
                decision.executed_at
                or decision.updated_at
                or decision.created_at
            )

            provider_order_id = (
                get_provider_order_id(
                    decision
                )
            )

            events.append(
                build_event(
                    event_id=(
                        f"decision:"
                        f"{decision.id}:"
                        "provider-action-created"
                    ),
                    event_type=(
                        "provider_action_created"
                    ),
                    title=(
                        "Razorpay Payment Link created"
                    ),
                    description=(
                        "Razorpay Test Mode created "
                        "a Payment Link for the "
                        "approved recovery action."
                    ),
                    source="razorpay",
                    status=(
                        decision
                        .provider_action_status
                        or "created"
                    ),
                    occurred_at=(
                        provider_created_at
                    ),
                    details={
                        "decision_id": (
                            decision.id
                        ),
                        "execution_mode": (
                            decision.execution_mode
                        ),
                        "provider_action_id": (
                            decision
                            .provider_action_id
                        ),
                        "provider_reference_id": (
                            decision
                            .provider_reference_id
                        ),
                        "provider_action_url": (
                            decision
                            .provider_action_url
                        ),
                        "provider_order_id": (
                            provider_order_id
                        ),
                        "current_provider_status": (
                            decision
                            .provider_action_status
                        ),
                    },
                )
            )

            notification_details = (
                get_notification_details(
                    decision
                )
            )

            if (
                notification_details
                is not None
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
                            f"decision:"
                            f"{decision.id}:"
                            "customer-notification-"
                            "requested"
                        ),
                        event_type=(
                            "customer_notification_"
                            "requested"
                        ),
                        title=(
                            f"Customer "
                            f"{notification_channel} "
                            "notification requested"
                        ),
                        description=(
                            "Razorpay accepted the "
                            "request to send the "
                            "recovery Payment Link by "
                            f"{notification_channel}."
                        ),
                        source="razorpay",
                        status=(
                            notification_status
                        ),
                        occurred_at=(
                            provider_created_at
                        ),
                        details={
                            "decision_id": (
                                decision.id
                            ),
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
                            "delivery_confirmed": (
                                False
                            ),
                        },
                    )
                )

        if (
            decision.provider_action_status
            == "paid"
            and recovery_case.recovered_at
            is not None
        ):
            events.append(
                build_event(
                    event_id=(
                        f"decision:"
                        f"{decision.id}:"
                        "provider-payment-confirmed"
                    ),
                    event_type=(
                        "provider_payment_confirmed"
                    ),
                    title=(
                        "Razorpay payment confirmed"
                    ),
                    description=(
                        "Razorpay confirmed that "
                        "the recovery Payment Link "
                        "was paid by a captured "
                        "provider payment."
                    ),
                    source="razorpay",
                    status="paid",
                    occurred_at=(
                        recovery_case.recovered_at
                    ),
                    details={
                        "decision_id": (
                            decision.id
                        ),
                        "provider_action_id": (
                            decision
                            .provider_action_id
                        ),
                        "provider_reference_id": (
                            decision
                            .provider_reference_id
                        ),
                        "provider_order_id": (
                            get_provider_order_id(
                                decision
                            )
                        ),
                        "provider_action_status": (
                            decision
                            .provider_action_status
                        ),
                        "failed_provider_payment_id": (
                            recovery_case
                            .provider_payment_id
                        ),
                        "recovered_provider_payment_id": (
                            recovery_case
                            .recovered_provider_payment_id
                        ),
                        "execution_mode": (
                            decision.execution_mode
                        ),
                        "confirmed_amount_rupees": (
                            recovery_case
                            .recovered_amount_rupees
                        ),
                        "currency": (
                            recovery_case.currency
                        ),
                    },
                )
            )

    for review in human_reviews:
        review_outcome = (
            get_value(review.outcome)
            or "unknown"
        )

        selected_action = (
            get_value(
                review.selected_action
            )
            or "unknown"
        )

        if review_outcome == "approved":
            event_type = (
                "human_review_approved"
            )

            title = (
                "Human Review approved"
            )

            description = (
                "The operator approved "
                f"{selected_action} as the "
                "next recovery action."
            )

            status_value = "approved"
        else:
            event_type = (
                "human_review_rejected"
            )

            title = (
                "Human Review rejected recovery"
            )

            description = (
                "The operator rejected further "
                "automatic recovery and stopped "
                "the case."
            )

            status_value = "rejected"

        events.append(
            build_event(
                event_id=(
                    f"human-review:{review.id}"
                ),
                event_type=event_type,
                title=title,
                description=description,
                source="human_reviewer",
                status=status_value,
                occurred_at=review.created_at,
                details={
                    "review_id": review.id,
                    "source_decision_id": (
                        review.source_decision_id
                    ),
                    "resulting_decision_id": (
                        review
                        .resulting_decision_id
                    ),
                    "outcome": (
                        review.outcome
                    ),
                    "selected_action": (
                        review.selected_action
                    ),
                    "reviewer_id": (
                        review.reviewer_id
                    ),
                    "reviewer_name": (
                        review.reviewer_name
                    ),
                    "reason": review.reason,
                    "case_state_version_before": (
                        review
                        .case_state_version_before
                    ),
                    "case_state_version_after": (
                        review
                        .case_state_version_after
                    ),
                },
            )
        )

    for shadow_decision in (
        ml_shadow_decisions
    ):
        events.append(
            build_event(
                event_id=(
                    f"ml-shadow:"
                    f"{shadow_decision.id}"
                ),
                event_type=(
                    "ml_shadow_decision"
                ),
                title=(
                    "CatBoost shadow evaluation"
                ),
                description=(
                    "CatBoost ranked the "
                    "policy-allowed recovery "
                    "actions."
                ),
                source="catboost",
                status=(
                    shadow_decision.status
                ),
                occurred_at=(
                    shadow_decision.created_at
                ),
                details={
                    "shadow_decision_id": (
                        shadow_decision.id
                    ),
                    "selected_action": (
                        shadow_decision
                        .selected_action
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
                        shadow_decision
                        .model_version
                    ),
                },
            )
        )

    for shadow_decision in (
        ai_shadow_decisions
    ):
        events.append(
            build_event(
                event_id=(
                    f"ai-shadow:"
                    f"{shadow_decision.id}"
                ),
                event_type=(
                    "ai_shadow_decision"
                ),
                title=(
                    "Ollama shadow evaluation"
                ),
                description=(
                    "The LLM generated an "
                    "independent recovery "
                    "recommendation."
                ),
                source="ollama",
                status=(
                    shadow_decision.status
                ),
                occurred_at=(
                    shadow_decision.created_at
                ),
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
                        shadow_decision
                        .reason_codes
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

    if (
        recovery_case.recovered_at
        is not None
    ):
        recovered_amount = Decimal(
            str(
                recovery_case
                .recovered_amount_rupees
            )
        )

        intervention_cost = Decimal(
            str(
                recovery_case
                .intervention_cost_rupees
            )
        )

        net_recovered = (
            recovered_amount
            - intervention_cost
        ).quantize(
            Decimal("0.01")
        )

        events.append(
            build_event(
                event_id=(
                    f"case:"
                    f"{recovery_case.id}:"
                    "recovered"
                ),
                event_type=(
                    "payment_recovered"
                ),
                title="Revenue recovered",
                description=(
                    "RecoverAI verified the "
                    "captured provider payment "
                    "and recorded the recovered "
                    "revenue."
                ),
                source="recovery_engine",
                status="recovered",
                occurred_at=(
                    recovery_case.recovered_at
                ),
                details={
                    "failed_provider_payment_id": (
                        recovery_case
                        .provider_payment_id
                    ),
                    "recovered_provider_payment_id": (
                        recovery_case
                        .recovered_provider_payment_id
                    ),
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
                    "currency": (
                        recovery_case.currency
                    ),
                },
            )
        )

    if recovery_case.closed_at is not None:
        events.append(
            build_event(
                event_id=(
                    f"case:"
                    f"{recovery_case.id}:closed"
                ),
                event_type="case_closed",
                title="Recovery case closed",
                description=(
                    "No additional recovery "
                    "action can be executed for "
                    "this case."
                ),
                source="recovery_engine",
                status=(
                    get_value(
                        recovery_case.current_state
                    )
                    or "closed"
                ),
                occurred_at=(
                    recovery_case.closed_at
                ),
                details={
                    "final_state": (
                        recovery_case
                        .current_state
                    ),
                    "failed_provider_payment_id": (
                        recovery_case
                        .provider_payment_id
                    ),
                    "recovered_provider_payment_id": (
                        recovery_case
                        .recovered_provider_payment_id
                    ),
                    "recovered_amount_rupees": (
                        recovery_case
                        .recovered_amount_rupees
                    ),
                },
            )
        )

    events.sort(
        key=lambda item: (
            item["occurred_at"],
            item["id"],
        )
    )

    return {
        "case_id": recovery_case.id,
        "tenant_id": recovery_case.tenant_id,

        # Backward-compatible field. This is the
        # original failed payment ID.
        "provider_payment_id": (
            recovery_case.provider_payment_id
        ),

        "failed_provider_payment_id": (
            recovery_case.provider_payment_id
        ),
        "recovered_provider_payment_id": (
            recovery_case
            .recovered_provider_payment_id
        ),
        "current_state": (
            get_value(
                recovery_case.current_state
            )
            or "unknown"
        ),
        "total_events": len(events),
        "events": events,
    }