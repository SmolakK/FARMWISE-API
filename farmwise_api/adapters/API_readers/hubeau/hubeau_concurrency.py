"""Bounded fan-out for the Hub'Eau adapters.

One request is issued per monitoring point. Launching them all at once made
Hub'Eau answer 503 for most of them, and a country-sized request then timed
out after 600 s with no data.

The unbounded fan-out also starved the rest of the process: each fetch runs in
``asyncio.to_thread``, which shares one default executor of about 32 workers,
so thousands of queued fetches delayed every other threaded task. A quality
assessment that takes under a second was measured at 605 s behind such a queue.
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace
from typing import Awaitable, Callable, Sequence, TypeVar

import requests

from farmwise_api._vendor.hubeaupyutils import hubeau as _vendored_client

logger = logging.getLogger(__name__)

T = TypeVar("T")

# The right limit differs per endpoint, measured on a one-degree French box
# over one month:
#
#   piezometry (many quick requests):  3 -> 124.7 s,  6 -> 6.7 s
#   groundwater quality (few slow ones): 3 -> 126.2 s, 6 -> 122.1 s
#
# So piezometry needs the wider limit to finish at all, while the quality
# endpoints gain nothing from it and draw more refusals (5 at 6, 1 at 2), which
# is why they pass the narrower limit below. The retries further down recover
# whatever is still refused.
DEFAULT_CONCURRENCY = 6
QUALITY_CONCURRENCY = 3


async def gather_points(
    fetch: Callable[[str], Awaitable[T]],
    point_ids: Sequence[str],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[T]:
    """Fetch every point with at most ``concurrency`` requests in flight.

    :param fetch: coroutine function called with one point identifier.
    :param point_ids: identifiers to fetch, in the order results are returned.
    :param concurrency: maximum number of simultaneous requests.
    :return: one result per identifier, in the order given.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    limit = asyncio.Semaphore(concurrency)

    async def guarded(point_id: str) -> T:
        async with limit:
            return await fetch(point_id)

    return list(await asyncio.gather(*(guarded(point_id) for point_id in point_ids)))


# ---------------------------------------------------------------- retries

# Hub'Eau answers 503 under load. The vendored client prints the status and
# returns an empty frame, so the adapter cannot tell a refused point from one
# with no data, and the point disappears from the result without a trace.
# Retrying at the HTTP layer keeps that distinction inside the client.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1.5
# The vendored client passes no timeout, so a stalled connection held a worker
# thread until the operating system gave up. Measured over repeated runs, that
# produced a bimodal distribution: the same request took either ~4 s or ~124 s,
# at every concurrency limit, which is the hang rather than the throughput.
# Hub'Eau occasionally accepts a connection and never answers: one run in six
# stalled in a repeated measurement, costing the whole timeout before the retry
# succeeded in under a second. Filtered queries return in about 1 s and the
# largest legitimate answer (a full page of results) in under 20 s, so the read
# budget sits between the two: long enough for a slow page, short enough that a
# stall does not dominate the request. Connecting is separate and quick.
CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 45
REQUEST_TIMEOUT_SECONDS = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)


def _retrying_get(url, *args, **kwargs):
    """``requests.get`` with a timeout and bounded retries.

    Retries the statuses Hub'Eau uses for overload, and connection or read
    timeouts. Called inside a worker thread, so sleeping here does not block
    the event loop. Only the vendored client's reference to ``requests`` is
    replaced, so no other adapter's HTTP behaviour changes.
    """
    kwargs.setdefault("timeout", REQUEST_TIMEOUT_SECONDS)
    response = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, *args, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
            if attempt == MAX_ATTEMPTS:
                logger.warning(
                    "Hub'Eau request failed after %d attempts (%s); "
                    "this point contributes no data", MAX_ATTEMPTS, error,
                )
                raise
            logger.info("Hub'Eau request failed (%s); retrying (%d/%d)",
                        error, attempt, MAX_ATTEMPTS - 1)
            time.sleep(BACKOFF_SECONDS * attempt)
            continue
        if response.status_code not in RETRY_STATUSES:
            return response
        if attempt < MAX_ATTEMPTS:
            logger.info(
                "Hub'Eau returned %s; retrying (%d/%d)",
                response.status_code, attempt, MAX_ATTEMPTS - 1,
            )
            time.sleep(BACKOFF_SECONDS * attempt)
    logger.warning(
        "Hub'Eau still returned %s after %d attempts; this point contributes no data",
        getattr(response, "status_code", "no response"), MAX_ATTEMPTS,
    )
    return response


# Installed once at import: the vendored module keeps its own reference to the
# requests module, so replacing it here leaves the real requests untouched.
_vendored_client.requests = SimpleNamespace(
    get=_retrying_get,
    JSONDecodeError=requests.JSONDecodeError,
    exceptions=requests.exceptions,
)


# ---------------------------------------------------------------- result cap

# Hub'Eau serves at most 20 000 results per query and refuses the "next" link
# beyond that with HTTP 400, so a larger area cannot be fetched in one
# bounding-box query: it would return the first page and silently drop the
# rest. Requests above this threshold fall back to one query per monitoring
# point, which stays well inside the cap.
MAX_BBOX_RESULTS = 18_000


def count_results(url: str, params: dict) -> int | None:
    """Ask Hub'Eau how many results a query would return.

    Costs one small request (``size=1``, ~0.2 s) and decides whether the
    bounding-box query can return the complete answer.

    :return: the number of results, or None when the probe fails - the caller
        then chooses the safe path rather than assuming a small answer.
    """
    # Hub'Eau expects repeated values comma-joined in one parameter. Passing a
    # list makes requests repeat the parameter instead, which the service reads
    # differently: the probe then counts a different query from the one the
    # adapter runs, and could report a small number for a query that is far
    # above the cap.
    probe = {
        key: ",".join(str(item) for item in value)
        if isinstance(value, (list, tuple, set)) else value
        for key, value in params.items()
        if value is not None
    }
    probe["size"] = 1
    try:
        response = _retrying_get(url, params=probe)
        if response is None or response.status_code not in (200, 206):
            logger.warning(
                "Hub'Eau count probe returned %s for %s",
                getattr(response, "status_code", "no response"), url,
            )
            return None
        return int(response.json().get("count"))
    except Exception as error:  # noqa: BLE001 - the caller falls back
        logger.warning("Hub'Eau count probe failed for %s: %s", url, error)
        return None
