import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
)

from ml.feature_schema import TARGET_COLUMN
from ml.train_catboost import prepare_features
from ml.train_model import calculate_metrics


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

CALIBRATION_METRICS_PATH = (
    ML_DIRECTORY
    / "artifacts"
    / "catboost_calibration_metrics.json"
)


def probability_to_logit(
    probabilities: np.ndarray,
) -> np.ndarray:
    clipped = np.clip(
        probabilities,
        0.000001,
        0.999999,
    )

    logits = np.log(
        clipped / (1.0 - clipped)
    )

    return logits.reshape(-1, 1)


def expected_calibration_error(
    actual: pd.Series,
    probabilities: np.ndarray,
    number_of_bins: int = 10,
) -> float:
    actual_values = actual.to_numpy()
    probabilities = np.asarray(probabilities)

    bin_edges = np.linspace(
        0.0,
        1.0,
        number_of_bins + 1,
    )

    bin_indexes = np.digitize(
        probabilities,
        bin_edges[1:-1],
        right=True,
    )

    error = 0.0

    for bin_index in range(number_of_bins):
        mask = bin_indexes == bin_index

        if not np.any(mask):
            continue

        bin_accuracy = float(
            actual_values[mask].mean()
        )

        bin_confidence = float(
            probabilities[mask].mean()
        )

        bin_weight = float(mask.mean())

        error += (
            abs(bin_accuracy - bin_confidence)
            * bin_weight
        )

    return round(error, 6)


def calibration_scores(
    actual: pd.Series,
    probabilities: np.ndarray,
) -> dict[str, float]:
    probabilities = np.clip(
        probabilities,
        0.000001,
        0.999999,
    )

    return {
        "log_loss": round(
            float(
                log_loss(
                    actual,
                    probabilities,
                )
            ),
            6,
        ),
        "brier_score": round(
            float(
                brier_score_loss(
                    actual,
                    probabilities,
                )
            ),
            6,
        ),
        "expected_calibration_error": (
            expected_calibration_error(
                actual=actual,
                probabilities=probabilities,
            )
        ),
    }


def fit_platt_calibrator(
    probabilities: np.ndarray,
    target: pd.Series,
) -> LogisticRegression:
    calibrator = LogisticRegression(
        max_iter=1000,
        solver="lbfgs",
        random_state=42,
    )

    calibrator.fit(
        probability_to_logit(probabilities),
        target,
    )

    return calibrator


def predict_platt(
    calibrator: LogisticRegression,
    probabilities: np.ndarray,
) -> np.ndarray:
    return calibrator.predict_proba(
        probability_to_logit(probabilities)
    )[:, 1]


def fit_isotonic_calibrator(
    probabilities: np.ndarray,
    target: pd.Series,
) -> IsotonicRegression:
    calibrator = IsotonicRegression(
        out_of_bounds="clip",
        y_min=0.01,
        y_max=0.99,
    )

    calibrator.fit(
        probabilities,
        target,
    )

    return calibrator


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Dataset was not found: {DATA_PATH}"
        )

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"CatBoost model was not found: {MODEL_PATH}"
        )

    dataframe = pd.read_csv(DATA_PATH)

    dataframe["event_timestamp"] = (
        pd.to_datetime(
            dataframe["event_timestamp"],
            utc=True,
        )
    )

    dataframe = dataframe.sort_values(
        "event_timestamp"
    ).reset_index(drop=True)

    train_end = int(len(dataframe) * 0.70)
    validation_end = int(len(dataframe) * 0.85)

    validation_data = dataframe.iloc[
        train_end:validation_end
    ].reset_index(drop=True)

    test_data = dataframe.iloc[
        validation_end:
    ].reset_index(drop=True)

    calibration_split = int(
        len(validation_data) * 0.67
    )

    calibration_fit_data = validation_data.iloc[
        :calibration_split
    ]

    calibration_check_data = validation_data.iloc[
        calibration_split:
    ]

    validation_features = prepare_features(
        validation_data
    )

    test_features = prepare_features(test_data)

    validation_target = validation_data[
        TARGET_COLUMN
    ]

    test_target = test_data[TARGET_COLUMN]

    model = CatBoostClassifier()
    model.load_model(str(MODEL_PATH))

    validation_raw_probabilities = (
        model.predict_proba(
            validation_features
        )[:, 1]
    )

    test_raw_probabilities = (
        model.predict_proba(
            test_features
        )[:, 1]
    )

    fit_probabilities = (
        validation_raw_probabilities[
            :calibration_split
        ]
    )

    check_probabilities = (
        validation_raw_probabilities[
            calibration_split:
        ]
    )

    fit_target = calibration_fit_data[
        TARGET_COLUMN
    ]

    check_target = calibration_check_data[
        TARGET_COLUMN
    ]

    platt_calibrator = fit_platt_calibrator(
        probabilities=fit_probabilities,
        target=fit_target,
    )

    isotonic_calibrator = (
        fit_isotonic_calibrator(
            probabilities=fit_probabilities,
            target=fit_target,
        )
    )

    raw_check_scores = calibration_scores(
        actual=check_target,
        probabilities=check_probabilities,
    )

    platt_check_probabilities = predict_platt(
        calibrator=platt_calibrator,
        probabilities=check_probabilities,
    )

    isotonic_check_probabilities = (
        isotonic_calibrator.predict(
            check_probabilities
        )
    )

    candidate_scores = {
        "none": raw_check_scores,
        "platt": calibration_scores(
            actual=check_target,
            probabilities=(
                platt_check_probabilities
            ),
        ),
        "isotonic": calibration_scores(
            actual=check_target,
            probabilities=(
                isotonic_check_probabilities
            ),
        ),
    }

    selected_method = min(
        candidate_scores,
        key=lambda method: (
            candidate_scores[method][
                "brier_score"
            ],
            candidate_scores[method][
                "log_loss"
            ],
        ),
    )

    final_calibrator: Any = None

    if selected_method == "platt":
        final_calibrator = fit_platt_calibrator(
            probabilities=(
                validation_raw_probabilities
            ),
            target=validation_target,
        )

        test_selected_probabilities = (
            predict_platt(
                calibrator=final_calibrator,
                probabilities=(
                    test_raw_probabilities
                ),
            )
        )

    elif selected_method == "isotonic":
        final_calibrator = (
            fit_isotonic_calibrator(
                probabilities=(
                    validation_raw_probabilities
                ),
                target=validation_target,
            )
        )

        test_selected_probabilities = (
            final_calibrator.predict(
                test_raw_probabilities
            )
        )

    else:
        test_selected_probabilities = (
            test_raw_probabilities
        )

    raw_test_metrics = calculate_metrics(
        actual=test_target,
        probabilities=test_raw_probabilities,
    )

    selected_test_metrics = calculate_metrics(
        actual=test_target,
        probabilities=(
            test_selected_probabilities
        ),
    )

    calibration_result = {
        "method": selected_method,
        "model": final_calibrator,
    }

    joblib.dump(
        calibration_result,
        CALIBRATOR_PATH,
    )

    results = {
        "model_name": "catboost_recovery_v1",
        "selection_dataset": (
            "validation_calibration_check"
        ),
        "selected_calibration_method": (
            selected_method
        ),
        "candidate_check_scores": (
            candidate_scores
        ),
        "raw_test_metrics": raw_test_metrics,
        "calibrated_test_metrics": (
            selected_test_metrics
        ),
        "raw_test_ece": (
            expected_calibration_error(
                actual=test_target,
                probabilities=(
                    test_raw_probabilities
                ),
            )
        ),
        "calibrated_test_ece": (
            expected_calibration_error(
                actual=test_target,
                probabilities=(
                    test_selected_probabilities
                ),
            )
        ),
    }

    CALIBRATION_METRICS_PATH.write_text(
        json.dumps(
            results,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nCalibration evaluation completed")
    print(
        f"Selected method: {selected_method}"
    )

    print("\nCalibration candidate scores:")
    print(
        json.dumps(
            candidate_scores,
            indent=2,
        )
    )

    print("\nRaw test metrics:")
    print(
        json.dumps(
            raw_test_metrics,
            indent=2,
        )
    )

    print("\nSelected/calibrated test metrics:")
    print(
        json.dumps(
            selected_test_metrics,
            indent=2,
        )
    )

    print(
        "\nRaw test ECE:",
        results["raw_test_ece"],
    )

    print(
        "Calibrated test ECE:",
        results["calibrated_test_ece"],
    )

    print(f"\nCalibrator: {CALIBRATOR_PATH}")
    print(
        f"Metrics: {CALIBRATION_METRICS_PATH}"
    )


if __name__ == "__main__":
    main()