import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    OneHotEncoder,
    StandardScaler,
)

from ml.feature_schema import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
)


ML_DIRECTORY = Path(__file__).resolve().parent

DATA_PATH = (
    ML_DIRECTORY
    / "data"
    / "recovery_training_data.csv"
)

ARTIFACT_DIRECTORY = ML_DIRECTORY / "artifacts"

MODEL_PATH = (
    ARTIFACT_DIRECTORY
    / "logistic_recovery_pipeline.joblib"
)

METRICS_PATH = (
    ARTIFACT_DIRECTORY
    / "logistic_metrics.json"
)


def validate_dataset(
    dataframe: pd.DataFrame,
) -> None:
    required_columns = set(
        MODEL_FEATURES
        + [TARGET_COLUMN, "event_timestamp"]
    )

    missing_columns = (
        required_columns - set(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            "Dataset is missing columns: "
            + ", ".join(sorted(missing_columns))
        )

    if dataframe.empty:
        raise ValueError("Dataset is empty")

    target_values = set(
        dataframe[TARGET_COLUMN]
        .dropna()
        .unique()
        .tolist()
    )

    if not target_values.issubset({0, 1}):
        raise ValueError(
            "Target column must contain only 0 and 1"
        )


def create_model_pipeline() -> Pipeline:
    numeric_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
            (
                "scaler",
                StandardScaler(),
            ),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="most_frequent"
                ),
            ),
            (
                "encoder",
                OneHotEncoder(
                    handle_unknown="ignore"
                ),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                categorical_pipeline,
                CATEGORICAL_FEATURES,
            ),
        ]
    )

    classifier = LogisticRegression(
        max_iter=2000,
        solver="lbfgs",
        random_state=42,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


def calculate_metrics(
    actual: pd.Series,
    probabilities: np.ndarray,
) -> dict[str, Any]:
    predictions = (
        probabilities >= 0.50
    ).astype(int)

    matrix = confusion_matrix(
        actual,
        predictions,
        labels=[0, 1],
    )

    return {
        "rows": int(len(actual)),
        "positive_rate": round(
            float(actual.mean()),
            6,
        ),
        "accuracy": round(
            float(
                accuracy_score(
                    actual,
                    predictions,
                )
            ),
            6,
        ),
        "precision": round(
            float(
                precision_score(
                    actual,
                    predictions,
                    zero_division=0,
                )
            ),
            6,
        ),
        "recall": round(
            float(
                recall_score(
                    actual,
                    predictions,
                    zero_division=0,
                )
            ),
            6,
        ),
        "f1": round(
            float(
                f1_score(
                    actual,
                    predictions,
                    zero_division=0,
                )
            ),
            6,
        ),
        "roc_auc": round(
            float(
                roc_auc_score(
                    actual,
                    probabilities,
                )
            ),
            6,
        ),
        "average_precision": round(
            float(
                average_precision_score(
                    actual,
                    probabilities,
                )
            ),
            6,
        ),
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
        "confusion_matrix": {
            "true_negative": int(matrix[0, 0]),
            "false_positive": int(matrix[0, 1]),
            "false_negative": int(matrix[1, 0]),
            "true_positive": int(matrix[1, 1]),
        },
    }


def calculate_naive_metrics(
    training_target: pd.Series,
    test_target: pd.Series,
) -> dict[str, float]:
    constant_probability = float(
        training_target.mean()
    )

    probabilities = np.full(
        shape=len(test_target),
        fill_value=constant_probability,
    )

    return {
        "constant_probability": round(
            constant_probability,
            6,
        ),
        "log_loss": round(
            float(
                log_loss(
                    test_target,
                    probabilities,
                )
            ),
            6,
        ),
        "brier_score": round(
            float(
                brier_score_loss(
                    test_target,
                    probabilities,
                )
            ),
            6,
        ),
    }


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Dataset was not found: {DATA_PATH}"
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

    train_end = int(len(dataframe) * 0.70)
    validation_end = int(len(dataframe) * 0.85)

    training_data = dataframe.iloc[:train_end]
    validation_data = dataframe.iloc[
        train_end:validation_end
    ]
    test_data = dataframe.iloc[validation_end:]

    training_features = training_data[
        MODEL_FEATURES
    ]
    training_target = training_data[
        TARGET_COLUMN
    ]

    validation_features = validation_data[
        MODEL_FEATURES
    ]
    validation_target = validation_data[
        TARGET_COLUMN
    ]

    test_features = test_data[MODEL_FEATURES]
    test_target = test_data[TARGET_COLUMN]

    model = create_model_pipeline()

    print("\nTraining Logistic Regression...")
    model.fit(
        training_features,
        training_target,
    )

    validation_probabilities = (
        model.predict_proba(
            validation_features
        )[:, 1]
    )

    test_probabilities = (
        model.predict_proba(
            test_features
        )[:, 1]
    )

    validation_metrics = calculate_metrics(
        actual=validation_target,
        probabilities=validation_probabilities,
    )

    test_metrics = calculate_metrics(
        actual=test_target,
        probabilities=test_probabilities,
    )

    naive_test_metrics = calculate_naive_metrics(
        training_target=training_target,
        test_target=test_target,
    )

    results = {
        "model_name": "logistic_regression_v1",
        "dataset": str(DATA_PATH),
        "data_source": "synthetic_v1",
        "features": MODEL_FEATURES,
        "split_strategy": "chronological_70_15_15",
        "training_rows": len(training_data),
        "validation_rows": len(validation_data),
        "test_rows": len(test_data),
        "training_positive_rate": round(
            float(training_target.mean()),
            6,
        ),
        "validation": validation_metrics,
        "test": test_metrics,
        "naive_test_baseline": naive_test_metrics,
    }

    ARTIFACT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        model,
        MODEL_PATH,
    )

    METRICS_PATH.write_text(
        json.dumps(
            results,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nTraining completed successfully")
    print(f"Model: {MODEL_PATH}")
    print(f"Metrics: {METRICS_PATH}")

    print("\nValidation metrics:")
    print(
        json.dumps(
            validation_metrics,
            indent=2,
        )
    )

    print("\nTest metrics:")
    print(
        json.dumps(
            test_metrics,
            indent=2,
        )
    )

    print("\nNaive test baseline:")
    print(
        json.dumps(
            naive_test_metrics,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()