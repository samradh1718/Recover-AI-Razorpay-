from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_database_session
from app.models.payment_event import PaymentEvent


router = APIRouter(
    prefix="/payment-events",
    tags=["Payment events"],
)


@router.get("")
def list_payment_events(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    database: Session = Depends(get_database_session),
) -> list[dict[str, Any]]:
    events = database.execute(
        select(PaymentEvent)
        .order_by(PaymentEvent.received_at.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    return [
        {
            "id": str(event.id),
            "tenant_id": str(event.tenant_id),
            "provider_event_id": event.provider_event_id,
            "event_type": event.event_type,
            "provider_payment_id": event.provider_payment_id,
            "provider_subscription_id": getattr(
                event,
                "provider_subscription_id",
                None,
            ),
            "processing_status": event.processing_status,
            "processing_error": event.processing_error,
            "received_at": event.received_at,
            "processed_at": event.processed_at,
        }
        for event in events
    ]
