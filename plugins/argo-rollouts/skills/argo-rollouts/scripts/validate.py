# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""CLI validator for Argo Rollouts manifests.

Usage::

    validate.py FILE [FILE ...]

Loads each YAML file (multi-doc safe), dispatches by ``kind`` to
:func:`rollout_lib.validate_rollout` or :func:`rollout_lib.validate_analysis`,
prints errors to stderr in the form ``FILE: kind: <message>``, and exits 0
if everything is valid or 1 if any error was found.

Self-contained: ``uv run scripts/validate.py ...`` installs PyYAML
automatically. Exit codes: 0 = valid, 1 = validation errors found,
2 = usage error (no files).
"""

from __future__ import annotations

import sys

from rollout_lib import load_yaml, validate_analysis, validate_rollout


def _validate_doc(path: str, doc: dict) -> list[str]:
    """Dispatch one doc to the right validator; return formatted error lines."""
    kind = doc.get("kind", "<unknown>")
    if kind == "Rollout":
        errs = validate_rollout(doc)
    elif kind == "AnalysisTemplate":
        errs = validate_analysis(doc)
    else:
        return [
            f"{path}: {kind}: unknown kind "
            "(expected 'Rollout' or 'AnalysisTemplate')"
        ]
    return [f"{path}: {kind}: {msg}" for msg in errs]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    files = argv if argv is not None else sys.argv[1:]
    if not files:
        print("usage: validate.py FILE [FILE ...]", file=sys.stderr)
        return 2

    exit_code = 0
    for path in files:
        try:
            docs = list(load_yaml(path))
        except FileNotFoundError:
            print(f"{path}: file not found", file=sys.stderr)
            exit_code = 1
            continue
        except OSError as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        if not docs:
            print(f"{path}: no YAML documents found", file=sys.stderr)
            exit_code = 1
            continue

        for doc in docs:
            if not isinstance(doc, dict):
                print(f"{path}: document is not a mapping", file=sys.stderr)
                exit_code = 1
                continue
            errs = _validate_doc(path, doc)
            for line in errs:
                print(line, file=sys.stderr)
            if errs:
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
