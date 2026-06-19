# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""CLI generator for Argo Rollouts ``AnalysisTemplate`` manifests.

Thin wrapper over :func:`rollout_lib.build_analysis_template`. Run with
``--help`` for the full flag reference, or see ``scripts/README.md``.

Self-contained: ``uv run scripts/gen_analysis.py ...`` installs PyYAML
automatically. Fallback: ``python3 scripts/gen_analysis.py`` with PyYAML
installed. Exit codes: 0 = success, 2 = bad arguments/values.
"""

from __future__ import annotations

import argparse
import sys

from rollout_lib import ANALYSIS_PROVIDERS, build_analysis_template, emit_yaml, parse_arg


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for ``gen_analysis``."""
    p = argparse.ArgumentParser(
        prog="gen_analysis.py",
        description="Generate an Argo Rollouts AnalysisTemplate manifest as YAML.",
    )
    p.add_argument("--name", required=True, help="AnalysisTemplate name.")
    p.add_argument("--provider", choices=list(ANALYSIS_PROVIDERS), required=True, help="Metric provider.")
    p.add_argument("--query", help="Provider query string (required for prometheus/graphite/influxdb/datadog).")
    p.add_argument("--address", help="Server URL for prometheus/graphite/influxdb, e.g. http://prometheus:9090.")
    p.add_argument("--success", dest="success", help="successCondition expression, e.g. 'result[0] >= 0.95'.")
    p.add_argument("--failure", dest="failure", help="failureCondition expression (optional).")
    p.add_argument("--failure-limit", type=int, default=0, dest="failure_limit", help="failureLimit (default: 0).")
    p.add_argument("--consecutive-success-limit", type=int, default=0, dest="consecutive_success_limit", help="consecutiveSuccessLimit (default: 0 = disabled).")
    p.add_argument("--interval", help="Go duration between evaluations, e.g. '5m'.")
    p.add_argument("--count", type=int, help="Number of evaluations before the metric terminates.")
    p.add_argument("--metric-name", default="success-rate", dest="metric_name", help="Name of the metric (default: success-rate).")
    p.add_argument("--arg", action="append", default=[], dest="args_raw", metavar="NAME=VALUE", help="Template arg (repeatable).")
    p.add_argument("--output", default="-", help="Output file path or '-' for stdout (default: -).")
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        parsed_args = [parse_arg(s) for s in args.args_raw]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        doc = build_analysis_template(
            name=args.name,
            provider=args.provider,
            query=args.query,
            address=args.address,
            success=args.success,
            failure=args.failure,
            failure_limit=args.failure_limit,
            consecutive_success_limit=args.consecutive_success_limit,
            interval=args.interval,
            count=args.count,
            metric_name=args.metric_name,
            args=parsed_args,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    text = emit_yaml(doc)
    if args.output == "-":
        sys.stdout.write(text)
    else:
        with open(args.output, "w") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
