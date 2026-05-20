#!/usr/bin/env python3
"""Prepare HTCondor job lists and submit files.

The defaults provide a generic two-argument job contract:

    executable $(input_file) $(run_dir)

Use --executable, --arguments, and optional --job-arg NAME=VALUE queue columns
to adapt this to a specific worker script.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from inputs import (
    inputs_from_local_dir,
    inputs_from_pfn_list,
    inputs_from_rucio,
)
from jobs import (
    DEFAULT_ARGUMENTS,
    DEFAULT_QUEUE_VARS,
    parse_job_arg,
    write_job_list,
)
from submit import SubmitConfig, render_submit_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HTCondor queue input and submit files for generic jobs"
    )

    input_group = parser.add_argument_group("input source")
    input_group.add_argument(
        "--input_dir",
        type=Path,
        nargs="?",
        help="Local directory containing input files",
    )
    input_group.add_argument(
        "--local-pattern",
        default="*.pool.root*",
        help="Glob pattern for --input_dir (default: *.pool.root*)",
    )
    input_group.add_argument(
        "--pfn-list",
        type=Path,
        help="Text file with one PFN/input path per line",
    )
    input_group.add_argument(
        "--rucio-dataset",
        type=str,
        help="Rucio dataset identifier, e.g. scope:name",
    )
    input_group.add_argument(
        "--rse",
        type=str,
        help="Rucio RSE name to restrict replicas, e.g. PRAGUELCG2_LOCALGROUPDISK",
    )

    job_group = parser.add_argument_group("job list")
    job_group.add_argument(
        "--runs-base",
        type=Path,
        default=Path("./runs"),
        help="Base directory for per-job run directories (default: ./runs)",
    )
    job_group.add_argument(
        "--job-arg",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Add a constant queue column available as $(NAME). Repeatable.",
    )
    job_group.add_argument(
        "--output-joblist",
        type=Path,
        default=Path("job_list.txt"),
        help="Output job list file (default: job_list.txt)",
    )

    submit_group = parser.add_argument_group("submit file")
    submit_group.add_argument(
        "--write-submit",
        action="store_true",
        help="Write an HTCondor submit file",
    )
    submit_group.add_argument(
        "--submit-file",
        type=Path,
        default=Path("submit_derivation.sub"),
        help="Path for generated submit file (default: submit_derivation.sub)",
    )
    submit_group.add_argument(
        "--executable",
        default="run_single_derivation.sh",
        help="Condor executable to run (default: run_single_derivation.sh)",
    )
    submit_group.add_argument(
        "--arguments",
        default=DEFAULT_ARGUMENTS,
        help=(
            "Condor arguments line. Use queue macros like $(input_file), "
            "$(run_dir), or extra --job-arg names."
        ),
    )
    submit_group.add_argument(
        "--transfer-input-files",
        default="",
        help="Comma-separated files Condor should transfer to the worker",
    )
    submit_group.add_argument(
        "--transfer-output-files",
        default='""',
        help='Condor transfer_output_files value (default: "")',
    )
    submit_group.add_argument(
        "--condor-log",
        type=Path,
        default=Path("condor.log"),
        help="Path for the condor log file (default: condor.log)",
    )
    submit_group.add_argument(
        "--job-flavour",
        default="workday",
        help='HTCondor +JobFlavour value (default: "workday")',
    )
    submit_group.add_argument(
        "--request-cpus",
        type=int,
        default=1,
        help="Requested CPUs per job (default: 1)",
    )
    submit_group.add_argument(
        "--request-memory",
        default="4GB",
        help="Requested memory per job (default: 4GB)",
    )
    submit_group.add_argument(
        "--request-disk",
        default="20GB",
        help="Requested disk per job (default: 20GB)",
    )
    submit_group.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="Condor max_retries value (default: 1)",
    )
    submit_group.add_argument(
        "--no-x509-proxy",
        action="store_true",
        help="Do not add x509userproxy to the submit file",
    )
    submit_group.add_argument(
        "--submit",
        action="store_true",
        help="Automatically submit the generated submit file",
    )
    return parser.parse_args()


def resolve_inputs(args: argparse.Namespace):
    sources = [bool(args.rucio_dataset), bool(args.pfn_list), bool(args.input_dir)]
    if sum(sources) != 1:
        print(
            "ERROR: provide exactly one input source: --rucio-dataset, --pfn-list, or --input_dir",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.rucio_dataset:
        return inputs_from_rucio(args.rucio_dataset, args.rse)
    if args.pfn_list:
        return inputs_from_pfn_list(args.pfn_list)
    return inputs_from_local_dir(args.input_dir, args.local_pattern)


def main() -> None:
    args = parse_args()
    inputs = resolve_inputs(args)
    extra_job_args = dict(parse_job_arg(value) for value in args.job_arg)
    reserved_names = set(DEFAULT_QUEUE_VARS)
    duplicate_names = reserved_names.intersection(extra_job_args)
    if duplicate_names:
        duplicate_list = ", ".join(sorted(duplicate_names))
        print(
            f"ERROR: --job-arg cannot override built-in queue columns: {duplicate_list}",
            file=sys.stderr,
        )
        sys.exit(2)

    queue_vars = write_job_list(
        inputs=inputs,
        runs_base=args.runs_base,
        output_joblist=args.output_joblist,
        extra_job_args=extra_job_args,
    )

    print(f"Generated {len(inputs)} jobs")
    print(f"Job list written to: {args.output_joblist}")
    print(f"Queue columns: {', '.join(queue_vars)}")

    submit_path = args.submit_file
    should_write_submit = args.write_submit or args.submit
    if should_write_submit:
        submit_text = render_submit_file(
            SubmitConfig(
                executable=args.executable,
                arguments=args.arguments,
                job_list=args.output_joblist.resolve(),
                queue_vars=queue_vars,
                transfer_input_files=args.transfer_input_files,
                transfer_output_files=args.transfer_output_files,
                job_flavour=args.job_flavour,
                request_cpus=args.request_cpus,
                request_memory=args.request_memory,
                request_disk=args.request_disk,
                max_retries=args.max_retries,
                condor_log=str(args.condor_log),
                x509userproxy="" if args.no_x509_proxy else "$ENV(X509_USER_PROXY)",
            )
        )
        submit_path.write_text(submit_text, encoding="utf-8")
        print(f"Submit file written to: {submit_path}")

    if args.submit:
        subprocess.run(["condor_submit", str(submit_path)], check=True)
    elif should_write_submit:
        print("\nTo submit:")
        print(f"\n  condor_submit {submit_path}\n")


if __name__ == "__main__":
    main()
