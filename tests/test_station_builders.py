from unittest.mock import MagicMock

import pandas as pd
import pytest

from adapters.API_readers.gios import gios_api_stations
from adapters.API_readers.imgw import imgw_api_stations
from adapters.API_readers.imgw_hydro import imgw_hydro_stations_api


def test_gios_station_builder_geocodes_and_writes_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(gios_api_stations, "generate_urls", lambda _url: ["page"])
    monkeypatch.setattr(gios_api_stations, "fetch_and_parse", lambda _url: object())
    monkeypatch.setattr(
        gios_api_stations,
        "extract_data",
        lambda _soup: [{"id": 1, "name": "Wroclaw, Poland"}],
    )
    monkeypatch.setattr(
        gios_api_stations, "get_coordinates", lambda _name: (51.1, 17.0)
    )
    output = tmp_path / "gios" / "stations.csv"

    result = gios_api_stations.build_station_file(output)

    assert result.loc[0, ["lat", "lon"]].tolist() == [51.1, 17.0]
    assert output.is_file()
    assert "coordinates" not in pd.read_csv(output).columns


def test_gios_station_builder_does_not_write_empty_result(monkeypatch, tmp_path):
    monkeypatch.setattr(gios_api_stations, "generate_urls", lambda _url: ["page"])
    monkeypatch.setattr(gios_api_stations, "fetch_and_parse", lambda _url: None)
    output = tmp_path / "stations.csv"

    result = gios_api_stations.build_station_file(output)

    assert result.empty
    assert not output.exists()


@pytest.mark.parametrize(
    "module, csv_text, expected_code",
    [
        (imgw_api_stations, "123,Wroclaw,value\n", 123),
        (imgw_hydro_stations_api, "Wroclaw,456,value\n", 456),
    ],
)
def test_imgw_station_builders(monkeypatch, tmp_path, module, csv_text, expected_code):
    response = MagicMock(text=csv_text)
    get = MagicMock(return_value=response)
    monkeypatch.setattr(module.requests, "get", get)
    monkeypatch.setattr(module, "get_coordinates", lambda _name: (51.1, 17.0))
    output = tmp_path / module.__name__.split(".")[-1] / "stations.csv"

    result = module.build_station_file(output)

    assert result.loc[0, "Code"] == expected_code
    assert result.loc[0, "Name"] == "Wroclaw,Poland"
    assert result.loc[0, ["lat", "lon"]].tolist() == [51.1, 17.0]
    assert output.is_file()
    get.assert_called_once_with(module.URL, timeout=60)
    response.raise_for_status.assert_called_once_with()
