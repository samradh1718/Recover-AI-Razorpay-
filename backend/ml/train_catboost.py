import json
from pathlib import Path
from typing import Any

import pandas as pd
from catboost import CatBoostClassifier

from ml.feature_schema import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
)
from ml.train_model import (
    calculate_metrics,
    calculate_naive_metrics,
    validate_dataset,
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
    / "catboost_recovery_model.cbm"
)

METRICS_PATH = (
    ARTIFACT_DIRECTORY
    / "catboost_metrics.json"
)


def prepare_features(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    features = dataframe[MODEL_FEATURES].copy()

    for column in CATEGORICAL_FEATURES:
        features[column] = (
            features[column]
            .fillna("unknown")
            .astype(str)
        )

    for column in NUMERIC_FEATURES:
        median_value = features[column].median()

        features[column] = (
            features[column]
            .fillna(median_value)
            .astype(float)
        )

    return features


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

    training_features = prepare_features(
        training_data
    )

    validation_features = prepare_features(
        validation_data
    )

    test_features = prepare_features(test_data)

    training_target = training_data[TARGET_COLUMN]
    validation_target = validation_data[
        TARGET_COLUMN
    ]
    test_target = test_data[TARGET_COLUMN]

    model = CatBoostClassifier(
        iterations=700,
        depth=6,
        learning_rate=0.05,
        loss_function="Logloss",
        eval_metric="AUC",
        random_seed=42,
        l2_leaf_reg=5.0,
        random_strength=0.5,
        allow_writing_files=False,
        verbose=100,
    )

    print("\nTraining CatBoost...")

    model.fit(
        training_features,
        training_target,
        cat_features=CATEGORICAL_FEATURES,
        eval_set=(
            validation_features,
            validation_target,
        ),
        early_stopping_rounds=80,
        use_best_model=True,
    )

    validation_probabilities = (
        model.predict_proba(
            validation_features
        )[:, 1]
    )

    test_probabilities = model.predict_proba(
        test_features
    )[:, 1]

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

    feature_importances = {
        feature: round(float(importance), 6)
        for feature, importance in sorted(
            zip(
                MODEL_FEATURES,
                model.get_feature_importance(),
            ),
            key=lambda item: item[1],
            reverse=True,
        )
    }

    results: dict[str, Any] = {
        "model_name": "catboost_recovery_v1",
        "dataset": str(DATA_PATH),
        "data_source": "synthetic_v1",
        "features": MODEL_FEATURES,
        "categorical_features": (
            CATEGORICAL_FEATURES
        ),
        "split_strategy": (
            "chronological_70_15_15"
        ),
        "best_iteration": (
            model.get_best_iteration()
        ),
        "training_rows": len(training_data),
        "validation_rows": len(validation_data),
        "test_rows": len(test_data),
        "validation": validation_metrics,
        "test": test_metrics,
        "naive_test_baseline": naive_test_metrics,
        "feature_importances": feature_importances,
    }

    ARTIFACT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    model.save_model(str(MODEL_PATH))

    METRICS_PATH.write_text(
        json.dumps(
            results,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nCatBoost training completed")
    print(f"Model: {MODEL_PATH}")
    print(f"Metrics: {METRICS_PATH}")
    print(
        f"Best iteration: "
        f"{model.get_best_iteration()}"
    )

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

    print("\nTop feature importances:")

    for feature, importance in list(
        feature_importances.items()
    )[:10]:
        print(
            f"{feature:28s} {importance:.4f}"
        )


if __name__ == "__main__":
    main()