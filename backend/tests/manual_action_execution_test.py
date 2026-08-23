from datetime import datetime, timezone

from sqlalchemy import select

from app.contracts.enums import RecoveryDecisionStatus
from app.db.session import SessionLocal
from app.models import RecoveryDecision
from app.services.action_executor import execute_recovery_action


with SessionLocal() as database:
    now = datetime.now(timezone.utc)

    decision = database.execute(
        select(RecoveryDecision)
        .where(
            RecoveryDecision.status
            == RecoveryDecisionStatus.SCHEDULED,
            RecoveryDecision.scheduled_for <= now,
        )
        .order_by(RecoveryDecision.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()

    if decision is None:
        print("No due scheduled recovery decision was found.")
        print("Create a payment.failed event or wait until its scheduled time.")
    else:
        print("Executing decision:", decision.id)
        print("Case ID:", decision.recovery_case_id)
        print("Action:", decision.final_action.value)

        result = execute_recovery_action(
            database=database,
            decision_id=decision.id,
        )

        print("Result:", result)