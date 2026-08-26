from typing import Any
from uuid import UUID

from app.contracts.enums import (
    RecoveryDecisionStatus,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.action_executor import (
    execute_recovery_action,
)
from app.services.ai_shadow_runner import (
    run_ai_shadow_decision,
)
from app.services.decision_engine import (
    evaluate_recovery_case,
)
from app.services.ml_shadow_runner import (
    run_ml_shadow_decision,
)
from app.services.payment_event_processor import (
    process_payment_event,
)
from app.services.payment_link_reconciliation_service import (
    reconcile_payment_link,
)
from app.services.razorpay_payment_link_service import (
    RazorpayProviderError,
)
from app.workers.celery_app import celery_app


@celery_app.task(
    name="recoverai.process_payment_event",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={
        "max_retries": 3,
    },
)
def process_payment_event_task(
    event_id: str,
) -> dict[str, Any]:
    with SessionLocal() as database:
        result = process_payment_event(
            database=database,
            event_id=UUID(event_id),
        )

        case_id = result.get("case_id")

        should_evaluate = (
            result.pop(
                "should_evaluate",
                "false",
            )
            == "true"
        )

        if (
            case_id is not None
            and should_evaluate
        ):
            decision = evaluate_recovery_case(
                database=database,
                case_id=UUID(case_id),
            )

            result["decision_id"] = str(
                decision.id
            )

            result["decision_status"] = (
                decision.status.value
            )

            result["policy_result"] = (
                decision.policy_result.value
            )

            if decision.final_action is not None:
                result["final_action"] = (
                    decision.final_action.value
                )

            # Ollama/LLM shadow evaluation.
            if settings.ai_shadow_mode_enabled:
                generate_ai_shadow_decision_task.apply_async(
                    args=[
                        str(decision.id)
                    ],
                    queue="ai_shadow",
                )

                result[
                    "ai_shadow_queued"
                ] = "true"

            # CatBoost ML shadow evaluation.
            generate_ml_shadow_decision_task.apply_async(
                args=[
                    str(decision.id)
                ],
                queue="ml_shadow",
            )

            result[
                "ml_shadow_queued"
            ] = "true"

            # Only an approved production decision
            # can execute a recovery action.
            if (
                decision.status
                == RecoveryDecisionStatus.SCHEDULED
            ):
                execute_recovery_action_task.apply_async(
                    args=[
                        str(decision.id)
                    ],
                    eta=decision.scheduled_for,
                )

                result[
                    "action_queued"
                ] = "true"

    print(
        f"Payment event processing result: {result}"
    )

    return result


@celery_app.task(
    name="recoverai.execute_recovery_action",
)
def execute_recovery_action_task(
    decision_id: str,
) -> dict[str, Any]:
    with SessionLocal() as database:
        result = execute_recovery_action(
            database=database,
            decision_id=UUID(decision_id),
        )

    should_reconcile = (
        settings.razorpay_reconciliation_enabled
        and result.get("status") == "executed"
        and result.get("execution_mode")
        == "razorpay_test"
        and bool(
            result.get("provider_action_id")
        )
    )

    if should_reconcile:
        reconcile_payment_link_task.apply_async(
            args=[
                decision_id
            ],
            countdown=(
                settings
                .razorpay_reconciliation_initial_delay_seconds
            ),
        )

        result[
            "reconciliation_queued"
        ] = True

    print(
        f"Recovery action execution result: {result}"
    )

    return result


@celery_app.task(
    bind=True,
    name="recoverai.reconcile_payment_link",
    max_retries=max(
        0,
        settings
        .razorpay_reconciliation_max_attempts
        - 1,
    ),
)
def reconcile_payment_link_task(
    self: Any,
    decision_id: str,
) -> dict[str, Any]:
    maximum_attempts = (
        settings
        .razorpay_reconciliation_max_attempts
    )

    current_attempt = (
        self.request.retries + 1
    )

    try:
        with SessionLocal() as database:
            result = reconcile_payment_link(
                database=database,
                decision_id=UUID(decision_id),
            )

    except RazorpayProviderError as error:
        print(
            "Razorpay reconciliation provider "
            f"error on attempt {current_attempt}/"
            f"{maximum_attempts}: {error}"
        )

        if current_attempt >= maximum_attempts:
            raise

        raise self.retry(
            exc=error,
            countdown=(
                settings
                .razorpay_reconciliation_retry_delay_seconds
            ),
        )

    if result["status"] == "provider_not_paid":
        if current_attempt >= maximum_attempts:
            result["status"] = (
                "reconciliation_exhausted"
            )
            result["attempts"] = (
                current_attempt
            )

            print(
                "Payment Link reconciliation "
                f"exhausted: {result}"
            )

            return result

        print(
            "Payment Link is not paid yet. "
            f"Retrying attempt {current_attempt + 1}/"
            f"{maximum_attempts}"
        )

        raise self.retry(
            countdown=(
                settings
                .razorpay_reconciliation_retry_delay_seconds
            ),
        )

    result["attempts"] = current_attempt

    print(
        f"Payment Link reconciliation result: {result}"
    )

    return result


@celery_app.task(
    name="recoverai.generate_ai_shadow_decision",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={
        "max_retries": 2,
    },
)
def generate_ai_shadow_decision_task(
    production_decision_id: str,
) -> dict[str, Any]:
    with SessionLocal() as database:
        result = run_ai_shadow_decision(
            database=database,
            production_decision_id=UUID(
                production_decision_id
            ),
        )

    print(
        f"AI shadow decision result: {result}"
    )

    return result


@celery_app.task(
    name="recoverai.generate_ml_shadow_decision",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={
        "max_retries": 2,
    },
)
def generate_ml_shadow_decision_task(
    production_decision_id: str,
) -> dict[str, Any]:
    with SessionLocal() as database:
        result = run_ml_shadow_decision(
            database=database,
            production_decision_id=UUID(
                production_decision_id
            ),
        )

    print(
        f"ML shadow decision result: {result}"
    )

    return result