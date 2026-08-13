"""
Eagerly fetch large/remote adapter data ahead of time.

Usage
-----
    python fetch_data.py --all
    python fetch_data.py --source eea --source EuroCropV2

Run this in your Docker build or deployment startup script so a server's
first *request* never triggers a surprise multi-minute download mid-response.
For local/library use this is optional -- data fetches lazily on first use
of the relevant adapter otherwise.
"""

from __future__ import annotations

import argparse
import logging

from farmwise_api.core.utils.data_manifest import REMOTE_DATA
from farmwise_api.core.utils.paths import CACHE_ROOT, prefetch_all


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all", action="store_true", help="Fetch every entry in the manifest."
    )
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        help="Fetch only entries whose path contains this substring "
        "(e.g. 'eea'). Repeatable.",
    )
    parser.add_argument(
        "--list", action="store_true", help="List manifest entries and exit."
    )
    args = parser.parse_args()

    if args.list:
        for rel, entry in REMOTE_DATA.items():
            print(f"  {rel}  ({entry.get('size_mb', '?')} MB, {entry['kind']})")
        return

    if not args.all and not args.source:
        parser.error("pass --all, --source NAME, or --list")

    prefetch_all(sources=args.source)
    print(f"Done. Cached under {CACHE_ROOT}.")


if __name__ == "__main__":
    main()
