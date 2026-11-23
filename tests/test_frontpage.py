"""The web page submits a job and polls it instead of holding one request open."""

import asyncio

from farmwise_api.server.routers import frontpage


def _page_script() -> str:
    return asyncio.run(frontpage.secured_frontend_page()).body.decode()


def test_the_page_submits_an_async_job_that_emails_its_result():
    script = _page_script()

    assert "fetch('/read-data-direct'" in script
    assert "mode: 'async'" in script
    assert "notify_email: true" in script
    assert "fetch('/jobs/' + jobId" in script
    assert "fetch('/read-data'," not in script


def test_a_failure_is_reported_with_its_status_code_and_detail():
    """statusText is empty over HTTP/2 and for unusual codes, leaving a bare 'Error:'."""
    script = _page_script()

    assert "'Error: ' + response.statusText" not in script
    assert "'HTTP ' + response.status" in script
