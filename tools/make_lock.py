"""Regenerate requirements-lock.txt from the ranges in pyproject.toml.

The lock is a *universal* resolution: one file that installs on Linux, macOS
and Windows, because every entry carries the environment markers that decide
where it applies. That matters here because the dependency set is not the same
everywhere - `uvicorn[standard]` pulls `uvloop` off Windows, `tqdm` pulls
`colorama` on Windows - so a lock resolved for one platform is wrong on the
other.

Resolution is done by uv. pip cannot do this: `pip install --platform` selects
wheel *tags* but still evaluates environment markers against the interpreter
it is running on, so a cross-platform lock built with pip silently describes
the machine that generated it.

Usage (from the repository root):

    python tools/make_lock.py            # rewrite the lock
    python tools/make_lock.py --check    # fail if the lock is out of date

Output is byte-identical on every platform, so the --check run in CI agrees
with a lock generated on a developer machine.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "requirements-lock.txt"

# Resolve for the lowest supported interpreter so the lock covers the whole
# supported range. Left implicit, uv would target whichever interpreter
# happens to be running and bake that assumption into the markers.
TARGET_PYTHON = "3.11"

# Extras included in the lock: what `pip install ".[server,dev]"` installs.
LOCKED_EXTRAS = ("server", "dev")

# Lines uv writes recording its own invocation. They embed the -o path, which
# differs between a real run and a --check run, so they are excluded from the
# comparison rather than being allowed to cause false drift.
HEADER_LINES = 2


def compile_lock(destination: Path) -> None:
    """Run uv's universal resolver, writing a fresh lock to `destination`."""
    if destination.exists():
        # uv reuses hashes found in an existing output file. Starting from a
        # stale file therefore produces a lock with fewer hashes than a clean
        # run, and two machines disagree. Always resolve from scratch.
        destination.unlink()

    command = [
        sys.executable, "-m", "uv", "pip", "compile",
        "pyproject.toml",                 # relative: keeps absolute paths out
        "--universal",                    # one lock for every platform
        "--generate-hashes",
        "--python-version", TARGET_PYTHON,
        "-o", str(destination),
    ]
    for extra in LOCKED_EXTRAS:
        command += ["--extra", extra]

    result = subprocess.run(
        command, cwd=REPO_ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(
            "uv could not resolve the declared ranges. Install it with "
            "`python -m pip install uv` if it is missing."
        )


def bodies_match(left: Path, right: Path) -> bool:
    """Compare two locks, ignoring uv's record of its own command line."""
    def body(path: Path) -> list[str]:
        return path.read_text(encoding="utf-8").splitlines()[HEADER_LINES:]
    return body(left) == body(right)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="exit non-zero if the lock is out of date, writing nothing",
    )
    args = parser.parse_args()
    lock = REPO_ROOT / LOCK_NAME

    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / LOCK_NAME
            compile_lock(candidate)
            if not lock.exists():
                raise SystemExit(f"{LOCK_NAME} is missing; run tools/make_lock.py")
            if not bodies_match(lock, candidate):
                raise SystemExit(
                    f"{LOCK_NAME} is out of date; run tools/make_lock.py"
                )
        print(f"{LOCK_NAME} is up to date")
        return

    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / LOCK_NAME
        compile_lock(candidate)
        # Replace uv's record of its own command line: it contains the
        # temporary output path, which is machine-specific noise and leaks a
        # local directory into a published file.
        body = candidate.read_text(encoding="utf-8").splitlines()[HEADER_LINES:]
        header = [
            "# Universal dependency lock for FARMWISE-API. Do not edit by hand.",
            "# Regenerate with: python tools/make_lock.py",
        ]
        # newline="" keeps LF endings on Windows too: the lock is compared
        # byte-for-byte against a Linux regeneration in CI.
        with open(lock, "w", encoding="utf-8", newline="") as handle:
            handle.write("\n".join(header + body) + "\n")

    pinned = sum(
        1 for line in lock.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith((" ", "#"))
    )
    print(f"wrote {lock} ({pinned} packages pinned, universal)")


if __name__ == "__main__":
    main()
