from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from adapters.API_readers.EuroCropV2.utils import extractors as euro_extractors
from adapters.API_readers.EuroCropV2.utils import preparation as euro_preparation
from adapters.API_readers.IFSGRID.utils import extraction as ifs_extraction
from adapters.API_readers.IFSGRID.utils import preparation as ifs_preparation
from adapters.API_readers.correctiv.utils import extractors as correctiv_extractors
from adapters.API_readers.correctiv.utils import preparation as correctiv_preparation


def test_eurocrop_extract_data_by_bbox(tmp_path):
    csv_path = tmp_path / "points.csv"
    pd.DataFrame(
        {
            "lat": [50.0, 60.0],
            "lon": [17.0, 30.0],
            "c2024": [1, 2],
        }
    ).to_csv(csv_path, index=False)

    result = euro_extractors.extract_data_by_bbox(
        str(csv_path), (51.0, 49.0, 18.0, 16.0)
    )

    assert result["c2024"].tolist() == [1]


def test_eurocrop_extract_data_by_bbox_skips_truncated_rows(tmp_path):
    csv_path = tmp_path / "points.csv"
    csv_path.write_text(
        "id,area,lon,lat,c2024\n"
        "1,3.0,17.0,50.0,4\n"
        "2,,17.0\n"
        "3,5.0,30.0,60.0,8\n",
        encoding="utf-8",
    )

    result = euro_extractors.extract_data_by_bbox(
        str(csv_path), (51.0, 49.0, 18.0, 16.0)
    )

    assert result["id"].tolist() == [1]
    assert result["c2024"].tolist() == [4]


def test_eurocrop_extract_years_selects_requested_columns_and_nan():
    frame = pd.DataFrame(
        {
            "lon": [17.0],
            "lat": [50.0],
            "c2022": [None],
            "c2023": [2],
            "cf2024": [3],
            "other": [9],
        }
    )

    result = euro_extractors.extract_years(
        frame, ("2023-01-01", "2024-12-31")
    )

    assert result.columns.tolist() == ["lon", "lat", "c2023", "cf2024"]
    assert "other" not in result


def test_eurocrop_data_aggregation_uses_mode(monkeypatch):
    prepared = pd.DataFrame(
        {
            "S2CELL": ["cell", "cell", "cell"],
            "lat": [50.0, 50.0, 50.0],
            "lon": [17.0, 17.0, 17.0],
            "c2024": [2, 2, 3],
        }
    )
    monkeypatch.setattr(
        euro_preparation, "prepare_coordinates", lambda *_args: prepared
    )

    result = euro_preparation.data_agregation(
        pd.DataFrame(), (51.0, 49.0, 18.0, 16.0), 10
    )

    assert result.loc["cell", "c2024"] == 2


def test_eurocrop_data_melting_expands_year_to_requested_days():
    frame = pd.DataFrame(
        {
            "lon": [17.0],
            "lat": [50.0],
            "c2024": [2],
            "cf2024": [7],
        },
        index=pd.Index(["cell"], name="S2CELL"),
    )

    result = euro_preparation.data_melting(
        frame, ("2024-01-01", "2024-01-03")
    )

    assert result.index.tolist() == list(pd.date_range("2024-01-01", periods=3))
    assert result[("c", "cell")].tolist() == [2, 2, 2]
    assert result[("cf", "cell")].tolist() == [7, 7, 7]


def test_correctiv_time_filters_and_column_cleanup():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2023-11-01", "2023-12-01", "2024-01-01", "2024-03-01"]
            ),
            "latitude": [50.0] * 4,
            "longitude": [17.0] * 4,
            "min_gwl": ["1", "bad", "3", "4"],
            "mean_gwl": ["2", "3", "4", "5"],
            "max_gwl": ["3", "4", "5", "6"],
        }
    )

    wide = correctiv_extractors.time_extraction_wide(
        frame, ("2024-01-01", "2024-01-31")
    )
    cleaned = correctiv_extractors.cols_extraction(wide)
    exact = correctiv_extractors.time_extraction(
        cleaned, ("2024-01-01", "2024-01-31")
    )

    assert wide["date"].tolist() == list(
        pd.to_datetime(["2023-12-01", "2024-01-01"])
    )
    assert np.isnan(cleaned.iloc[0]["min_gwl"])
    assert exact["date"].tolist() == [pd.Timestamp("2024-01-01")]
    assert {"lat", "lon"}.issubset(cleaned.columns)


def test_correctiv_data_melting_expands_monthly_values():
    frame = pd.DataFrame(
        {
            "S2CELL": ["cell"],
            "date": pd.to_datetime(["2024-02-01"]),
            "min_gwl": [1.0],
            "mean_gwl": [2.0],
            "max_gwl": [3.0],
        }
    )

    result = correctiv_preparation.data_melting(frame)

    assert len(result) == 29
    assert result["date"].min() == pd.Timestamp("2024-02-01")
    assert result["date"].max() == pd.Timestamp("2024-02-29")
    assert result["mean_gwl"].eq(2.0).all()


@pytest.mark.parametrize(
    "period, expected",
    [
        (("2019-01-01", "2019-12-31"), (None, None)),
        (("2019-12-01", "2020-01-02"), (date(2020, 1, 1), date(2020, 1, 2))),
        (("2021-01-01", "2021-01-02"), (date(2021, 1, 1), date(2021, 1, 2))),
    ],
)
def test_ifsgrid_check_overlap(period, expected):
    assert ifs_preparation.check_overlap(period) == expected


def test_ifsgrid_build_bbox_uses_north_south_east_west_order():
    polygon = ifs_preparation.build_bbox((51.0, 49.0, 18.0, 16.0))

    assert polygon.bounds == (16.0, 49.0, 18.0, 51.0)


def test_ifsgrid_aggregate_spatial_groups_cells(monkeypatch):
    prepared = pd.DataFrame(
        {
            "S2CELL": ["cell", "cell"],
            "lat": [50.0, 50.1],
            "lon": [17.0, 17.1],
            "UAA": [2.0, 4.0],
        }
    )
    monkeypatch.setattr(
        ifs_preparation, "prepare_coordinates", lambda *_args: prepared
    )

    result = ifs_preparation.aggregate_spatial(
        pd.DataFrame(), (51.0, 49.0, 18.0, 16.0), 10
    )

    assert result.loc[0, "S2CELL"] == "cell"
    assert result.loc[0, "UAA"] == 3.0
    assert "lat" not in result


def test_ifsgrid_expand_time_dimension_creates_daily_pivot():
    frame = pd.DataFrame({"S2CELL": ["cell"], "UAA": [3.0]})

    result = ifs_preparation.expand_time_dimension(
        frame, date(2024, 1, 1), date(2024, 1, 3)
    )

    assert result.index.tolist() == list(pd.date_range("2024-01-01", periods=3))
    assert result[("UAA", "cell")].eq(3.0).all()


def test_ifsgrid_stack_values_merges_factors(monkeypatch):
    monkeypatch.setattr(
        ifs_extraction,
        "factor_mapping_extractor",
        lambda factor: {factor: f"{factor}.shp"},
    )

    def extract(_path, factor, _bbox):
        return pd.DataFrame(
            {"lat": [50.0], "lon": [17.0], factor: [len(factor)]}
        )

    monkeypatch.setattr(ifs_extraction, "extract_values", extract)

    result = ifs_extraction.stack_values(
        ["UAA", "ARA"], box(16.0, 49.0, 18.0, 51.0)
    )

    assert result.loc[0, "UAA"] == 3
    assert result.loc[0, "ARA"] == 3


def test_ifsgrid_extract_values_rejects_missing_feature(monkeypatch):
    monkeypatch.setattr(
        ifs_extraction.gpd,
        "read_file",
        MagicMock(return_value=pd.DataFrame({"geometry": []})),
    )

    with pytest.raises(ValueError, match="Column 'UAA'"):
        ifs_extraction.extract_values(
            "data.shp", "UAA", box(16.0, 49.0, 18.0, 51.0)
        )
