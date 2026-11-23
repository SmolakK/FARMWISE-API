from farmwise_api.core.utils.country_bboxes import (
    EUROPE_EAST_LIMIT,
    return_country_bboxes,
)


def test_russia_is_cut_at_the_urals():
    north, south, east, west = return_country_bboxes()["Russian Federation"]

    assert east == EUROPE_EAST_LIMIT == 60.0
    assert west < 20  # Kaliningrad stays in
    assert north > south


def test_no_country_box_reaches_past_the_urals():
    boxes = return_country_bboxes()

    assert all(east <= EUROPE_EAST_LIMIT for _, _, east, _ in boxes.values())
    # Countries well inside the limit are unchanged.
    assert boxes["Poland"][2] < 25
