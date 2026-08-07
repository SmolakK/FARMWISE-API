import pandas as pd
import pytest

from adapters.API_readers.quadica import quadica_read
from adapters.API_readers.quadica.mappings.quadica_mappings import GLOBAL_MAPPING
from adapters.API_readers.quadica.utils import extractors, preparation


def _assign_one_cell(frame, _spatial_range, _level):
    return frame.assign(S2CELL="cell")


def test_requested_data_files_deduplicates_multi_factor_tables():
    selected = extractors.requested_data_files(
        ["surface water quantity", "surface water quantity", "temperature"]
    )

    assert "tavg_monthly_with_coords.csv" in selected
    assert "q_annual_with_coords.csv" in selected
    assert "c_annual_with_coords.csv" in selected
    assert "wrtds_monthly_with_coords_date_merged.csv" in selected
    assert len(selected["tavg_monthly_with_coords.csv"]) == 1


def test_monthly_horizontal_extraction_keeps_native_months(monkeypatch, tmp_path):
    path = tmp_path / "pre_monthly_with_coords.csv"
    pd.DataFrame(
        {
            "OBJECTID": [1],
            "lat": [50.0],
            "lon": [10.0],
            "2014-01-01": [31.0],
            "2014-02-01": [28.0],
            "2014-03-01": [99.0],
        }
    ).to_csv(path, index=False)
    monkeypatch.setattr(extractors, "prepare_coordinates", _assign_one_cell)

    result = extractors.monthly_horizontal_extraction(
        path,
        (55.1, 47.3, 15.0, 6.0),
        ("2014-01-01", "2014-02-28"),
        10,
    )

    assert result["date"].tolist() == list(
        pd.to_datetime(["2014-01-01", "2014-02-01"])
    )
    assert result["pre"].tolist() == [31.0, 28.0]
    assert len(result) == 2


def test_monthly_extraction_returns_empty_for_bbox_without_stations(
    monkeypatch, tmp_path
):
    path = tmp_path / "tavg_monthly_with_coords.csv"
    pd.DataFrame(
        {
            "OBJECTID": [1],
            "lat": [60.0],
            "lon": [20.0],
            "2014-01-01": [5.0],
        }
    ).to_csv(path, index=False)
    monkeypatch.setattr(extractors, "prepare_coordinates", _assign_one_cell)

    result = extractors.monthly_horizontal_extraction(
        path,
        (55.1, 47.3, 15.0, 6.0),
        ("2014-01-01", "2014-01-31"),
        10,
    )

    assert result.empty


def test_yearly_extraction_uses_one_timestamp_per_year(monkeypatch, tmp_path):
    path = tmp_path / "q_annual_with_coords.csv"
    pd.DataFrame(
        {
            "OBJECTID": [1, 1],
            "Year": [2013, 2014],
            "lat": [50.0, 50.0],
            "lon": [10.0, 10.0],
            "n_Qdaily": [10, 12],
            "median_Qdaily": [2.0, 3.0],
        }
    ).to_csv(path, index=False)
    monkeypatch.setattr(extractors, "prepare_coordinates", _assign_one_cell)

    result = extractors.year_vertical_extraction(
        path,
        ["n_Qdaily", "median_Qdaily"],
        (55.1, 47.3, 15.0, 6.0),
        ("2014-01-01", "2014-12-31"),
        10,
    )

    assert result["date"].tolist() == [pd.Timestamp("2014-01-01")]
    assert result["median_Qdaily"].tolist() == [3.0]


def test_quadica_aggregation_sums_counts_and_applies_type_policy():
    frame = pd.DataFrame(
        {
            "OBJECTID": [1, 2],
            "date": pd.to_datetime(["2014-01-01", "2014-01-01"]),
            "S2CELL": ["cell", "cell"],
            "n_NO3": [2, 3],
            "median_NO3N": [1.0, 101.0],
        }
    )

    result = preparation.data_aggregation(
        frame,
        ["surface water quality"],
        {"default": "mean", "surface water quality": "median"},
    )

    row = result.loc[("cell", pd.Timestamp("2014-01-01"))]
    assert row["n_NO3"] == 5
    assert row["median_NO3N"] == 51.0


def test_multi_factor_values_returns_empty_when_all_fragments_are_empty(
    monkeypatch
):
    monkeypatch.setattr(
        preparation,
        "combined_extractions",
        lambda *_args, **_kwargs: pd.DataFrame(),
    )

    result = preparation.multi_factor_values(
        {"tavg_monthly_with_coords.csv": "unused.csv"},
        ["temperature"],
        (55.1, 47.3, 15.0, 6.0),
        ("2014-01-01", "2014-02-28"),
        10,
    )

    assert result.empty


def test_pivoting_uses_unique_records_without_hidden_mean():
    index = pd.MultiIndex.from_tuples(
        [("cell", pd.Timestamp("2014-01-01"))],
        names=["S2CELL", "Timestamp"],
    )
    aggregated = pd.DataFrame({"median_Qdaily": [3.0]}, index=index)

    result = preparation.pivoting_table(aggregated)

    assert result.loc[pd.Timestamp("2014-01-01"), ("median_Qdaily", "cell")] == 3.0


@pytest.mark.asyncio
async def test_read_data_resolves_local_resource_and_preserves_monthly_units(
    monkeypatch, tmp_path
):
    path = tmp_path / "tavg_monthly_with_coords.csv"
    pd.DataFrame(
        {
            "OBJECTID": [1],
            "lat": [50.0],
            "lon": [10.0],
            "2014-01-01": [1.0],
            "2014-02-01": [2.0],
        }
    ).to_csv(path, index=False)
    resolved = []

    def adapter_data(*parts):
        resolved.append(parts)
        return path

    monkeypatch.setattr(quadica_read, "adapter_data", adapter_data)
    monkeypatch.setattr(extractors, "prepare_coordinates", _assign_one_cell)

    result = await quadica_read.read_data(
        (55.1, 47.3, 15.0, 6.0),
        ("2014-01-01", "2014-02-28"),
        ["temperature"],
        10,
    )

    assert resolved == [("quadica", "data", "tavg_monthly_with_coords.csv")]
    assert result.index.tolist() == list(
        pd.to_datetime(["2014-01-01", "2014-02-01"])
    )
    assert result.columns.tolist() == [
        ("Monthly Median Air Temperature [°C]", "cell")
    ]
    assert result.iloc[:, 0].tolist() == [1.0, 2.0]


def test_quadica_mapping_preserves_source_units_and_statistic_names():
    assert GLOBAL_MAPPING["pre"].endswith("[mm/month]")
    assert GLOBAL_MAPPING["pet"].endswith("[mm/month]")
    assert GLOBAL_MAPPING["median_Qdaily"].startswith("Median ")
