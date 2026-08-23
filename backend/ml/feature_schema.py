CATEGORICAL_FEATURES = [
    "failure_category",
    "payment_method",
    "recovery_action",
    "customer_segment",
]

NUMERIC_FEATURES = [
    "amount_rupees",
    "attempt_count",
    "communication_count",
    "customer_success_rate",
    "customer_tenure_days",
    "previous_failures",
    "previous_recoveries",
    "hours_since_failure",
    "days_to_deadline",
    "hour_of_day",
    "day_of_week",
    "is_subscription",
]

MODEL_FEATURES = (
    CATEGORICAL_FEATURES + NUMERIC_FEATURES
)

TARGET_COLUMN = "recovered"

IDENTIFIER_COLUMNS = [
    "case_id",
    "customer_id",
    "event_timestamp",
    "data_source",
    "generator_version",
]

OUTCOME_COLUMNS = [
    "recovered_amount_rupees",
    "action_cost_rupees",
    "net_recovered_rupees",
    "time_to_recovery_hours",
]