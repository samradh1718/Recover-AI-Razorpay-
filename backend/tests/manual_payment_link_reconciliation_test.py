import argparse
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


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile the latest Razorpay Payment Link "
            "decision, or a specified payment."
        )
    )

    parser.add_argument(
        "--payment-id",
        help=(
            "Optional original provider payment ID. "
            "The latest eligible decision is used "
            "when omitted."
        ),
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    with SessionLocal() as database:
        query = (
            select(
                RecoveryDecision.id,
                RecoveryCase.provider_payment_id,
            )
            .join(
                RecoveryCase,
                RecoveryCase.id
                == RecoveryDecision.recovery_case_id,
            )
            .where(
                RecoveryDecision.provider_action_id
                .is_not(None),
            )
            .order_by(
                RecoveryDecision.created_at.desc()
            )
            .limit(1)
        )

        if arguments.payment_id is not None:
            query = query.where(
                RecoveryCase.provider_payment_id
                == arguments.payment_id
            )

        match = database.execute(
            query
        ).one_or_none()

        database.rollback()

        if match is None:
            target = (
                arguments.payment_id
                or "the latest recovery case"
            )

            raise RuntimeError(
                "No Razorpay Payment Link decision "
                f"was found for {target}"
            )

        decision_id = match[0]
        payment_id = match[1]

        print(
            "Reconciling latest eligible decision"
        )
        print("Payment ID:", payment_id)
        print("Decision ID:", decision_id)

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