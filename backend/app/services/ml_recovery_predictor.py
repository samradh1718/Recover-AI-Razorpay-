from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from catboost import CatBoostClassifier

from ml.feature_schema import MODEL_FEATURES


BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]

ARTIFACT_DIRECTORY = (
    BACKEND_DIRECTORY / "ml" / "artifacts"
)

MODEL_PATH = (
    ARTIFACT_DIRECTORY
    / "catboost_recovery_model.cbm"
)

CALIBRATOR_PATH = (
    ARTIFACT_DIRECTORY
    / "catboost_probability_calibrator.joblib"
)


class MLArtifactError(RuntimeError):
    """Raised when an ML artifact cannot be loaded."""


class MLRecoveryPredictor:
    def __init__(self) -> None:
        if not MODEL_PATH.exists():
            raise MLArtifactError(
                f"CatBoost model not found: {MODEL_PATH}"
            )

        if not CALIBRATOR_PATH.exists():
            raise MLArtifactError(
                "Probability calibrator not found: "
                f"{CALIBRATOR_PATH}"
            )

        self.model = CatBoostClassifier()
        self.model.load_model(str(MODEL_PATH))

        loaded_calibrator = joblib.load(
            CALIBRATOR_PATH
        )

        if isinstance(loaded_calibrator, dict):
            self.calibrator = (
                loaded_calibrator.get("calibrator")
                or loaded_calibrator.get("model")
                or loaded_calibrator.get("estimator")
            )
        else:
            self.calibrator = loaded_calibrator

        if self.calibrator is None:
            raise MLArtifactError(
                "The calibration artifact does not "
                "contain a valid calibrator"
            )

    def predict_raw_probability(
        self,
        features: dict[str, Any],
    ) -> float:
        missing_features = [
            feature_name
            for feature_name in MODEL_FEATURES
            if feature_name not in features
        ]

        if missing_features:
            raise ValueError(
                "Missing ML features: "
                + ", ".join(missing_features)
            )

        model_input = pd.DataFrame(
            [
                {
                    feature_name: features[
                        feature_name
                    ]
                    for feature_name in MODEL_FEATURES
                }
            ],
            columns=MODEL_FEATURES,
        )

        probability = self.model.predict_proba(
            model_input
        )[0][1]

        return float(probability)

    def calibrate_probability(
        self,
        raw_probability: float,
    ) -> float:
        calibration_input = [
            [float(raw_probability)]
        ]

        if hasattr(
            self.calibrator,
            "predict_proba",
        ):
            calibrated_probability = (
                self.calibrator.predict_proba(
                    calibration_input
                )[0][1]
            )

        elif hasattr(
            self.calibrator,
            "predict",
        ):
            calibrated_probability = (
                self.calibrator.predict(
                    calibration_input
                )[0]
            )

        else:
            raise MLArtifactError(
                "Calibrator has neither "
                "predict_proba() nor predict()"
            )

        return max(
            0.0,
            min(
                1.0,
                float(calibrated_probability),
            ),
        )

    def predict_recovery_probability(
        self,
        features: dict[str, Any],
    ) -> dict[str, float]:
        raw_probability = (
            self.predict_raw_probability(
                features
            )
        )

        calibrated_probability = (
            self.calibrate_probability(
                raw_probability
            )
        )

        return {
            "raw_probability": raw_probability,
            "calibrated_probability": (
                calibrated_probability
            ),
        }