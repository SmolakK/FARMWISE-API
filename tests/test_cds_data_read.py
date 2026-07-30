from unittest.mock import MagicMock

import pandas as pd

from adapters.API_readers.cds.cds_utils import cds_data_read


def test_cds_read_data_builds_request_and_converts_temperature(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(cds_data_read.cdsapi, "Client", MagicMock(return_value=client))
    source = pd.DataFrame(
        {
            "valid_time": pd.to_datetime(["2024-01-01T00:00:00"]),
            "latitude": [50.0],
            "longitude": [17.0],
            "expver": [1],
            "number": [0],
            "t2m": [280.0],
        }
    )
    dataset = MagicMock()
    dataset.to_dataframe.return_value = source
    monkeypatch.setattr(
        cds_data_read.xr, "open_dataset", MagicMock(return_value=dataset)
    )

    def prepare(frame, _spatial_range, _level):
        return frame.assign(S2CELL="cell")

    monkeypatch.setattr(cds_data_read, "prepare_coordinates", prepare)

    result = cds_data_read.cds_read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2024-01-01", "2024-01-01"),
        ["temperature"],
        5,
        "dataset-name",
    )

    request = client.retrieve.call_args.args[1]
    assert request["variable"] == ["2m_temperature"]
    assert request["year"] == ["2024"]
    assert request["month"] == ["01"]
    assert request["day"] == ["01"]
    assert request["area"] == [51.0, 16.0, 49.0, 18.0]
    assert result.iloc[0, 0] == 280.0 - 273.15
