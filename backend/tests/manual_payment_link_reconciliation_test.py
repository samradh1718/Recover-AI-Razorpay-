import json

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    RecoveryCase,
    RecoveryDecision,
)
from app.services.payment_link_reconciliation_service import (
    reconcile_payment_link,
)


PAYMENT_ID = "pay_test_auto_009"


def main() -> None:
    with SessionLocal() as database:
        decision_id = database.execute(
            select(
                RecoveryDecision.id
            )
            .join(
                RecoveryCase,
                RecoveryCase.id
                == RecoveryDecision.recovery_case_id,
            )
            .where(
                RecoveryCase.provider_payment_id
                == PAYMENT_ID,
                RecoveryDecision.provider_action_id
                .is_not(None),
            )
            .order_by(
                RecoveryDecision.created_at.desc()
            )
            .limit(1)
        ).scalar_one_or_none()

        database.rollback()

        if decision_id is None:
            raise RuntimeError(
                "No Razorpay Payment Link decision "
                f"was found for {PAYMENT_ID}"
            )

        result = reconcile_payment_link(
            database=database,
            decision_id=decision_id,
        )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()