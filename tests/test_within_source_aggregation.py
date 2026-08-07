import pandas as pd
import pytest

from core.within_source_aggregation import (
    aggregate_to_s2,
    validate_within_source_methods,
)


def test_aggregate_to_s2_selects_method_per_data_type():
    frame = pd.DataFrame(
        {
            "S2CELL": ["cell", "cell", "cell"],
            "Timestamp": pd.to_datetime(["2024-01-01"] * 3),
            "Temperature [C]": [10.0, 20.0, 30.0],
            "Land cover": ["forest", "field", "forest"],
        }
    )

    result = aggregate_to_s2(
        frame,
        logical_data_types=("temperature", "land cover"),
        methods={
            "default": "mean",
            "temperature": "median",
            "land cover": "mode",
        },
        warn_on_aggregation=False,
    )

    assert result.iloc[0]["Temperature [C]"] == 20.0
    assert result.iloc[0]["Land cover"] == "forest"


def test_aggregate_to_s2_supports_column_metadata_overrides():
    frame = pd.DataFrame(
        {
            "S2CELL": ["cell", "cell"],
            "Timestamp": pd.to_datetime(["2024-01-01"] * 2),
            "point_id": [1, 2],
            "lat": [50.0, 52.0],
            "value": [1.0, 9.0],
        }
    )

    result = aggregate_to_s2(
        frame,
        logical_data_types=("soil",),
        methods={"default": "median", "soil": "median"},
        column_aggregations={"point_id": "nunique", "lat": "mean"},
        warn_on_aggregation=False,
    )

    assert result.iloc[0].to_dict() == {
        "point_id": 2.0,
        "lat": 51.0,
        "value": 5.0,
    }


def test_aggregate_to_s2_uses_explicit_column_data_types():
    frame = pd.DataFrame(
        {
            "S2CELL": ["cell"] * 3,
            "Timestamp": pd.to_datetime(["2024-01-01"] * 3),
            "opaque_numeric_code": [1.0, 3.0, 100.0],
            "opaque_category_code": [2, 2, 7],
        }
    )

    result = aggregate_to_s2(
        frame,
        logical_data_types=("temperature", "land cover"),
        methods={
            "default": "max",
            "temperature": "median",
            "land cover": "mode",
        },
        column_data_types={
            "opaque_numeric_code": "temperature",
            "opaque_category_code": "land cover",
        },
        warn_on_aggregation=False,
    )

    assert result.iloc[0]["opaque_numeric_code"] == 3.0
    assert result.iloc[0]["opaque_category_code"] == 2


def test_aggregate_to_s2_warns_only_when_rows_are_collapsed():
    frame = pd.DataFrame(
        {
            "S2CELL": ["cell", "cell"],
            "Timestamp": pd.to_datetime(["2024-01-01"] * 2),
            "value": [1.0, 3.0],
        }
    )

    with pytest.warns(UserWarning, match="Some data were aggregated"):
        aggregate_to_s2(
            frame,
            logical_data_types=("custom",),
            methods={"default": "mean"},
        )


def test_validate_within_source_methods_rejects_cross_source_weighting():
    with pytest.raises(ValueError, match="Unknown within-source aggregation"):
        validate_within_source_methods({"temperature": "weighted_mean"})
