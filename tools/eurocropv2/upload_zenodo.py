"""Create a Zenodo draft and upload a prepared EuroCropsV2 deposit.

Publishing is never automatic unless ``--publish`` is supplied explicitly.
The access token is read only from ``ZENODO_TOKEN``.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import requests


def _request(response: requests.Response) -> dict:
    if not response.ok:
        raise RuntimeError(
            f"Zenodo API returned HTTP {response.status_code}: {response.text}"
        )
    return response.json() if response.content else {}


def upload_deposit(
    *,
    metadata_path: Path,
    upload_list_path: Path,
    token: str,
    sandbox: bool = False,
    deposition_id: int | None = None,
    publish: bool = False,
) -> dict:
    base = "https://sandbox.zenodo.org" if sandbox else "https://zenodo.org"
    api = f"{base}/api/deposit/depositions"
    headers = {"Authorization": f"Bearer {token}"}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    files = [
        Path(line.strip())
        for line in upload_list_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Upload files are missing: {missing}")

    if deposition_id is None:
        deposit = _request(requests.post(api, headers=headers, json={}, timeout=60))
        deposition_id = int(deposit["id"])
    else:
        deposit = _request(
            requests.get(f"{api}/{deposition_id}", headers=headers, timeout=60)
        )

    deposit = _request(
        requests.put(
            f"{api}/{deposition_id}",
            headers={**headers, "Content-Type": "application/json"},
            json={"metadata": metadata},
            timeout=60,
        )
    )
    bucket_url = deposit["links"]["bucket"]
    for path in files:
        print(f"Uploading {path.name} ({path.stat().st_size:,} bytes)...")
        with path.open("rb") as handle:
            _request(
                requests.put(
                    f"{bucket_url}/{path.name}",
                    headers=headers,
                    data=handle,
                    timeout=(30, None),
                )
            )

    if publish:
        deposit = _request(
            requests.post(
                f"{api}/{deposition_id}/actions/publish",
                headers=headers,
                timeout=60,
            )
        )
    else:
        deposit = _request(
            requests.get(f"{api}/{deposition_id}", headers=headers, timeout=60)
        )
    return deposit


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--upload-list", type=Path, required=True)
    parser.add_argument("--deposition-id", type=int)
    parser.add_argument("--sandbox", action="store_true")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish after upload. Without this flag the record remains a draft.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        raise RuntimeError("Set ZENODO_TOKEN; never put the token in a file or command.")
    deposit = upload_deposit(
        metadata_path=args.metadata,
        upload_list_path=args.upload_list,
        token=token,
        sandbox=args.sandbox,
        deposition_id=args.deposition_id,
        publish=args.publish,
    )
    print(f"Zenodo deposition ID: {deposit['id']}")
    print(f"State: {deposit.get('state', 'unknown')}")
    print(f"URL: {deposit.get('links', {}).get('html', 'not available')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
