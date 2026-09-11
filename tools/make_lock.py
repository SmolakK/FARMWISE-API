"""Regenerate requirements-lock.txt from the ranges in pyproject.toml.

The lock file pins the exact transitive closure of the runtime, server and dev
dependencies, each with a SHA-256 hash, for one target platform. It records
the environment the published results and the CI runs were produced in;
`pyproject.toml` keeps the supported ranges for ordinary library use.

Usage (from the repository root):

    python tools/make_lock.py

Resolution is performed by pip for the target interpreter and platform below,
so the lock can be produced from any machine - including a Windows checkout
targeting the Linux environment CI uses.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "requirements-lock.txt"

# The environment the lock describes. Keep in step with the CI `locked` job.
TARGET_PYTHON = "3.12"
TARGET_PLATFORMS = ("manylinux_2_28_x86_64", "manylinux2014_x86_64")
TARGET_LABEL = "linux x86_64 (manylinux_2_28)"

# Extras included in the lock: what `pip install ".[server,dev]"` installs.
LOCKED_EXTRAS = ("server", "dev")


def declared_requirements() -> list[str]:
    """Return the dependency specifiers the lock should cover."""
    project = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    specs = list(project["dependencies"])
    for extra in LOCKED_EXTRAS:
        specs.extend(project["optional-dependencies"][extra])
    return specs


def resolve(specs: list[str]) -> dict:
    """Ask pip to resolve `specs` for the target platform, without installing."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        req_file = tmp_path / "requirements.in"
        req_file.write_text("\n".join(specs), encoding="utf-8")
        report_file = tmp_path / "report.json"

        command = [
            sys.executable, "-m", "pip", "install",
            "--dry-run", "--quiet",
            "--report", str(report_file),
            "--python-version", TARGET_PYTHON,
            "--only-binary", ":all:",
            "--target", str(tmp_path / "unused"),
            "-r", str(req_file),
        ]
        for platform in TARGET_PLATFORMS:
            command += ["--platform", platform]

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            sys.stderr.write(result.stdout + result.stderr)
            raise SystemExit(
                "pip could not resolve the declared ranges for Python "
                f"{TARGET_PYTHON} on {TARGET_LABEL}."
            )
        return json.loads(report_file.read_text(encoding="utf-8"))


def sha256_of(item: dict) -> str | None:
    archive = item.get("download_info", {}).get("archive_info") or {}
    digest = (archive.get("hashes") or {}).get("sha256")
    if digest:
        return digest
    legacy = archive.get("hash", "")
    return legacy.split("=", 1)[1] if legacy.startswith("sha256=") else None


def render(report: dict) -> str:
    packages = sorted(
        ((i["metadata"]["name"], i["metadata"]["version"], sha256_of(i))
         for i in report["install"]),
        key=lambda row: row[0].lower(),
    )
    unhashed = [name for name, _, digest in packages if not digest]
    if unhashed:
        raise SystemExit(
            "no SHA-256 recorded for: " + ", ".join(unhashed)
            + " - cannot write a verifiable lock file."
        )

    header = [
        "# FARMWISE-API pinned environment",
        "#",
        "# Exact transitive closure of the runtime, server and dev extras -",
        "# the same set CI installs. Generated from the bounded ranges in",
        "# pyproject.toml by tools/make_lock.py. Do not edit by hand.",
        "#",
        f"#   Python   : {TARGET_PYTHON}",
        f"#   Platform : {TARGET_LABEL}",
        f"#   Packages : {len(packages)}",
        f"#   Generated: {date.today().isoformat()}",
        "#",
        "# Install exactly this environment:",
        "#",
        "#   python -m pip install --require-hashes -r requirements-lock.txt",
        "#   python -m pip install -e . --no-deps",
        "#",
        "# The hashes identify specific wheels, so this file installs only on",
        "# the platform above; that is what makes it reproducible. On another",
        "# platform install from pyproject.toml's ranges instead.",
        "",
    ]
    body = []
    for name, version, digest in packages:
        body.append(f"{name.lower()}=={version} \\")
        body.append(f"    --hash=sha256:{digest}")
    return "\n".join(header + body) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUT,
        help="lock file to write (default: %(default)s)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="exit non-zero if the lock file is out of date, writing nothing",
    )
    args = parser.parse_args()

    text = render(resolve(declared_requirements()))

    if args.check:
        current = (args.output.read_text(encoding="utf-8")
                   if args.output.exists() else "")
        # the Generated: line changes every day; compare the pins only
        def pins(blob: str) -> list[str]:
            return [ln for ln in blob.splitlines() if not ln.startswith("#")]
        if pins(current) != pins(text):
            raise SystemExit(
                f"{args.output.name} is out of date; run tools/make_lock.py"
            )
        print(f"{args.output.name} is up to date")
        return

    args.output.write_text(text, encoding="utf-8")
    count = sum(1 for ln in text.splitlines() if ln.endswith(" \\"))
    print(f"wrote {args.output} ({count} packages pinned)")


if __name__ == "__main__":
    main()
