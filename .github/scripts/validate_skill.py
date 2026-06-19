#!/usr/bin/env python3
"""
Validate an agentskills.io skill against the specification.

Usage:
    python validate_skill.py PATH/TO/SKILL.md
    python validate_skill.py             # validates argo-rollouts/SKILL.md by default

Checks (per https://agentskills.io/specification.md):
  * File uses YAML frontmatter delimited by `---` lines.
  * `name` is present, matches ^[a-z0-9]+(-[a-z0-9]+)*$ , and is <= 64 chars.
  * `name` equals the basename of its parent directory.
  * `description` is present, non-empty, and <= 1024 chars.
  * `compatibility`, if present, is <= 500 chars.
  * `metadata`, if present, is a mapping of str -> str.
  * Body (after frontmatter) is < 500 lines (recommendation, treated as a rule).

Exits 1 on any violation (messages on stderr), 0 if clean.
Dependency-free: ships a tiny YAML-subset parser as a fallback when PyYAML
is unavailable, because CI installs PyYAML but a fresh checkout may not have it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Tiny YAML frontmatter parser (fallback only — PyYAML preferred).
# Handles the subset agentskills.io actually uses: top-level scalars, a single
# nested `metadata:` mapping, and quoted or unquoted values.
# --------------------------------------------------------------------------- #
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def _parse_yaml_frontmatter(text: str) -> "dict[str, object]":
    try:
        import yaml  # type: ignore

        m = _FRONTMATTER_RE.match(text)
        if not m:
            raise ValueError("no YAML frontmatter block found")
        data = yaml.safe_load(m.group(1))
        if not isinstance(data, dict):
            raise ValueError("frontmatter did not parse to a mapping")
        return data
    except Exception:
        # Fall back to a hand-rolled parser for the spec subset.
        return _fallback_parse(text)


def _fallback_parse(text: str) -> "dict[str, object]":
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("no YAML frontmatter block found")
    out: dict[str, object] = {}
    current_key: str | None = None
    for raw in m.group(1).splitlines():
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        sub = re.match(r"^(\S+):\s*(.*)$", line)
        if not sub:
            if current_key is not None and line.startswith("  "):
                # Nested metadata entry: "  key: value"
                kv = re.match(r"^\s+(\S+):\s*(.*)$", line)
                if kv:
                    container = out.setdefault(current_key, {})
                    if isinstance(container, dict):
                        container[kv.group(1)] = _coerce(kv.group(2))
            continue
        key, val = sub.group(1), sub.group(2)
        if val == "":
            # Either an empty value or a nested mapping header (e.g. `metadata:`).
            # Peek: if the next non-blank line is indented, treat as a mapping.
            current_key = key
            out.setdefault(key, {})
        else:
            current_key = key
            out[key] = _coerce(val)
    return out


def _coerce(raw: str) -> object:
    s = raw.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.lower() in {"true", "false"}:
        return s.lower() == "true"
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_coerce(part.strip()) for part in inner.split(",")]
    return s


# --------------------------------------------------------------------------- #
# Validators
# --------------------------------------------------------------------------- #
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESC = 1024
MAX_COMPAT = 500
MAX_BODY_LINES = 500


def validate(skill_path: Path) -> list[str]:
    """Return a list of human-readable violation strings (empty = clean)."""
    violations: list[str] = []

    if not skill_path.is_file():
        return [f"{skill_path}: not a file"]

    text = skill_path.read_text(encoding="utf-8")

    # Frontmatter presence + split
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return [f"{skill_path}: missing YAML frontmatter (expected leading '---\\n...\\n---')"]
    fm_text, body = m.group(1), text[m.end():]

    try:
        fm = _parse_yaml_frontmatter(text)
    except ValueError as exc:
        return [f"{skill_path}: frontmatter parse error: {exc}"]

    # `name`
    name = fm.get("name")
    if name is None:
        violations.append("frontmatter: `name` is required")
    elif not isinstance(name, str):
        violations.append(f"frontmatter: `name` must be a string, got {type(name).__name__}")
    else:
        if not NAME_RE.match(name):
            violations.append(
                f"frontmatter: `name` ({name!r}) must match {NAME_RE.pattern} "
                "(lowercase alphanumerics + single hyphens; no leading/trailing/consecutive hyphens)"
            )
        if len(name) > MAX_NAME:
            violations.append(f"frontmatter: `name` length {len(name)} exceeds {MAX_NAME} chars")
        # name must equal parent directory basename
        parent_basename = skill_path.parent.name
        if name != parent_basename:
            violations.append(
                f"frontmatter: `name` ({name!r}) must equal its parent directory "
                f"name ({parent_basename!r}) per the agentskills.io spec"
            )

    # `description`
    desc = fm.get("description")
    if desc is None:
        violations.append("frontmatter: `description` is required")
    elif not isinstance(desc, str) or not desc.strip():
        violations.append("frontmatter: `description` must be a non-empty string")
    elif len(desc) > MAX_DESC:
        violations.append(
            f"frontmatter: `description` length {len(desc)} exceeds {MAX_DESC} chars"
        )

    # `license` is recommended and we want it for this repo
    lic = fm.get("license")
    if lic is None:
        violations.append("frontmatter: `license` is recommended (this repo uses MIT)")

    # `compatibility` optional
    compat = fm.get("compatibility")
    if compat is not None:
        if not isinstance(compat, str):
            violations.append(
                f"frontmatter: `compatibility` must be a string, got {type(compat).__name__}"
            )
        elif len(compat) > MAX_COMPAT:
            violations.append(
                f"frontmatter: `compatibility` length {len(compat)} exceeds {MAX_COMPAT} chars"
            )

    # `metadata` optional mapping[str,str]
    meta = fm.get("metadata")
    if meta is not None:
        if not isinstance(meta, dict):
            violations.append(
                f"frontmatter: `metadata` must be a mapping, got {type(meta).__name__}"
            )
        else:
            for k, v in meta.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    violations.append(
                        f"frontmatter: `metadata` entries must be str -> str; "
                        f"key {k!r} -> {v!r} violates that"
                    )

    # `allowed-tools` optional but if present, string or list of strings
    tools = fm.get("allowed-tools") or fm.get("allowed_tools")
    if tools is not None and not isinstance(tools, (str, list)):
        violations.append(
            f"frontmatter: `allowed-tools` must be a string or list, got {type(tools).__name__}"
        )

    # Body length recommendation treated as a rule
    body_lines = len(body.splitlines())
    if body_lines > MAX_BODY_LINES:
        violations.append(
            f"body: {body_lines} lines exceeds {MAX_BODY_LINES}-line recommendation"
        )

    return violations


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        skill_path = Path(argv[1])
    else:
        # Default: <repo-root>/argo-rollouts/SKILL.md
        skill_path = Path(__file__).resolve().parents[2] / "argo-rollouts" / "SKILL.md"

    violations = validate(skill_path)
    if not violations:
        print(f"OK: {skill_path} conforms to agentskills.io spec", file=sys.stderr)
        return 0
    print(f"FAIL: {skill_path} violates agentskills.io spec:", file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
