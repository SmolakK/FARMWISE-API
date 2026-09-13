"""Collect all live empirical inputs used by the evaluation notebooks.

The analysis itself lives in :mod:`evaluation.analysis` and the notebook.
This module is intentionally a small convenience entry point: running it
executes the experiments configured in :mod:`evaluation.scenarios` and writes
one frozen collection under ``evaluation/empirical_input/<collection-id>``.

Unlike ``python -m evaluation.collect_empirical``, it does not acknowledge the
IMGW research-use terms, so IMGW sources are only included when that gate is
already open in the environment.
"""

from __future__ import annotations

import asyncio

from evaluation.collect_empirical import collect


def run_all() -> dict:
    """Run the complete empirical collection with the configured defaults."""
    return asyncio.run(collect())


def main() -> None:
    """Collect raw data and print the paths consumed by the notebooks."""
    result = run_all()
    print(
        f"Collected {result['request_count']} measured requests and "
        f"{result['observation_count']} cross-source observations in "
        f"{result['collection_dir']}."
    )


if __name__ == "__main__":
    main()
