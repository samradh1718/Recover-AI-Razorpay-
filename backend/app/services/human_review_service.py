from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.enums import (
    HumanReviewOutcome,
    PolicyResult,
    RecoveryActionType,
    RecoveryCaseState,
    RecoveryDecisionStatus,
)
from app.contracts.human_reviews import (
    HumanReviewResolutionRequest,
)
from app.models import (
    HumanReviewResolution,
    RecoveryCase,
    RecoveryDecision,
)
from app.services.decision_engine import (
    CUSTOMER_ACTIONS,
    ActionOption,
    _calculate_action_schedule,
    _case_state,
    _decision_status,
    _money,
    _option_payload,
    _options_for_failure,
)


TERMINAL_CASE_STATES = {
    RecoveryCaseState.RECOVERED,
    RecoveryCaseState.EXHAUSTED,
    RecoveryCaseState.STOPPED,
    RecoveryCaseState.EXPIRED,
}


class HumanReviewError(Exception):
    """Base exception for Human Review operations."""


class HumanReviewCaseNotFoundError(
    HumanReviewError
):
    """Raised when the requested case does not exist."""


class HumanReviewDecisionNotFoundError(
    HumanReviewError
):
    """Raised when the source decision does not exist."""


class HumanReviewTenantMismatchError(
    HumanReviewError
):
    """Raised when the case belongs to another tenant."""


class HumanReviewNotPendingError(
    HumanReviewError
):
    """Raised when the case is not awaiting review."""


class HumanReviewVersionConflictError(
    HumanReviewError
):
    """Raised when the submitted case version is stale."""


class HumanReviewAlreadyResolvedError(
    HumanReviewError
):
    """Raised when a different review already resolved it."""


class HumanReviewActionNotAllowedError(
    HumanReviewError
):
    """Raised when the selected action is unsafe."""


@dataclass(frozen=True)
class HumanReviewServiceResult:
    review: HumanReviewResolution
    decision: RecoveryDecision
    recovery_case: RecoveryCase
    should_queue_action: bool
    reused_existing_resolution: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _stop_option() -> ActionOption:
    return ActionOption(
        action=RecoveryActionType.STOP_RECOVERY,
        probability=Decimal("0.0000"),
        cost_rupees=Decimal("0.00"),
        delay_minutes=None,
        reason_code="human_review_stop_recovery",
        explanation=(
            "A human reviewer rejected further recovery "
            "action and closed the case."
        ),
    )


def _selected_action_for_request(
    request: HumanReviewResolutionRequest,
) -> RecoveryActionType:
    if (
        request.outcome
        == HumanReviewOutcome.REJECTED
    ):
        return RecoveryActionType.STOP_RECOVERY

    if request.selected_action is None:
        raise HumanReviewActionNotAllowedError(
            "An approved review requires an action"
        )

    return request.selected_action


def _find_approved_option(
    *,
    recovery_case: RecoveryCase,
    selected_action: RecoveryActionType,
) -> tuple[
    ActionOption,
    list[ActionOption],
]:
    options = _options_for_failure(
        recovery_case.failure_category
    )

    selected_option = next(
        (
            option
            for option in options
            if option.action == selected_action
        ),
        None,
    )

    if selected_option is None:
        category = (
            recovery_case.failure_category.value
            if recovery_case.failure_category
            is not None
            else "unknown"
        )

        raise HumanReviewActionNotAllowedError(
            f"Action {selected_action.value} is not "
            f"allowed for failure category {category}"
        )

    if (
        selected_option.action
        in {
            RecoveryActionType.HUMAN_REVIEW,
            RecoveryActionType.STOP_RECOVERY,
        }
    ):
        raise HumanReviewActionNotAllowedError(
            "The selected action cannot be executed"
        )

    if (
        selected_option.action
        == RecoveryActionType.RETRY_PAYMENT
        and recovery_case.attempt_count >= 3
    ):
        raise HumanReviewActionNotAllowedError(
            "The maximum payment-attempt limit "
            "has been reached"
        )

    if (
        selected_option.action in CUSTOMER_ACTIONS
        and recovery_case.communication_count >= 3
    ):
        raise HumanReviewActionNotAllowedError(
            "The customer-contact limit has been reached"
        )

    return selected_option, options


def _validate_existing_resolution(
    *,
    existing_review: HumanReviewResolution,
    request: HumanReviewResolutionRequest,
    selected_action: RecoveryActionType,
) -> None:
    matches_existing = (
        existing_review.tenant_id
        == request.tenant_id
        and existing_review.outcome
        == request.outcome
        and existing_review.selected_action
        == selected_action
        and existing_review.reviewer_id
        == request.reviewer_id
        and existing_review.reviewer_name
        == request.reviewer_name
        and existing_review.reason
        == request.reason
        and existing_review
        .case_state_version_before
        == request.expected_state_version
    )

    if not matches_existing:
        raise HumanReviewAlreadyResolvedError(
            "This Human Review was already resolved "
            "with different review details"
        )


def _reason_codes(
    *,
    source_decision: RecoveryDecision,
    outcome: HumanReviewOutcome,
    selected_option: ActionOption,
) -> list[str]:
    values = [
        *source_decision.reason_codes,
        (
            "human_review_approved"
            if outcome
            == HumanReviewOutcome.APPROVED
            else "human_review_rejected"
        ),
        (
            "human_selected_"
            f"{selected_option.action.value}"
        ),
        selected_option.reason_code,
    ]

    return list(dict.fromkeys(values))


def _load_resulting_decision(
    *,
    database: Session,
    review: HumanReviewResolution,
) -> RecoveryDecision:
    decision = database.get(
        RecoveryDecision,
        review.resulting_decision_id,
    )

    if decision is None:
        raise HumanReviewDecisionNotFoundError(
            "The resulting Human Review decision "
            "was not found"
        )

    return decision


def resolve_human_review(
    *,
    database: Session,
    case_id: UUID,
    request: HumanReviewResolutionRequest,
) -> HumanReviewServiceResult:
    recovery_case = database.execute(
        select(RecoveryCase)
        .where(
            RecoveryCase.id == case_id
        )
        .with_for_update()
    ).scalar_one_or_none()

    if recovery_case is None:
        raise HumanReviewCaseNotFoundError(
            "Recovery case was not found"
        )

    if (
        recovery_case.tenant_id
        != request.tenant_id
    ):
        raise HumanReviewTenantMismatchError(
            "Recovery case does not belong "
            "to the requested tenant"
        )

    source_decision = database.execute(
        select(RecoveryDecision)
        .where(
            RecoveryDecision.id
            == request.source_decision_id
        )
        .with_for_update()
    ).scalar_one_or_none()

    if source_decision is None:
        raise HumanReviewDecisionNotFoundError(
            "Source recovery decision was not found"
        )

    if (
        source_decision.recovery_case_id
        != recovery_case.id
        or source_decision.tenant_id
        != recovery_case.tenant_id
    ):
        raise HumanReviewDecisionNotFoundError(
            "Source decision does not belong "
            "to this recovery case"
        )

    selected_action = (
        _selected_action_for_request(request)
    )

    existing_review = database.execute(
        select(HumanReviewResolution)
        .where(
            HumanReviewResolution
            .source_decision_id
            == source_decision.id
        )
        .with_for_update()
    ).scalar_one_or_none()

    if existing_review is not None:
        _validate_existing_resolution(
            existing_review=existing_review,
            request=request,
            selected_action=selected_action,
        )

        resulting_decision = (
            _load_resulting_decision(
                database=database,
                review=existing_review,
            )
        )

        return HumanReviewServiceResult(
            review=existing_review,
            decision=resulting_decision,
            recovery_case=recovery_case,
            should_queue_action=(
                resulting_decision.status
                == RecoveryDecisionStatus.SCHEDULED
            ),
            reused_existing_resolution=True,
        )

    if (
        recovery_case.current_state
        in TERMINAL_CASE_STATES
    ):
        raise HumanReviewNotPendingError(
            "A terminal recovery case cannot "
            "be reviewed"
        )

    if (
        recovery_case.current_state
        != RecoveryCaseState.HUMAN_REVIEW
    ):
        raise HumanReviewNotPendingError(
            "Recovery case is not awaiting "
            "Human Review"
        )

    if (
        recovery_case.state_version
        != request.expected_state_version
    ):
        raise HumanReviewVersionConflictError(
            "Recovery case version changed; "
            "refresh before reviewing"
        )

    if (
        source_decision.status
        != RecoveryDecisionStatus.PROPOSED
        or source_decision.final_action
        != RecoveryActionType.HUMAN_REVIEW
        or source_decision.policy_result
        != PolicyResult.ESCALATED
    ):
        raise HumanReviewNotPendingError(
            "Source decision is not a pending "
            "Human Review decision"
        )

    if (
        source_decision.case_state_version + 1
        != recovery_case.state_version
    ):
        raise HumanReviewVersionConflictError(
            "Source decision is not the current "
            "Human Review decision"
        )

    existing_version_decision = database.execute(
        select(RecoveryDecision)
        .where(
            RecoveryDecision.recovery_case_id
            == recovery_case.id,
            RecoveryDecision.case_state_version
            == recovery_case.state_version,
        )
    ).scalar_one_or_none()

    if existing_version_decision is not None:
        raise HumanReviewVersionConflictError(
            "A decision already exists for the "
            "current case version"
        )

    now = utc_now()

    if (
        request.outcome
        == HumanReviewOutcome.APPROVED
        and as_utc(
            recovery_case.recovery_deadline_at
        )
        <= now
    ):
        raise HumanReviewActionNotAllowedError(
            "Recovery deadline has expired"
        )

    amount = _money(
        recovery_case.recoverable_amount_rupees
    )

    if (
        request.outcome
        == HumanReviewOutcome.APPROVED
        and amount <= Decimal("0.00")
    ):
        raise HumanReviewActionNotAllowedError(
            "No recoverable amount remains"
        )

    if (
        request.outcome
        == HumanReviewOutcome.REJECTED
    ):
        selected_option = _stop_option()
        available_options = (
            _options_for_failure(
                recovery_case.failure_category
            )
        )
    else:
        (
            selected_option,
            available_options,
        ) = _find_approved_option(
            recovery_case=recovery_case,
            selected_action=selected_action,
        )

    (
        scheduled_for,
        effective_delay_seconds,
        schedule_mode,
    ) = _calculate_action_schedule(
        now=now,
        policy_delay_minutes=(
            selected_option.delay_minutes
        ),
    )

    policy_result = (
        PolicyResult.MODIFIED
        if request.outcome
        == HumanReviewOutcome.APPROVED
        else PolicyResult.REJECTED
    )

    resulting_decision = RecoveryDecision(
        tenant_id=recovery_case.tenant_id,
        recovery_case_id=recovery_case.id,
        case_state_version=(
            recovery_case.state_version
        ),
        recommended_action=(
            source_decision.recommended_action
        ),
        final_action=selected_option.action,
        policy_result=policy_result,
        status=_decision_status(
            selected_option.action
        ),
        recovery_probability=(
            selected_option.probability
        ),
        expected_recovery_rupees=(
            selected_option.expected_recovery(
                amount
            )
        ),
        estimated_action_cost_rupees=(
            selected_option.cost_rupees
        ),
        expected_net_value_rupees=(
            selected_option.expected_net_value(
                amount
            )
        ),
        explanation=(
            "Human Review "
            f"{request.outcome.value}: "
            f"{selected_option.explanation}"
        ),
        reason_codes=_reason_codes(
            source_decision=source_decision,
            outcome=request.outcome,
            selected_option=selected_option,
        ),
        decision_inputs={
            "failure_category": (
                recovery_case
                .failure_category
                .value
                if recovery_case
                .failure_category
                is not None
                else "unknown"
            ),
            "recoverable_amount_rupees": str(
                amount
            ),
            "attempt_count": (
                recovery_case.attempt_count
            ),
            "communication_count": (
                recovery_case
                .communication_count
            ),
            "source_decision_id": str(
                source_decision.id
            ),
            "human_review_outcome": (
                request.outcome.value
            ),
            "human_selected_action": (
                selected_option.action.value
            ),
            "reviewer_id": request.reviewer_id,
            "selected_option": (
                _option_payload(
                    selected_option,
                    amount,
                )
            ),
            "policy_delay_minutes": (
                selected_option.delay_minutes
            ),
            "effective_delay_seconds": (
                effective_delay_seconds
            ),
            "schedule_mode": schedule_mode,
        },
        alternatives=[
            _option_payload(
                option,
                amount,
            )
            for option in available_options
            if (
                option.action
                not in {
                    selected_option.action,
                    RecoveryActionType.HUMAN_REVIEW,
                }
            )
        ],
        model_source="human_review_v1",
        scheduled_for=scheduled_for,
    )

    version_before = recovery_case.state_version
    version_after = version_before + 1

    recovery_case.current_state = _case_state(
        selected_option.action,
        deadline_expired=False,
    )

    recovery_case.state_version = version_after

    recovery_case.next_action_at = scheduled_for
    recovery_case.updated_at = now

    if (
        selected_option.action
        == RecoveryActionType.STOP_RECOVERY
    ):
        recovery_case.closed_at = now
    else:
        recovery_case.closed_at = None

    database.add(resulting_decision)
    database.flush()

    review = HumanReviewResolution(
        tenant_id=recovery_case.tenant_id,
        recovery_case_id=recovery_case.id,
        source_decision_id=source_decision.id,
        resulting_decision_id=(
            resulting_decision.id
        ),
        case_state_version_before=(
            version_before
        ),
        case_state_version_after=(
            version_after
        ),
        outcome=request.outcome,
        selected_action=(
            selected_option.action
        ),
        reviewer_id=request.reviewer_id,
        reviewer_name=request.reviewer_name,
        reason=request.reason,
        created_at=now,
    )

    database.add(review)
    database.commit()

    database.refresh(review)
    database.refresh(resulting_decision)
    database.refresh(recovery_case)

    return HumanReviewServiceResult(
        review=review,
        decision=resulting_decision,
        recovery_case=recovery_case,
        should_queue_action=(
            resulting_decision.status
            == RecoveryDecisionStatus.SCHEDULED
        ),
        reused_existing_resolution=False,
    )


def list_case_human_reviews(
    *,
    database: Session,
    case_id: UUID,
    tenant_id: UUID,
) -> list[HumanReviewResolution]:
    recovery_case = database.get(
        RecoveryCase,
        case_id,
    )

    if recovery_case is None:
        raise HumanReviewCaseNotFoundError(
            "Recovery case was not found"
        )

    if recovery_case.tenant_id != tenant_id:
        raise HumanReviewTenantMismatchError(
            "Recovery case does not belong "
            "to the requested tenant"
        )

    return list(
        database.scalars(
            select(HumanReviewResolution)
            .where(
                HumanReviewResolution
                .recovery_case_id
                == case_id,
                HumanReviewResolution.tenant_id
                == tenant_id,
            )
            .order_by(
                HumanReviewResolution
                .created_at
                .desc()
            )
        ).all()
    )