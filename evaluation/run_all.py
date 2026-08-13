"""Collect all live empirical inputs used by the evaluation notebooks.

The analysis itself lives in the notebooks.  This module is intentionally a
small convenience entry point: running it executes the request, cross-source,
and live-scaling scenarios configured in :mod:`evaluation.scenarios` and
writes the raw artifacts under ``evaluation/empirical_input``.
"""

from __future__ import annotations

import asyncio

from evaluation.collect_empirical import OUTPUT_DIR, collect


def run_all() -> dict:
    """Run the complete empirical collection with the configured defaults."""
    return asyncio.run(collect())


def main() -> None:
    """Collect raw data and print the paths consumed by the notebooks."""
    result = run_all()
    print(
        f"Collected {result['request_count']} live requests and "
        f"{result['observation_count']} cross-source observations in "
        f"{OUTPUT_DIR}."
    )


if __name__ == "__main__":
    main()
