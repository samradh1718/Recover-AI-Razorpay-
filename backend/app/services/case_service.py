from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.cases import RecoveryCaseCreate
from app.models import RecoveryCase


def create_recovery_case(
    database: Session,
    case_data: RecoveryCaseCreate
) -> RecoveryCase:

    recovery_case = RecoveryCase(
        tenant_id=case_data.tenant_id,

        provider_payment_id=case_data.provider_payment_id,
        provider_subscription_id=case_data.provider_subscription_id,
        provider_customer_id=case_data.provider_customer_id,

        currency=case_data.currency.upper(),

        original_amount_rupees=(
            case_data.original_amount_rupees
        ),

        recoverable_amount_rupees=(
            case_data.recoverable_amount_rupees
        ),

        recovery_deadline_at=(
            case_data.recovery_deadline_at
        )
    )

    database.add(recovery_case)

    try:
        database.commit()
        database.refresh(recovery_case)

    except Exception:
        database.rollback()
        raise

    return recovery_case


def get_recovery_cases(
    database: Session,
    offset: int,
    limit: int
) -> list[RecoveryCase]:

    statement = (
        select(RecoveryCase)
        .order_by(RecoveryCase.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    cases = database.scalars(statement).all()

    return list(cases)


def get_recovery_case_by_id(
    database: Session,
    case_id: UUID
) -> RecoveryCase | None:

    return database.get(
        RecoveryCase,
        case_id
    )