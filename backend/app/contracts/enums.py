from enum import Enum


class RecoveryActionType(str, Enum):
    RETRY_PAYMENT = "retry_payment"
    SEND_PAYMENT_LINK = "send_payment_link"
    REQUEST_PAYMENT_METHOD_UPDATE = (
        "request_payment_method_update"
    )
    REQUEST_CUSTOMER_AUTHORIZATION = (
        "request_customer_authorization"
    )
    HUMAN_REVIEW = "human_review"
    STOP_RECOVERY = "stop_recovery"


class PolicyResult(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class RecoveryDecisionStatus(str, Enum):
    PROPOSED = "proposed"
    SCHEDULED = "scheduled"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class HumanReviewOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class FailureCategory(str, Enum):
    TEMPORARY_GATEWAY_OR_BANK = (
        "temporary_gateway_or_bank"
    )
    INSUFFICIENT_FUNDS = "insufficient_funds"
    INVALID_OR_EXPIRED_METHOD = (
        "invalid_or_expired_method"
    )
    MANDATE_OR_AUTHORIZATION = (
        "mandate_or_authorization"
    )
    UNKNOWN = "unknown"


class RecoveryCaseState(str, Enum):
    DETECTED = "DETECTED"
    DIAGNOSED = "DIAGNOSED"
    EVALUATING = "EVALUATING"
    READY = "READY"
    SCHEDULED = "SCHEDULED"
    EXECUTING = "EXECUTING"
    WAITING_FOR_RETRY = "WAITING_FOR_RETRY"
    WAITING_FOR_CUSTOMER = "WAITING_FOR_CUSTOMER"
    HUMAN_REVIEW = "HUMAN_REVIEW"

    RECOVERED = "RECOVERED"
    EXHAUSTED = "EXHAUSTED"
    STOPPED = "STOPPED"
    EXPIRED = "EXPIRED"