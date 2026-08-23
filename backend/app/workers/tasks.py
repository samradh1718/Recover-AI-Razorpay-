from uuid import UUID

from app.db.session import SessionLocal
from app.services.decision_engine import evaluate_recovery_case
from app.services.payment_event_processor import (
    process_payment_event,
)
from app.workers.celery_app import celery_app


@celery_app.task(
    name="recoverai.process_payment_event",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_payment_event_task(
    event_id: str,
) -> dict[str, str]:
    with SessionLocal() as database:
        result = process_payment_event(
            database=database,
            event_id=UUID(event_id),
        )

        case_id = result.get("case_id")
        should_evaluate = (
            result.pop("should_evaluate", "false") == "true"
        )

        if case_id is not None and should_evaluate:
            decision = evaluate_recovery_case(
                database=database,
                case_id=UUID(case_id),
            )

            result["decision_id"] = str(decision.id)
            result["decision_status"] = decision.status.value
            result["policy_result"] = decision.policy_result.value

            if decision.final_action is not None:
                result["final_action"] = (
                    decision.final_action.value
                )

    print(
        f"Payment event processing result: {result}"
    )

    return result
