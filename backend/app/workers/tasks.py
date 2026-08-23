from uuid import UUID

from app.db.session import SessionLocal
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

    print(
        f"Payment event processing result: {result}"
    )

    return result