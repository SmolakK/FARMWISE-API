"""The CORINE nomenclature must stay consistent and match what is returned."""

import pytest

from farmwise_api.adapters.API_readers.corine.corine_mappings import corine_mapping as clc
from farmwise_api.adapters.API_readers.corine import corine_read


def test_nomenclature_has_the_full_44_class_set():
    """CLC defines 44 level-3 classes; a short list means one was dropped."""
    assert len(clc.CLC_CLASSES) == 44


def test_every_code_is_a_valid_three_level_code():
    for code, label in clc.CLC_CLASSES.items():
        assert 111 <= code <= 523, f"{code} is outside the CLC code range"
        digits = str(code)
        assert len(digits) == 3, f"{code} is not a three-digit level-3 code"
        assert digits[0] in "12345", f"{code} has no valid level-1 digit"
        assert "0" not in digits, f"{code} contains a zero digit"
        assert label and label[0].isupper(), f"{code} has a suspect label"


def test_hierarchy_lookups_agree_with_the_code_digits():
    """level_1/level_2 must be derivable from every level-3 code."""
    for code in clc.CLC_CLASSES:
        assert clc.level_1(code) is not None, f"no level-1 label for {code}"
        assert clc.level_2(code) is not None, f"no level-2 label for {code}"

    # and no orphaned parent labels
    used_level_1 = {code // 100 for code in clc.CLC_CLASSES}
    used_level_2 = {code // 10 for code in clc.CLC_CLASSES}
    assert set(clc.CLC_LEVEL_1) == used_level_1
    assert set(clc.CLC_LEVEL_2) == used_level_2


@pytest.mark.parametrize(
    "code, expected",
    [
        (211, "Non-irrigated arable land"),
        (231, "Pastures"),
        (312, "Coniferous forest"),
        (523, "Sea and ocean"),
    ],
)
def test_known_codes_resolve(code, expected):
    """Spot-checks against the published legend, including codes the live
    adapter returned for a test area in Thuringia (211 and 231)."""
    assert clc.describe(code) == expected


def test_describe_rejects_unknown_and_malformed_codes():
    assert clc.describe(999) is None
    assert clc.describe("not a code") is None
    assert clc.describe(None) is None
    assert clc.level_1(999) is None
    assert clc.level_2(999) is None


def test_string_codes_resolve_like_integers():
    """The feature layer stores codes as 3-character strings."""
    assert clc.describe("211") == clc.describe(211)
    assert clc.level_1("211") == "Agricultural areas"
    assert clc.level_2("211") == "Arable land"


def test_adapter_declares_a_field_for_every_snapshot():
    """Every snapshot the adapter offers must have a class field configured."""
    assert set(corine_read.CLASS_FIELDS) == set(corine_read.AVAILABLE_SNAPSHOTS)
    for snapshot, field in corine_read.CLASS_FIELDS.items():
        assert field.casefold() == f"code_{str(snapshot)[2:]}", (
            f"CLC{snapshot} field {field!r} does not follow the Code_YY pattern"
        )


def test_snapshot_periods_are_contiguous_and_ordered():
    """Each survey must carry forward exactly until the next one begins."""
    from datetime import date

    periods = list(
        corine_read._snapshot_periods(date(1990, 1, 1), date(2020, 12, 31))
    )
    assert [p[0] for p in periods] == list(corine_read.AVAILABLE_SNAPSHOTS)
    for (_, _, earlier_end), (_, later_start, _) in zip(periods, periods[1:]):
        assert (later_start - earlier_end).days == 1, (
            "snapshots must tile the timeline without gaps or overlaps"
        )


def test_request_before_the_first_survey_yields_nothing():
    from datetime import date

    assert list(
        corine_read._snapshot_periods(date(1980, 1, 1), date(1985, 1, 1))
    ) == []
