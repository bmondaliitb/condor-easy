"""Build queue files for generic HTCondor jobs."""

from __future__ import annotations

from pathlib import Path
import sys

from inputs import InputItem


DEFAULT_QUEUE_VARS = ["input_file", "run_dir"]
DEFAULT_ARGUMENTS = "$(input_file) $(run_dir)"


def parse_job_arg(value: str) -> tuple[str, str]:
    if "=" not in value:
        print(f"ERROR: --job-arg must be NAME=VALUE, got {value!r}", file=sys.stderr)
        sys.exit(2)

    name, arg_value = value.split("=", 1)
    if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
        print(f"ERROR: invalid job argument name {name!r}", file=sys.stderr)
        sys.exit(2)
    if any(char.isspace() for char in arg_value):
        print(
            "ERROR: --job-arg values cannot contain whitespace because Condor queue "
            f"rows are whitespace-delimited: {name}={arg_value!r}",
            file=sys.stderr,
        )
        sys.exit(2)

    return name, arg_value


def write_job_list(
    *,
    inputs: list[InputItem],
    runs_base: Path,
    output_joblist: Path,
    extra_job_args: dict[str, str] | None = None,
) -> list[str]:
    runs_base.mkdir(parents=True, exist_ok=True)
    extra_job_args = extra_job_args or {}
    queue_vars = DEFAULT_QUEUE_VARS + list(extra_job_args)

    with open(output_joblist, "w", encoding="utf-8") as handle:
        for item in inputs:
            run_dir = runs_base / item.run_name
            run_dir.mkdir(parents=True, exist_ok=True)
            values = {
                "input_file": item.path,
                "run_dir": str(run_dir.absolute()),
                **extra_job_args,
            }
            handle.write(" ".join(values[name] for name in queue_vars) + "\n")

    return queue_vars
