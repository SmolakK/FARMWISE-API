import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from API_readers.gios.gios_utils import generate_urls, fetch_and_parse, extract_data


def test_generate_urls():
    base_url = "https://example.com/page="
    start, end, step = 2, 10, 2

    expected_urls = [
        "https://example.com/page=02",
        "https://example.com/page=04",
        "https://example.com/page=06",
        "https://example.com/page=08",
        "https://example.com/page=10"
    ]

    result = generate_urls(base_url, start, end, step)
    assert result == expected_urls, "Generated URLs do not match expected output"


@patch("API_readers.gios.gios_utils.requests.get")
def test_fetch_and_parse(mock_get):
    # Mock a successful HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = "<html><body><span class='w1'>1</span><span class='w1'>Location</span></body></html>"
    mock_get.return_value = mock_response

    url = "https://example.com"
    result = fetch_and_parse(url)

    assert isinstance(result, BeautifulSoup), "Returned result is not a BeautifulSoup object"
    assert result.find("span", class_="w1").get_text(strip=True) == "1", "Parsed content is incorrect"


def test_extract_data():
    html_content = """
    <html>
        <body>
            <span class='w1'>1</span><span class='w1'>Location A</span>
            <span class='w1'>2</span><span class='w1'>Location B</span>
        </body>
    </html>
    """
    soup = BeautifulSoup(html_content, "html.parser")

    expected_data = [
        {"id": 1, "name": "Location A, Poland"},
        {"id": 2, "name": "Location B, Poland"}
    ]

    result = extract_data(soup)
    assert result == expected_data, "Extracted data does not match expected output"


@patch("API_readers.gios.gios_utils.requests.get")
def test_fetch_and_parse_failure(mock_get):
    # Mock a failed HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    url = "https://example.com"
    result = fetch_and_parse(url)

    assert result is None, "Failed request should return None"
