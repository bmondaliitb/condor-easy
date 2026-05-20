"""Input discovery for HTCondor job preparation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import subprocess
import sys
from urllib.parse import urlparse


@dataclass(frozen=True)
class InputItem:
    """One resolved input and a filesystem-safe name for its run directory."""

    path: str
    run_name: str


def inputs_from_local_dir(input_dir: Path, pattern: str) -> list[InputItem]:
    if not input_dir.is_dir():
        print(f"ERROR: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    inputs = sorted(input_dir.glob(pattern))
    if not inputs:
        print(f"No files matching {pattern!r} found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    return [
        InputItem(path=str(input_file.absolute()), run_name=input_file.stem)
        for input_file in inputs
    ]


def inputs_from_pfn_list(path: Path) -> list[InputItem]:
    with open(path, "r", encoding="utf-8") as handle:
        lines = [line.strip() for line in handle]

    pfns = [line for line in lines if line and not line.startswith("#")]
    if not pfns:
        print(f"No PFNs found in {path}", file=sys.stderr)
        sys.exit(5)

    return [InputItem(path=pfn, run_name=safe_name_from_input(pfn)) for pfn in pfns]


def inputs_from_rucio(dataset: str, rse: str | None = None) -> list[InputItem]:
    cmd = ["rucio", "list-file-replicas", "--pfns"]
    if rse:
        cmd += ["--rse", rse]
    cmd += [dataset]

    try:
        proc = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        print("ERROR: rucio is not configured", file=sys.stderr)
        sys.exit(3)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: rucio command failed: {exc.stderr}", file=sys.stderr)
        sys.exit(3)

    pfn_regex = re.compile(r"(?:root|http|https|srm|gsiftp)://\S+")
    pfns = pfn_regex.findall(proc.stdout)
    if not pfns:
        print(f"No PFNs found in rucio output for {dataset}", file=sys.stderr)
        sys.exit(4)

    return [InputItem(path=pfn, run_name=safe_name_from_input(pfn)) for pfn in pfns]


def safe_name_from_input(input_path: str) -> str:
    parsed = urlparse(input_path)
    name = os.path.basename(parsed.path)
    if not name:
        name = re.sub(r"[^A-Za-z0-9_.-]+", "_", input_path)
    return name
