import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd


RANDOM_SEED = 42
GENERATOR_VERSION = "synthetic_v1"

FAILURE_CATEGORIES = [
    "temporary_gateway_or_bank",
    "insufficient_funds",
    "invalid_or_expired_method",
    "mandate_or_authorization",
    "unknown",
]

FAILURE_WEIGHTS = [
    0.27,
    0.25,
    0.18,
    0.22,
    0.08,
]

PAYMENT_METHODS = [
    "card",
    "upi",
    "netbanking",
    "wallet",
    "emandate",
]

PAYMENT_METHOD_WEIGHTS = [
    0.34,
    0.30,
    0.14,
    0.08,
    0.14,
]

RECOVERY_ACTIONS = [
    "retry_payment",
    "send_payment_link",
    "request_payment_method_update",
    "request_customer_authorization",
    "human_review",
    "stop_recovery",
]

PREFERRED_ACTIONS = {
    "temporary_gateway_or_bank": "retry_payment",
    "insufficient_funds": "retry_payment",
    "invalid_or_expired_method": (
        "request_payment_method_update"
    ),
    "mandate_or_authorization": (
        "request_customer_authorization"
    ),
    "unknown": "human_review",
}

BASE_RECOVERY_PROBABILITY = {
    "temporary_gateway_or_bank": 0.58,
    "insufficient_funds": 0.38,
    "invalid_or_expired_method": 0.26,
    "mandate_or_authorization": 0.46,
    "unknown": 0.16,
}

ACTION_EFFECTS = {
    "temporary_gateway_or_bank": {
        "retry_payment": 0.24,
        "send_payment_link": 0.05,
        "request_payment_method_update": -0.05,
        "request_customer_authorization": -0.07,
        "human_review": -0.02,
        "stop_recovery": -0.30,
    },
    "insufficient_funds": {
        "retry_payment": 0.13,
        "send_payment_link": 0.11,
        "request_payment_method_update": 0.07,
        "request_customer_authorization": -0.05,
        "human_review": -0.02,
        "stop_recovery": -0.28,
    },
    "invalid_or_expired_method": {
        "retry_payment": -0.15,
        "send_payment_link": 0.16,
        "request_payment_method_update": 0.32,
        "request_customer_authorization": -0.04,
        "human_review": 0.02,
        "stop_recovery": -0.24,
    },
    "mandate_or_authorization": {
        "retry_payment": -0.09,
        "send_payment_link": 0.10,
        "request_payment_method_update": 0.04,
        "request_customer_authorization": 0.30,
        "human_review": 0.01,
        "stop_recovery": -0.27,
    },
    "unknown": {
        "retry_payment": -0.04,
        "send_payment_link": 0.04,
        "request_payment_method_update": 0.01,
        "request_customer_authorization": 0.01,
        "human_review": 0.13,
        "stop_recovery": -0.15,
    },
}

ACTION_COSTS = {
    "retry_payment": 0.50,
    "send_payment_link": 1.00,
    "request_payment_method_update": 1.50,
    "request_customer_authorization": 1.00,
    "human_review": 50.00,
    "stop_recovery": 0.00,
}


def choose_action(
    rng: np.random.Generator,
    failure_category: str,
) -> str:
    # Most historical decisions follow the preferred
    # action, while some exploration remains.
    if rng.random() < 0.72:
        return PREFERRED_ACTIONS[failure_category]

    return str(rng.choice(RECOVERY_ACTIONS))


def calculate_recovery_probability(
    *,
    failure_category: str,
    payment_method: str,
    recovery_action: str,
    amount_rupees: float,
    attempt_count: int,
    communication_count: int,
    customer_success_rate: float,
    previous_recoveries: int,
    hours_since_failure: float,
    is_subscription: int,
    rng: np.random.Generator,
) -> float:
    probability = (
        BASE_RECOVERY_PROBABILITY[failure_category]
        + ACTION_EFFECTS[failure_category][recovery_action]
    )

    probability += (
        customer_success_rate - 0.50
    ) * 0.30

    probability -= attempt_count * 0.055
    probability -= communication_count * 0.018

    probability -= min(
        hours_since_failure,
        168,
    ) * 0.0012

    if previous_recoveries > 0:
        probability += min(
            previous_recoveries * 0.015,
            0.08,
        )

    if amount_rupees > 10000:
        probability -= 0.04

    if amount_rupees > 50000:
        probability -= 0.05

    if (
        payment_method == "card"
        and failure_category
        == "invalid_or_expired_method"
        and recovery_action
        == "request_payment_method_update"
    ):
        probability += 0.08

    if (
        payment_method == "emandate"
        and failure_category
        == "mandate_or_authorization"
        and recovery_action
        == "request_customer_authorization"
    ):
        probability += 0.06

    if (
        is_subscription == 1
        and recovery_action
        == "request_customer_authorization"
    ):
        probability += 0.025

    # Noise prevents the generated data from being
    # perfectly predictable.
    probability += float(
        rng.normal(loc=0.0, scale=0.045)
    )

    return float(
        np.clip(probability, 0.02, 0.95)
    )


def derive_customer_segment(
    amount_rupees: float,
    customer_tenure_days: int,
    customer_success_rate: float,
) -> str:
    if (
        amount_rupees >= 10000
        or customer_tenure_days >= 900
    ):
        return "high_value"

    if (
        customer_tenure_days <= 45
        or customer_success_rate < 0.45
    ):
        return "new_or_risky"

    return "standard"


def generate_dataset(
    row_count: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    now = datetime.now(timezone.utc)

    records: list[dict] = []

    for _ in range(row_count):
        failure_category = str(
            rng.choice(
                FAILURE_CATEGORIES,
                p=FAILURE_WEIGHTS,
            )
        )

        payment_method = str(
            rng.choice(
                PAYMENT_METHODS,
                p=PAYMENT_METHOD_WEIGHTS,
            )
        )

        recovery_action = choose_action(
            rng=rng,
            failure_category=failure_category,
        )

        amount_rupees = round(
            float(
                np.clip(
                    rng.lognormal(
                        mean=7.55,
                        sigma=1.00,
                    ),
                    100,
                    100000,
                )
            ),
            2,
        )

        attempt_count = int(
            rng.choice(
                [0, 1, 2, 3, 4],
                p=[0.42, 0.29, 0.17, 0.08, 0.04],
            )
        )

        communication_count = int(
            rng.choice(
                [0, 1, 2, 3],
                p=[0.48, 0.31, 0.15, 0.06],
            )
        )

        customer_success_rate = round(
            float(rng.beta(7, 2.5)),
            4,
        )

        customer_tenure_days = int(
            rng.integers(1, 1826)
        )

        previous_failures = int(
            rng.poisson(lam=1.8)
        )

        previous_recoveries = int(
            rng.binomial(
                n=previous_failures,
                p=min(
                    0.85,
                    customer_success_rate,
                ),
            )
        )

        hours_since_failure = round(
            float(
                np.clip(
                    rng.exponential(scale=22),
                    0,
                    168,
                )
            ),
            2,
        )

        days_to_deadline = round(
            max(
                0.0,
                7.0 - hours_since_failure / 24,
            ),
            2,
        )

        is_subscription = int(
            rng.random() < 0.43
        )

        days_ago = int(rng.integers(0, 366))
        event_hour = int(rng.integers(0, 24))
        event_minute = int(rng.integers(0, 60))

        event_timestamp = (
            now
            - timedelta(days=days_ago)
        ).replace(
            hour=event_hour,
            minute=event_minute,
            second=0,
            microsecond=0,
        )

        customer_segment = derive_customer_segment(
            amount_rupees=amount_rupees,
            customer_tenure_days=customer_tenure_days,
            customer_success_rate=customer_success_rate,
        )

        recovery_probability = (
            calculate_recovery_probability(
                failure_category=failure_category,
                payment_method=payment_method,
                recovery_action=recovery_action,
                amount_rupees=amount_rupees,
                attempt_count=attempt_count,
                communication_count=(
                    communication_count
                ),
                customer_success_rate=(
                    customer_success_rate
                ),
                previous_recoveries=(
                    previous_recoveries
                ),
                hours_since_failure=(
                    hours_since_failure
                ),
                is_subscription=is_subscription,
                rng=rng,
            )
        )

        recovered = int(
            rng.random() < recovery_probability
        )

        recovered_amount_rupees = (
            amount_rupees if recovered else 0.0
        )

        action_cost_rupees = ACTION_COSTS[
            recovery_action
        ]

        net_recovered_rupees = round(
            recovered_amount_rupees
            - action_cost_rupees,
            2,
        )

        time_to_recovery_hours = (
            round(
                float(
                    np.clip(
                        rng.exponential(
                            scale=18 + attempt_count * 8
                        ),
                        0.25,
                        168,
                    )
                ),
                2,
            )
            if recovered
            else None
        )

        records.append(
            {
                "case_id": str(uuid4()),
                "customer_id": (
                    f"cust_{uuid4().hex[:12]}"
                ),
                "event_timestamp": (
                    event_timestamp.isoformat()
                ),
                "data_source": "synthetic",
                "generator_version": (
                    GENERATOR_VERSION
                ),
                "failure_category": failure_category,
                "payment_method": payment_method,
                "recovery_action": recovery_action,
                "customer_segment": customer_segment,
                "amount_rupees": amount_rupees,
                "attempt_count": attempt_count,
                "communication_count": (
                    communication_count
                ),
                "customer_success_rate": (
                    customer_success_rate
                ),
                "customer_tenure_days": (
                    customer_tenure_days
                ),
                "previous_failures": previous_failures,
                "previous_recoveries": (
                    previous_recoveries
                ),
                "hours_since_failure": (
                    hours_since_failure
                ),
                "days_to_deadline": days_to_deadline,
                "hour_of_day": event_timestamp.hour,
                "day_of_week": (
                    event_timestamp.weekday()
                ),
                "is_subscription": is_subscription,
                "recovered": recovered,
                "recovered_amount_rupees": (
                    recovered_amount_rupees
                ),
                "action_cost_rupees": (
                    action_cost_rupees
                ),
                "net_recovered_rupees": (
                    net_recovered_rupees
                ),
                "time_to_recovery_hours": (
                    time_to_recovery_hours
                ),
            }
        )

    dataframe = pd.DataFrame(records)

    return dataframe.sort_values(
        "event_timestamp"
    ).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--rows",
        type=int,
        default=20000,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=RANDOM_SEED,
    )

    arguments = parser.parse_args()

    if arguments.rows < 1000:
        raise ValueError(
            "Generate at least 1000 rows"
        )

    dataframe = generate_dataset(
        row_count=arguments.rows,
        seed=arguments.seed,
    )

    output_directory = (
        Path(__file__).resolve().parent / "data"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_directory
        / "recovery_training_data.csv"
    )

    dataframe.to_csv(
        output_path,
        index=False,
    )

    print("\nDataset generated successfully")
    print(f"Path: {output_path}")
    print(f"Rows: {len(dataframe):,}")
    print(f"Columns: {len(dataframe.columns)}")

    print(
        "Recovery rate: "
        f"{dataframe['recovered'].mean() * 100:.2f}%"
    )

    print("\nFailure-category distribution:")
    print(
        dataframe[
            "failure_category"
        ].value_counts(normalize=True)
        .mul(100)
        .round(2)
        .to_string()
    )

    print("\nAction outcome rates:")
    print(
        dataframe.groupby(
            "recovery_action"
        )["recovered"]
        .agg(["count", "mean"])
        .assign(
            recovery_rate_percent=lambda value: (
                value["mean"] * 100
            ).round(2)
        )
        .drop(columns=["mean"])
        .to_string()
    )


if __name__ == "__main__":
    main()