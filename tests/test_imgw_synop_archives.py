from farmwise_api.adapters.API_readers.imgw.imgw_api_synop_daily import (
    _select_synop_archives,
)


def test_selects_historical_station_archives():
    files = [
        "2025_100_s.zip",
        "2025_105_s.zip",
        "2025_115_s.zip",
    ]

    result = _select_synop_archives(
        files,
        {"100", "115"},
        ("2025-01-01", "2025-12-31"),
    )

    assert result == [
        "2025_100_s.zip",
        "2025_115_s.zip",
    ]


def test_selects_requested_month_from_new_layout():
    files = [
        "2026_01_s.zip",
        "2026_02_s.zip",
        "2026_03_s.zip",
    ]

    result = _select_synop_archives(
        files,
        {"100"},
        ("2026-02-10", "2026-02-20"),
    )

    assert result == [
        "2026_02_s.zip",
    ]


def test_selects_historical_multiyear_station_archive():
    files = [
        "1966_1970_100_s.zip",
        "1966_1970_105_s.zip",
    ]

    result = _select_synop_archives(
        files,
        {"105"},
        ("1967-01-01", "1967-12-31"),
    )

    assert result == [
        "1966_1970_105_s.zip",
    ]


def test_month_and_three_digit_station_are_not_confused():
    """`2025_10_s.zip` is October; `2025_100_s.zip` is station 100.

    The two layouts share a prefix, so the month pattern is constrained to
    01-12 and the station pattern to three or more digits. Without that, a
    month archive would be read as a station and silently skipped.
    """
    files = ["2025_10_s.zip", "2025_100_s.zip"]

    result = _select_synop_archives(files, {"100"}, ("2025-10-01", "2025-10-31"))

    assert result == ["2025_10_s.zip", "2025_100_s.zip"]


def test_month_outside_the_request_is_skipped_but_its_station_twin_is_not():
    """Only the month filter depends on the requested period."""
    files = ["2025_03_s.zip", "2025_300_s.zip"]

    result = _select_synop_archives(files, {"300"}, ("2025-07-01", "2025-07-31"))

    assert result == ["2025_300_s.zip"]


def test_all_stations_are_taken_when_no_preselection_applies():
    """An empty station set means the spatial pre-check kept everything."""
    files = ["2025_100_s.zip", "2025_105_s.zip"]

    result = _select_synop_archives(files, set(), ("2025-01-01", "2025-12-31"))

    assert result == files


def test_station_archives_are_not_filtered_by_the_requested_period():
    """The year comes from the folder, not the file name.

    Archives are listed per year folder (and per multi-year folder such as
    1966_1970), so the period has already been applied by the time this runs.
    Filtering again on the file name would drop every multi-year archive.
    """
    files = ["2025_100_s.zip"]

    result = _select_synop_archives(files, {"100"}, ("1990-01-01", "1990-12-31"))

    assert result == files


def test_files_that_are_not_synop_archives_are_ignored():
    files = ["2025_100_k.zip", "README.txt", "2025_100_s.zip"]

    result = _select_synop_archives(files, {"100"}, ("2025-01-01", "2025-12-31"))

    assert result == ["2025_100_s.zip"]


def test_an_unrecognised_synop_layout_is_kept_rather_than_dropped():
    """IMGW has changed this layout before; a new one must not vanish.

    Spatial filtering happens later against the station catalogue, so keeping
    an unknown `_s.zip` costs a download but never loses data silently.
    """
    files = ["2027_something_new_s.zip"]

    result = _select_synop_archives(files, {"100"}, ("2027-01-01", "2027-12-31"))

    assert result == files


def test_directory_prefixes_in_hrefs_are_handled():
    """Listing pages may give hrefs with a path."""
    files = ["/data/dobowe/synop/2026_02_s.zip"]

    result = _select_synop_archives(files, {"100"}, ("2026-02-10", "2026-02-20"))

    assert result == files

