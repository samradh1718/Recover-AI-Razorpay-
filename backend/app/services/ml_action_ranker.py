from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.contracts.enums import (
    FailureCategory,
    RecoveryActionType,
)
from app.models.recovery_case import RecoveryCase
from app.services.ml_recovery_predictor import (
    MLRecoveryPredictor,
)


MONEY_PRECISION = Decimal("0.01")
PROBABILITY_PRECISION = Decimal("0.0001")


ACTION_COSTS = {
    RecoveryActionType.RETRY_PAYMENT: Decimal("0.50"),
    RecoveryActionType.SEND_PAYMENT_LINK: Decimal("2.00"),
    RecoveryActionType.REQUEST_PAYMENT_METHOD_UPDATE: (
        Decimal("1.00")
    ),
    RecoveryActionType.REQUEST_CUSTOMER_AUTHORIZATION: (
        Decimal("1.00")
    ),
    RecoveryActionType.HUMAN_REVIEW: Decimal("50.00"),
    RecoveryActionType.STOP_RECOVERY: Decimal("0.00"),
}


FAILURE_ACTIONS = {
    FailureCategory.TEMPORARY_GATEWAY_OR_BANK: [
        RecoveryActionType.RETRY_PAYMENT,
        RecoveryActionType.SEND_PAYMENT_LINK,
        RecoveryActionType.HUMAN_REVIEW,
        RecoveryActionType.STOP_RECOVERY,
    ],
    FailureCategory.INSUFFICIENT_FUNDS: [
        RecoveryActionType.RETRY_PAYMENT,
        RecoveryActionType.SEND_PAYMENT_LINK,
        RecoveryActionType.HUMAN_REVIEW,
        RecoveryActionType.STOP_RECOVERY,
    ],
    FailureCategory.INVALID_OR_EXPIRED_METHOD: [
        RecoveryActionType.REQUEST_PAYMENT_METHOD_UPDATE,
        RecoveryActionType.SEND_PAYMENT_LINK,
        RecoveryActionType.HUMAN_REVIEW,
        RecoveryActionType.STOP_RECOVERY,
    ],
    FailureCategory.MANDATE_OR_AUTHORIZATION: [
        RecoveryActionType.REQUEST_CUSTOMER_AUTHORIZATION,
        RecoveryActionType.SEND_PAYMENT_LINK,
        RecoveryActionType.HUMAN_REVIEW,
        RecoveryActionType.STOP_RECOVERY,
    ],
    FailureCategory.UNKNOWN: [
        RecoveryActionType.HUMAN_REVIEW,
        RecoveryActionType.STOP_RECOVERY,
    ],
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Decimal) -> Decimal:
    return value.quantize(
        MONEY_PRECISION,
        rounding=ROUND_HALF_UP,
    )


def get_enum_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)

    return str(value)


def get_allowed_actions(
    recovery_case: RecoveryCase,
) -> list[RecoveryActionType]:
    failure_category = (
        recovery_case.failure_category
        or FailureCategory.UNKNOWN
    )

    actions = list(
        FAILURE_ACTIONS.get(
            failure_category,
            FAILURE_ACTIONS[FailureCategory.UNKNOWN],
        )
    )

    # Stopping rule: do not retry indefinitely.
    if recovery_case.attempt_count >= 3:
        actions = [
            action
            for action in actions
            if action != RecoveryActionType.RETRY_PAYMENT
        ]

    # Communication limit prevents customer harassment.
    if recovery_case.communication_count >= 3:
        customer_communication_actions = {
            RecoveryActionType.SEND_PAYMENT_LINK,
            RecoveryActionType.REQUEST_PAYMENT_METHOD_UPDATE,
            RecoveryActionType.REQUEST_CUSTOMER_AUTHORIZATION,
        }

        actions = [
            action
            for action in actions
            if action not in customer_communication_actions
        ]

    # No new recovery action after the deadline.
    if recovery_case.recovery_deadline_at <= utc_now():
        return [
            RecoveryActionType.HUMAN_REVIEW,
            RecoveryActionType.STOP_RECOVERY,
        ]

    return actions


def build_model_features(
    recovery_case: RecoveryCase,
    action: RecoveryActionType,
) -> dict[str, Any]:
    now = utc_now()

    created_at = recovery_case.created_at

    if created_at.tzinfo is None:
        created_at = created_at.replace(
            tzinfo=timezone.utc
        )

    deadline = recovery_case.recovery_deadline_at

    if deadline.tzinfo is None:
        deadline = deadline.replace(
            tzinfo=timezone.utc
        )

    hours_since_failure = max(
        0.0,
        (now - created_at).total_seconds() / 3600,
    )

    days_to_deadline = max(
        0.0,
        (deadline - now).total_seconds() / 86400,
    )

    amount = Decimal(
        recovery_case.recoverable_amount_rupees
    )

    customer_segment = (
        "high_value"
        if amount >= Decimal("5000.00")
        else "standard"
    )

    # These fields are not stored in RecoveryCase yet.
    # Safe neutral defaults are used for shadow-mode inference.
    payment_method = (
        getattr(
            recovery_case,
            "payment_method",
            None,
        )
        or "unknown"
    )

    return {
        "failure_category": get_enum_value(
            recovery_case.failure_category
            or FailureCategory.UNKNOWN
        ),
        "payment_method": payment_method,
        "recovery_action": action.value,
        "customer_segment": customer_segment,
        "amount_rupees": float(amount),
        "attempt_count": recovery_case.attempt_count,
        "communication_count": (
            recovery_case.communication_count
        ),
        "customer_success_rate": 0.50,
        "customer_tenure_days": 0,
        "previous_failures": (
            recovery_case.attempt_count
        ),
        "previous_recoveries": 0,
        "hours_since_failure": round(
            hours_since_failure,
            4,
        ),
        "days_to_deadline": round(
            days_to_deadline,
            4,
        ),
        "hour_of_day": now.hour,
        "day_of_week": now.weekday(),
        "is_subscription": int(
            recovery_case.provider_subscription_id
            is not None
        ),
    }


def rank_recovery_actions(
    recovery_case: RecoveryCase,
) -> list[dict[str, Any]]:
    predictor = MLRecoveryPredictor()

    recoverable_amount = Decimal(
        recovery_case.recoverable_amount_rupees
    )

    ranked_actions: list[dict[str, Any]] = []

    for action in get_allowed_actions(recovery_case):
        features = build_model_features(
            recovery_case=recovery_case,
            action=action,
        )

        if action == RecoveryActionType.STOP_RECOVERY:
            raw_probability = 0.0
            calibrated_probability = 0.0
        else:
            prediction = (
                predictor.predict_recovery_probability(
                    features
                )
            )

            raw_probability = prediction[
                "raw_probability"
            ]

            calibrated_probability = prediction[
                "calibrated_probability"
            ]

        probability_decimal = Decimal(
            str(calibrated_probability)
        )

        expected_recovery = money(
            recoverable_amount * probability_decimal
        )

        action_cost = ACTION_COSTS[action]

        expected_net_value = money(
            expected_recovery - action_cost
        )

        ranked_actions.append(
            {
                "action": action.value,
                "raw_probability": str(
                    Decimal(str(raw_probability)).quantize(
                        PROBABILITY_PRECISION
                    )
                ),
                "calibrated_probability": str(
                    probability_decimal.quantize(
                        PROBABILITY_PRECISION
                    )
                ),
                "expected_recovery_rupees": str(
                    expected_recovery
                ),
                "estimated_action_cost_rupees": str(
                    action_cost
                ),
                "expected_net_value_rupees": str(
                    expected_net_value
                ),
                "model_features": features,
            }
        )

    ranked_actions.sort(
        key=lambda item: Decimal(
            item["expected_net_value_rupees"]
        ),
        reverse=True,
    )

    for position, action_result in enumerate(
        ranked_actions,
        start=1,
    ):
        action_result["rank"] = position

    return ranked_actions