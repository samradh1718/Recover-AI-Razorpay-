import hashlib
import json
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from ml.evaluate_model import predict_platt
from ml.generate_training_data import (
    ACTION_COSTS,
    PREFERRED_ACTIONS,
    RECOVERY_ACTIONS,
    calculate_recovery_probability,
)
from ml.train_catboost import prepare_features
from ml.train_model import validate_dataset


ML_DIRECTORY = Path(__file__).resolve().parent

DATA_PATH = (
    ML_DIRECTORY
    / "data"
    / "recovery_training_data.csv"
)

MODEL_PATH = (
    ML_DIRECTORY
    / "artifacts"
    / "catboost_recovery_model.cbm"
)

CALIBRATOR_PATH = (
    ML_DIRECTORY
    / "artifacts"
    / "catboost_probability_calibrator.joblib"
)

OUTPUT_PATH = (
    ML_DIRECTORY
    / "artifacts"
    / "recovery_policy_evaluation.json"
)


def stable_case_seed(case_id: str) -> int:
    digest = hashlib.sha256(
        f"{case_id}:policy-evaluation-v1".encode(
            "utf-8"
        )
    ).digest()

    return int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=False,
    )


def calculate_true_probability(
    row: pd.Series,
    recovery_action: str,
) -> float:
    # Every candidate action for the same case receives
    # the same deterministic noise draw. This prevents
    # random noise from unfairly favouring one action.
    rng = np.random.default_rng(
        stable_case_seed(str(row["case_id"]))
    )

    return calculate_recovery_probability(
        failure_category=str(
            row["failure_category"]
        ),
        payment_method=str(
            row["payment_method"]
        ),
        recovery_action=recovery_action,
        amount_rupees=float(
            row["amount_rupees"]
        ),
        attempt_count=int(
            row["attempt_count"]
        ),
        communication_count=int(
            row["communication_count"]
        ),
        customer_success_rate=float(
            row["customer_success_rate"]
        ),
        previous_recoveries=int(
            row["previous_recoveries"]
        ),
        hours_since_failure=float(
            row["hours_since_failure"]
        ),
        is_subscription=int(
            row["is_subscription"]
        ),
        rng=rng,
    )


def calibrate_probabilities(
    artifact: dict,
    raw_probabilities: np.ndarray,
) -> np.ndarray:
    method = str(artifact["method"])
    calibrator = artifact["model"]

    if method == "none":
        return raw_probabilities

    if method == "platt":
        return predict_platt(
            calibrator=calibrator,
            probabilities=raw_probabilities,
        )

    if method == "isotonic":
        return np.asarray(
            calibrator.predict(
                raw_probabilities
            ),
            dtype=float,
        )

    raise ValueError(
        f"Unsupported calibration method: {method}"
    )


def build_model_probability_matrix(
    test_data: pd.DataFrame,
    model: CatBoostClassifier,
    calibration_artifact: dict,
) -> np.ndarray:
    candidate_frames: list[pd.DataFrame] = []

    for action in RECOVERY_ACTIONS:
        candidate_data = test_data.copy()
        candidate_data["recovery_action"] = action
        candidate_frames.append(candidate_data)

    all_candidates = pd.concat(
        candidate_frames,
        ignore_index=True,
    )

    candidate_features = prepare_features(
        all_candidates
    )

    raw_probabilities = model.predict_proba(
        candidate_features
    )[:, 1]

    calibrated_probabilities = (
        calibrate_probabilities(
            artifact=calibration_artifact,
            raw_probabilities=raw_probabilities,
        )
    )

    case_count = len(test_data)

    return np.column_stack(
        [
            calibrated_probabilities[
                action_index
                * case_count:
                (action_index + 1)
                * case_count
            ]
            for action_index in range(
                len(RECOVERY_ACTIONS)
            )
        ]
    )


def build_true_probability_matrix(
    test_data: pd.DataFrame,
) -> np.ndarray:
    matrix = np.zeros(
        (
            len(test_data),
            len(RECOVERY_ACTIONS),
        ),
        dtype=float,
    )

    for row_index, (_, row) in enumerate(
        test_data.iterrows()
    ):
        for action_index, action in enumerate(
            RECOVERY_ACTIONS
        ):
            matrix[
                row_index,
                action_index,
            ] = calculate_true_probability(
                row=row,
                recovery_action=action,
            )

    return matrix


def action_indices(
    actions: list[str],
) -> np.ndarray:
    action_to_index = {
        action: index
        for index, action in enumerate(
            RECOVERY_ACTIONS
        )
    }

    return np.asarray(
        [
            action_to_index[action]
            for action in actions
        ],
        dtype=int,
    )


def summarize_policy(
    *,
    policy_name: str,
    selected_indices: np.ndarray,
    oracle_indices: np.ndarray,
    true_probability_matrix: np.ndarray,
    amounts: np.ndarray,
    action_costs: np.ndarray,
) -> dict:
    row_indices = np.arange(
        len(selected_indices)
    )

    selected_probabilities = (
        true_probability_matrix[
            row_indices,
            selected_indices,
        ]
    )

    selected_costs = action_costs[
        selected_indices
    ]

    expected_gross_recovery = float(
        np.sum(
            selected_probabilities * amounts
        )
    )

    intervention_cost = float(
        np.sum(selected_costs)
    )

    expected_net_recovery = (
        expected_gross_recovery
        - intervention_cost
    )

    payment_volume = float(
        np.sum(amounts)
    )

    selected_actions = [
        RECOVERY_ACTIONS[index]
        for index in selected_indices
    ]

    action_counts = Counter(
        selected_actions
    )

    oracle_agreement = float(
        np.mean(
            selected_indices
            == oracle_indices
        )
    )

    return {
        "policy": policy_name,
        "cases": len(selected_indices),
        "payment_volume_rupees": round(
            payment_volume,
            2,
        ),
        "expected_recovered_cases": round(
            float(
                np.sum(
                    selected_probabilities
                )
            ),
            2,
        ),
        "expected_recovery_rate_percent": round(
            float(
                np.mean(
                    selected_probabilities
                )
                * 100
            ),
            4,
        ),
        "expected_gross_recovery_rupees": round(
            expected_gross_recovery,
            2,
        ),
        "intervention_cost_rupees": round(
            intervention_cost,
            2,
        ),
        "expected_net_recovery_rupees": round(
            expected_net_recovery,
            2,
        ),
        "net_recovery_rate_percent": round(
            (
                expected_net_recovery
                / payment_volume
                * 100
            ),
            4,
        ),
        "oracle_agreement_percent": round(
            oracle_agreement * 100,
            4,
        ),
        "action_distribution": {
            action: action_counts.get(
                action,
                0,
            )
            for action in RECOVERY_ACTIONS
        },
    }


def compare_policies(
    candidate: dict,
    baseline: dict,
) -> dict:
    candidate_net = float(
        candidate[
            "expected_net_recovery_rupees"
        ]
    )

    baseline_net = float(
        baseline[
            "expected_net_recovery_rupees"
        ]
    )

    absolute_uplift = (
        candidate_net - baseline_net
    )

    uplift_percent = (
        absolute_uplift
        / abs(baseline_net)
        * 100
        if baseline_net != 0
        else None
    )

    return {
        "candidate": candidate["policy"],
        "baseline": baseline["policy"],
        "absolute_net_uplift_rupees": round(
            absolute_uplift,
            2,
        ),
        "relative_net_uplift_percent": (
            round(uplift_percent, 4)
            if uplift_percent is not None
            else None
        ),
    }


def main() -> None:
    for required_path in (
        DATA_PATH,
        MODEL_PATH,
        CALIBRATOR_PATH,
    ):
        if not required_path.exists():
            raise FileNotFoundError(
                f"Required file was not found: "
                f"{required_path}"
            )

    dataframe = pd.read_csv(DATA_PATH)

    validate_dataset(dataframe)

    dataframe["event_timestamp"] = (
        pd.to_datetime(
            dataframe["event_timestamp"],
            utc=True,
        )
    )

    dataframe = dataframe.sort_values(
        "event_timestamp"
    ).reset_index(drop=True)

    test_start = int(
        len(dataframe) * 0.85
    )

    test_data = (
        dataframe.iloc[test_start:]
        .copy()
        .reset_index(drop=True)
    )

    model = CatBoostClassifier()
    model.load_model(str(MODEL_PATH))

    calibration_artifact = joblib.load(
        CALIBRATOR_PATH
    )

    model_probability_matrix = (
        build_model_probability_matrix(
            test_data=test_data,
            model=model,
            calibration_artifact=(
                calibration_artifact
            ),
        )
    )

    true_probability_matrix = (
        build_true_probability_matrix(
            test_data
        )
    )

    amounts = test_data[
        "amount_rupees"
    ].astype(float).to_numpy()

    action_costs = np.asarray(
        [
            ACTION_COSTS[action]
            for action in RECOVERY_ACTIONS
        ],
        dtype=float,
    )

    true_expected_net_matrix = (
        true_probability_matrix
        * amounts[:, np.newaxis]
        - action_costs[np.newaxis, :]
    )

    model_expected_net_matrix = (
        model_probability_matrix
        * amounts[:, np.newaxis]
        - action_costs[np.newaxis, :]
    )

    oracle_indices = np.argmax(
        true_expected_net_matrix,
        axis=1,
    )

    catboost_indices = np.argmax(
        model_expected_net_matrix,
        axis=1,
    )

    rules_indices = action_indices(
        [
            PREFERRED_ACTIONS[
                str(failure_category)
            ]
            for failure_category in test_data[
                "failure_category"
            ]
        ]
    )

    logged_indices = action_indices(
        test_data[
            "recovery_action"
        ].astype(str).tolist()
    )

    stop_index = RECOVERY_ACTIONS.index(
        "stop_recovery"
    )

    stop_indices = np.full(
        len(test_data),
        stop_index,
        dtype=int,
    )

    policies = {
        "stop_recovery": summarize_policy(
            policy_name="stop_recovery",
            selected_indices=stop_indices,
            oracle_indices=oracle_indices,
            true_probability_matrix=(
                true_probability_matrix
            ),
            amounts=amounts,
            action_costs=action_costs,
        ),
        "logged_synthetic": summarize_policy(
            policy_name="logged_synthetic",
            selected_indices=logged_indices,
            oracle_indices=oracle_indices,
            true_probability_matrix=(
                true_probability_matrix
            ),
            amounts=amounts,
            action_costs=action_costs,
        ),
        "rules_preferred": summarize_policy(
            policy_name="rules_preferred",
            selected_indices=rules_indices,
            oracle_indices=oracle_indices,
            true_probability_matrix=(
                true_probability_matrix
            ),
            amounts=amounts,
            action_costs=action_costs,
        ),
        "catboost_calibrated": summarize_policy(
            policy_name="catboost_calibrated",
            selected_indices=catboost_indices,
            oracle_indices=oracle_indices,
            true_probability_matrix=(
                true_probability_matrix
            ),
            amounts=amounts,
            action_costs=action_costs,
        ),
        "synthetic_oracle": summarize_policy(
            policy_name="synthetic_oracle",
            selected_indices=oracle_indices,
            oracle_indices=oracle_indices,
            true_probability_matrix=(
                true_probability_matrix
            ),
            amounts=amounts,
            action_costs=action_costs,
        ),
    }

    comparisons = {
        "catboost_vs_stop": compare_policies(
            policies["catboost_calibrated"],
            policies["stop_recovery"],
        ),
        "catboost_vs_logged": compare_policies(
            policies["catboost_calibrated"],
            policies["logged_synthetic"],
        ),
        "catboost_vs_rules": compare_policies(
            policies["catboost_calibrated"],
            policies["rules_preferred"],
        ),
        "catboost_vs_oracle": compare_policies(
            policies["catboost_calibrated"],
            policies["synthetic_oracle"],
        ),
    }

    results = {
        "evaluation_name": (
            "synthetic_counterfactual_policy_v1"
        ),
        "dataset_source": "synthetic_v1",
        "test_rows": len(test_data),
        "split_strategy": (
            "chronological_70_15_15"
        ),
        "calibration_method": (
            calibration_artifact["method"]
        ),
        "methodology": {
            "ground_truth": (
                "synthetic generator expected "
                "recovery probability"
            ),
            "selection_objective": (
                "probability * amount_rupees "
                "- action_cost_rupees"
            ),
            "noise_control": (
                "same deterministic noise draw "
                "for every candidate action "
                "within a case"
            ),
            "real_world_claim": False,
        },
        "policies": policies,
        "comparisons": comparisons,
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            results,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Synthetic policy evaluation completed")
    print("Test cases:", len(test_data))
    print(
        "Payment volume:",
        f"INR {np.sum(amounts):,.2f}",
    )
    print()

    for policy in policies.values():
        print(
            f"{policy['policy']:<22} "
            f"| net INR "
            f"{policy['expected_net_recovery_rupees']:>12,.2f} "
            f"| recovery "
            f"{policy['expected_recovery_rate_percent']:>7.3f}% "
            f"| oracle agreement "
            f"{policy['oracle_agreement_percent']:>7.3f}%"
        )

    print()
    print("CatBoost comparisons")

    for comparison in comparisons.values():
        print(
            f"{comparison['candidate']} vs "
            f"{comparison['baseline']}: "
            f"INR "
            f"{comparison['absolute_net_uplift_rupees']:,.2f} "
            f"("
            f"{comparison['relative_net_uplift_percent']}"
            f"%)"
        )

    print()
    print("Saved:", OUTPUT_PATH)


if __name__ == "__main__":
    main()