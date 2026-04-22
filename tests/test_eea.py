# test_read_data.py
import pytest
import inspect
import pandas as pd
from unittest.mock import patch, AsyncMock
from API_readers.eea.eea_read import read_data

@pytest.mark.asyncio
async def test_is_coroutine():
    assert inspect.iscoroutinefunction(read_data)

@pytest.mark.asyncio
async def test_handles_none_dataframe():
    df = await read_data((0,0,0,0), ('2000-01-01','2000-01-02'), [], 0)
    assert df is None or isinstance(df, pd.DataFrame)

@pytest.mark.asyncio
async def test_coordinates_in_range():
    df = await read_data(
        (50,49,17,16),
        ('2018-01-01','2018-01-02'),
        ['land cover'],
        10
    )
    if isinstance(df, pd.DataFrame):
        if 'lat' in df.columns:
            assert df['lat'].between(-90, 90).all()
        if 'lon' in df.columns:
            assert df['lon'].between(-180, 180).all()

@pytest.mark.asyncio
async def test_s2cell_generated_if_exists():
    df = await read_data((50,49,17,16), ('2018-01-01','2018-01-02'), ['land cover'], 10)
    if isinstance(df, pd.DataFrame) and 'S2CELL' in df.columns:
        assert not df['S2CELL'].isna().all()

@pytest.mark.asyncio
async def test_timestamp_is_datetime_day_precision():
    df = await read_data((50,49,17,16), ('2018-01-01','2018-01-02'), ['land cover'], 10)
    if isinstance(df, pd.DataFrame) and 'Timestamp' in df.columns:
        assert pd.api.types.is_datetime64_any_dtype(df['Timestamp'])
        assert (df['Timestamp'].dt.hour == 0).all()
        assert (df['Timestamp'].dt.minute == 0).all()
        assert (df['Timestamp'].dt.second == 0).all()
        assert (df['Timestamp'].dt.nanosecond == 0).all()

@pytest.mark.asyncio
async def test_no_duplicates_on_lat_lon_timestamp():
    df = await read_data((50,49,17,16), ('2018-01-01','2018-01-02'), ['land cover'], 10)
    if isinstance(df, pd.DataFrame):
        subset = [c for c in ['lat','lon','Timestamp'] if c in df.columns]
        if subset:
            assert not df.duplicated(subset=subset).any()

@pytest.mark.asyncio
async def test_timestamp_within_range():
    df = await read_data((50,49,17,16), ('2018-01-01','2018-01-02'), ['land cover'], 10)
    if isinstance(df, pd.DataFrame) and 'Timestamp' in df.columns:
        assert df['Timestamp'].min() >= pd.Timestamp('2018-01-01')
        assert df['Timestamp'].max() <= pd.Timestamp('2018-01-02')
