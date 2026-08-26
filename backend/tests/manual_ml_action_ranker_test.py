import json

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.recovery_case import RecoveryCase
from app.services.ml_action_ranker import (
    rank_recovery_actions,
)


def main() -> None:
    with SessionLocal() as database:
        recovery_case = database.execute(
            select(RecoveryCase)
            .where(
                RecoveryCase.failure_category.is_not(None)
            )
            .order_by(
                RecoveryCase.created_at.desc()
            )
            .limit(1)
        ).scalar_one_or_none()

        if recovery_case is None:
            raise RuntimeError(
                "No recovery case is available for testing"
            )

        results = rank_recovery_actions(
            recovery_case
        )

        print("\nRecovery case")
        print("Case ID:", recovery_case.id)
        print(
            "Payment ID:",
            recovery_case.provider_payment_id,
        )
        print(
            "Failure:",
            recovery_case.failure_category.value,
        )
        print(
            "Amount:",
            recovery_case.recoverable_amount_rupees,
        )

        print("\nML action ranking")
        print(
            json.dumps(
                results,
                indent=2,
                default=str,
            )
        )

        if results:
            print("\nSelected ML shadow action")
            print("Action:", results[0]["action"])
            print(
                "Probability:",
                results[0][
                    "calibrated_probability"
                ],
            )
            print(
                "Expected net value: ₹",
                results[0][
                    "expected_net_value_rupees"
                ],
                sep="",
            )


if __name__ == "__main__":
    main()