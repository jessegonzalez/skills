"""Shared helpers for Argo Rollouts manifest generation and validation.

This module is the single source of truth used by the three CLI scripts
(``gen_rollout.py``, ``gen_analysis.py``, ``validate.py``) and by the test
suite. Importing from here gives you:

- :func:`build_rollout` / :func:`build_analysis_template` -- construct a
  manifest dict from kwargs (no I/O).
- :func:`validate_rollout` / :func:`validate_analysis` -- return a list of
  human-readable error strings (empty == valid).
- :func:`emit_yaml` / :func:`load_yaml` -- deterministic serialization and
  safe multi-doc loading.
- :func:`parse_steps` / :func:`parse_arg` -- parsers for the
  ``--steps`` and ``--arg`` CLI syntax.

The YAML output uses ``sort_keys=False`` and ``default_flow_style=False`` so
manifests are deterministic and diff cleanly under GitOps.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Canonical apiVersion for every Argo Rollouts CRD we emit.
API_VERSION = "argoproj.io/v1alpha1"

#: Allowed values for ``--strategy``.
STRATEGIES = ("canary", "bluegreen")

#: Allowed values for ``--traffic-routing``.
TRAFFIC_ROUTERS = ("none", "istio", "nginx", "alb", "smi")

#: Known canary step keys (one per step item). A step must contain exactly one.
STEP_KEYS = frozenset({
    "setWeight",
    "pause",
    "analysis",
    "experiment",
    "setCanaryScale",
    "setHeaderRoute",
    "setMirrorRoute",
    "plugin",
    "replicaProgressThreshold",
})

#: Analysis providers that take an ``address`` + ``query`` shape.
ADDRESS_PROVIDERS = frozenset({"prometheus", "graphite", "influxdb"})

#: All accepted AnalysisTemplate providers.
ANALYSIS_PROVIDERS = (
    "prometheus",
    "datadog",
    "wavefront",
    "newrelic",
    "cloudwatch",
    "graphite",
    "influxdb",
    "kayenta",
    "job",
    "web",
)


# ---------------------------------------------------------------------------
# YAML I/O helpers
# ---------------------------------------------------------------------------


def emit_yaml(doc: Any) -> str:
    """Serialize a manifest dict to deterministic YAML.

    Output is stable across runs (``sort_keys=False``,
    ``default_flow_style=False``) so manifests diff cleanly.
    """
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)


def load_yaml(path: str | os.PathLike[str]) -> Iterator[dict]:
    """Yield non-null YAML documents from ``path`` (multi-doc safe).

    Empty documents (e.g. the trailing ``---`` separator) are skipped so
    validators only see real manifests.
    """
    with open(path) as f:
        for doc in yaml.safe_load_all(f):
            if doc is not None:
                yield doc


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_steps(spec: str) -> list[dict]:
    """Parse a ``--steps`` string into a list of canary step dicts.

    Grammar (comma-separated chunks)::

        "<weight> <duration>"   -> [{setWeight: <int>}, {pause: {duration: <str>}}]
        "<weight>"              -> [{setWeight: <int>}]
        "<duration>"            -> [{pause: {duration: <str>}]]

    Whitespace inside a chunk is collapsed; empty chunks are ignored.
    Raises :class:`ValueError` on a chunk that does not match.
    """
    steps: list[dict] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        tokens = chunk.split()
        if len(tokens) == 2:
            weight_tok, duration = tokens
            if not weight_tok.lstrip("-").isdigit():
                raise ValueError(
                    f"invalid step {chunk!r}: first token must be an integer weight"
                )
            steps.append({"setWeight": int(weight_tok)})
            steps.append({"pause": {"duration": duration}})
        elif len(tokens) == 1:
            tok = tokens[0]
            if tok.lstrip("-").isdigit():
                steps.append({"setWeight": int(tok)})
            else:
                steps.append({"pause": {"duration": tok}})
        else:
            raise ValueError(
                f"invalid step {chunk!r}: expected '<weight> <duration>'"
            )
    return steps


def parse_arg(s: str) -> tuple[str, str]:
    """Parse a ``NAME=VALUE`` string into a ``(name, value)`` tuple.

    Raises :class:`ValueError` if no ``=`` is present. The value may be empty
    (``NAME=``); use this when the value should come from a Rollout arg.
    """
    if "=" not in s:
        raise ValueError(f"invalid --arg {s!r}; expected NAME=VALUE")
    name, _, value = s.partition("=")
    return name, value


# ---------------------------------------------------------------------------
# Rollout builder
# ---------------------------------------------------------------------------


def _coerce_routes(routes: Any) -> list[str] | None:
    """Normalize ``--routes`` input into a list of route names."""
    if routes is None:
        return None
    if isinstance(routes, str):
        items = [r.strip() for r in routes.split(",")]
        return [r for r in items if r]
    return [str(r) for r in routes]


def _is_zero(value: Any) -> bool:
    """True if ``value`` represents integer zero (string or int)."""
    if value is None:
        return False
    if isinstance(value, int):
        return value == 0
    if isinstance(value, str):
        return value.strip() == "0"
    return False


def build_rollout(
    *,
    name: str,
    image: str,
    replicas: int = 1,
    namespace: str | None = None,
    port: int = 8080,
    strategy: str = "canary",
    steps: str | list[dict] | None = None,
    traffic_routing: str = "none",
    stable_service: str | None = None,
    canary_service: str | None = None,
    active_service: str | None = None,
    preview_service: str | None = None,
    virtual_service: str | None = None,
    routes: str | list[str] | None = None,
    analysis_template: str | None = None,
    starting_step: int | None = None,
    manual_gate: bool = False,
    max_surge: str | int | None = None,
    max_unavailable: str | int | None = None,
) -> dict:
    """Build an Argo Rollouts ``Rollout`` manifest as a dict.

    All parameters match the CLI flags (underscores instead of dashes).
    Raises :class:`ValueError` with a clear message on contradictory input
    (e.g. traffic-routing set without a stable/canary service, blue-green
    without an active service, or ``maxSurge`` and ``maxUnavailable`` both
    zero). The returned dict serializes cleanly via :func:`emit_yaml`.
    """
    # ---- validate ---------------------------------------------------------
    if not name:
        raise ValueError("--name is required")
    if not image:
        raise ValueError("--image is required")
    if strategy not in STRATEGIES:
        raise ValueError(
            f"--strategy must be one of {STRATEGIES!r}, got {strategy!r}"
        )
    if traffic_routing not in TRAFFIC_ROUTERS:
        raise ValueError(
            f"--traffic-routing must be one of {TRAFFIC_ROUTERS!r}, "
            f"got {traffic_routing!r}"
        )

    use_traffic = traffic_routing != "none"
    if use_traffic:
        if strategy != "canary":
            raise ValueError(
                f"--traffic-routing requires --strategy canary, got {strategy!r}"
            )
        if not stable_service:
            raise ValueError(
                f"--stable-service is required when --traffic-routing={traffic_routing!r}"
            )
        if not canary_service:
            raise ValueError(
                f"--canary-service is required when --traffic-routing={traffic_routing!r}"
            )
        if traffic_routing == "istio" and not virtual_service:
            raise ValueError(
                "--virtual-service is required when --traffic-routing=istio"
            )

    if strategy == "bluegreen" and not active_service:
        raise ValueError("--active-service is required when --strategy=bluegreen")

    if _is_zero(max_surge) and _is_zero(max_unavailable):
        raise ValueError(
            "--max-surge and --max-unavailable cannot both be 0 "
            "(k8s requires at least one to allow progress)"
        )

    # ---- metadata ---------------------------------------------------------
    metadata: dict = {"name": name}
    if namespace:
        metadata["namespace"] = namespace
    metadata["labels"] = {"app": name}

    # ---- pod template -----------------------------------------------------
    container = {
        "name": name,
        "image": image,
        "ports": [{"containerPort": port}],
    }
    template = {
        "metadata": {"labels": {"app": name}},
        "spec": {"containers": [container]},
    }

    # ---- strategy ---------------------------------------------------------
    if strategy == "canary":
        canary: dict = {}

        if use_traffic:
            canary["canaryService"] = canary_service
            canary["stableService"] = stable_service
            canary["trafficRouting"] = _build_traffic_routing(
                traffic_routing, virtual_service, routes
            )

        if max_surge is not None:
            canary["maxSurge"] = max_surge
        if max_unavailable is not None:
            canary["maxUnavailable"] = max_unavailable

        if steps:
            parsed = (
                parse_steps(steps) if isinstance(steps, str) else list(steps)
            )
            canary["steps"] = parsed

        if analysis_template:
            analysis: dict = {
                "templates": [{"templateName": analysis_template}],
                "args": [],
            }
            if starting_step is not None:
                analysis["startingStep"] = starting_step
            canary["analysis"] = analysis

        strategy_block = {"canary": canary}
    else:  # bluegreen
        blue_green: dict = {
            "activeService": active_service,
            "scaleDownDelaySeconds": 30,
        }
        if preview_service:
            blue_green["previewService"] = preview_service
        if manual_gate:
            blue_green["autoPromotionEnabled"] = False
        if max_surge is not None:
            blue_green["maxSurge"] = max_surge
        if max_unavailable is not None:
            blue_green["maxUnavailable"] = max_unavailable
        strategy_block = {"blueGreen": blue_green}

    # ---- assemble ---------------------------------------------------------
    return {
        "apiVersion": API_VERSION,
        "kind": "Rollout",
        "metadata": metadata,
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": name}},
            "template": template,
            "strategy": strategy_block,
        },
    }


def _build_traffic_routing(
    router: str,
    virtual_service: str | None,
    routes: Any,
) -> dict:
    """Build the ``trafficRouting`` block for the selected router."""
    if router == "istio":
        vs: dict = {"name": virtual_service}
        route_list = _coerce_routes(routes)
        if route_list:
            vs["routes"] = route_list
        return {"istio": {"virtualService": vs}}
    # nginx / alb / smi take provider-specific extra config that we leave
    # for the user to hand-edit; emit an empty marker so the structure is
    # discoverable and the validator still sees that trafficRouting is set.
    return {router: {}}


# ---------------------------------------------------------------------------
# AnalysisTemplate builder
# ---------------------------------------------------------------------------


def _coerce_args(args: Any) -> list[dict]:
    """Normalize ``args`` input into a list of ``{name, value}`` dicts.

    Accepts:
      * list of ``(name, value)`` tuples/lists
      * dict of ``{name: value}``
      * list of pre-formed ``{name, value}`` dicts
    """
    out: list[dict] = []
    if args is None:
        return out
    if isinstance(args, dict):
        items: Iterable = args.items()
    else:
        items = args
    for item in items:
        if isinstance(item, dict):
            if "name" not in item:
                raise ValueError(f"invalid arg {item!r}: missing 'name'")
            extras = {k: v for k, v in item.items() if k != "name"}
            out.append({"name": item["name"], **extras})
        elif isinstance(item, (tuple, list)):
            if len(item) != 2:
                raise ValueError(f"invalid arg {item!r}: expected (name, value)")
            out.append({"name": item[0], "value": item[1]})
        else:
            raise ValueError(f"invalid arg {item!r}: expected tuple or dict")
    return out


def build_analysis_template(
    *,
    name: str,
    provider: str,
    query: str | None = None,
    address: str | None = None,
    success: str | None = None,
    failure: str | None = None,
    failure_limit: int = 0,
    consecutive_success_limit: int = 0,
    interval: str | None = None,
    count: int | None = None,
    metric_name: str = "success-rate",
    args: Any = None,
) -> dict:
    """Build an Argo Rollouts ``AnalysisTemplate`` manifest as a dict.

    Provider shapes:

    - ``prometheus`` / ``graphite`` / ``influxdb`` -> ``{address, query}``
      (both required)
    - ``datadog`` -> ``{apiVersion: v1, query}``
    - other providers -> best-effort ``{query}``; complex providers
      (Wavefront, New Relic, CloudWatch, Kayenta, Job, Web) need
      hand-editing -- see the script README for guidance.

    ``failureLimit`` and ``consecutiveSuccessLimit`` are always emitted
    (defaults of ``0`` per the Argo spec, where ``0`` disables the
    corresponding success/error logic).
    """
    if not name:
        raise ValueError("--name is required")
    if not provider:
        raise ValueError("--provider is required")
    if provider not in ANALYSIS_PROVIDERS:
        raise ValueError(
            f"--provider must be one of {list(ANALYSIS_PROVIDERS)!r}, "
            f"got {provider!r}"
        )

    provider_block = _build_provider_block(provider, address, query)
    metric: dict = {
        "name": metric_name,
        "failureLimit": failure_limit,
        "consecutiveSuccessLimit": consecutive_success_limit,
    }
    if interval:
        metric["interval"] = interval
    if count is not None:
        metric["count"] = count
    if success:
        metric["successCondition"] = success
    if failure:
        metric["failureCondition"] = failure
    metric["provider"] = provider_block

    spec: dict = {}
    arg_list = _coerce_args(args)
    if arg_list:
        spec["args"] = arg_list
    spec["metrics"] = [metric]

    return {
        "apiVersion": API_VERSION,
        "kind": "AnalysisTemplate",
        "metadata": {"name": name},
        "spec": spec,
    }


def _build_provider_block(
    provider: str, address: str | None, query: str | None
) -> dict:
    """Build the ``provider`` block for the selected AnalysisTemplate provider."""
    if provider in ADDRESS_PROVIDERS:
        if not address:
            raise ValueError(
                f"--address is required for provider {provider!r}"
            )
        if not query:
            raise ValueError(
                f"--query is required for provider {provider!r}"
            )
        return {provider: {"address": address, "query": query}}
    if provider == "datadog":
        if not query:
            raise ValueError("--query is required for provider 'datadog'")
        return {"datadog": {"apiVersion": "v1", "query": query}}
    # Best-effort fallback for wavefront / newrelic / cloudwatch / kayenta /
    # job / web: these have provider-specific shapes. Emit a query-only stub
    # and let the user hand-edit.
    return {provider: {"query": query} if query else {}}


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_rollout(doc: dict) -> list[str]:
    """Validate a ``Rollout`` manifest; return a list of error strings.

    An empty list means the manifest is valid. Each error names the field
    path so users can find the problem quickly. The checks implement the
    "Writing manifests: the checklist" rules from SKILL.md.
    """
    errors: list[str] = []

    # Rule 1: apiVersion + kind
    if doc.get("apiVersion") != API_VERSION:
        errors.append(
            f"apiVersion: expected {API_VERSION!r}, got {doc.get('apiVersion')!r}"
        )
    if doc.get("kind") != "Rollout":
        errors.append(
            f"kind: expected 'Rollout', got {doc.get('kind')!r}"
        )

    spec = doc.get("spec") or {}
    strategy = spec.get("strategy") or {}

    # Detect the canonical camelCase mistake before counting strategies.
    if "bluegreen" in strategy:
        errors.append(
            "spec.strategy.bluegreen: key must be camelCase 'blueGreen'"
        )

    has_canary = "canary" in strategy
    has_blue_green = "blueGreen" in strategy

    # Rule 2: exactly one strategy
    if has_canary and has_blue_green:
        errors.append(
            "spec.strategy: set exactly one of 'canary' or 'blueGreen' (both present)"
        )
    elif not has_canary and not has_blue_green:
        errors.append(
            "spec.strategy: must set exactly one of 'canary' or 'blueGreen'"
        )

    # Rule 3: selector.matchLabels subset of template.metadata.labels
    selector_labels = ((spec.get("selector") or {}).get("matchLabels")) or {}
    template_labels = (
        ((spec.get("template") or {}).get("metadata") or {}).get("labels")
    ) or {}
    for key, value in selector_labels.items():
        if template_labels.get(key) != value:
            errors.append(
                f"spec.selector.matchLabels.{key}: {value!r} does not match "
                f"spec.template.metadata.labels.{key}={template_labels.get(key)!r}"
            )

    canary = strategy.get("canary") or {}
    blue_green = strategy.get("blueGreen") or {}

    # Rule 4: trafficRouting requires canaryService + stableService
    if canary.get("trafficRouting"):
        if not canary.get("canaryService"):
            errors.append(
                "spec.strategy.canary.canaryService: required when 'trafficRouting' is set"
            )
        if not canary.get("stableService"):
            errors.append(
                "spec.strategy.canary.stableService: required when 'trafficRouting' is set"
            )

    # Rule 5: blueGreen requires activeService
    if has_blue_green and not blue_green.get("activeService"):
        errors.append("spec.strategy.blueGreen.activeService: required")

    # Rule 6: maxSurge + maxUnavailable cannot both be 0
    if has_canary:
        surge = canary.get("maxSurge")
        unavail = canary.get("maxUnavailable")
    else:
        surge = blue_green.get("maxSurge")
        unavail = blue_green.get("maxUnavailable")
    if _is_zero(surge) and _is_zero(unavail):
        errors.append(
            "spec.strategy: maxSurge and maxUnavailable cannot both be 0"
        )

    # Rule 7: every analysis template entry needs a templateName
    analysis = canary.get("analysis") or {}
    for i, entry in enumerate(analysis.get("templates") or []):
        if not entry.get("templateName"):
            errors.append(
                f"spec.strategy.canary.analysis.templates[{i}]: missing 'templateName'"
            )

    # Rule 8: each canary step has exactly one known step key
    for i, step in enumerate(canary.get("steps") or []):
        if not isinstance(step, dict):
            errors.append(
                f"spec.strategy.canary.steps[{i}]: must be a mapping, "
                f"got {type(step).__name__}"
            )
            continue
        keys = set(step.keys())
        if not keys:
            errors.append(f"spec.strategy.canary.steps[{i}]: empty step")
        elif len(keys) > 1:
            errors.append(
                f"spec.strategy.canary.steps[{i}]: must have exactly one key, "
                f"got {sorted(keys)}"
            )
        elif keys.isdisjoint(STEP_KEYS):
            errors.append(
                f"spec.strategy.canary.steps[{i}]: unknown step key "
                f"{next(iter(keys))!r}; expected one of {sorted(STEP_KEYS)}"
            )

    return errors


def validate_analysis(doc: dict) -> list[str]:
    """Validate an ``AnalysisTemplate`` manifest; return a list of error strings.

    An empty list means the manifest is valid. Checks: apiVersion/kind, at
    least one metric, each metric has a name and a provider block.
    """
    errors: list[str] = []

    if doc.get("apiVersion") != API_VERSION:
        errors.append(
            f"apiVersion: expected {API_VERSION!r}, got {doc.get('apiVersion')!r}"
        )
    if doc.get("kind") != "AnalysisTemplate":
        errors.append(
            f"kind: expected 'AnalysisTemplate', got {doc.get('kind')!r}"
        )

    spec = doc.get("spec") or {}
    metrics = spec.get("metrics") or []
    if not metrics:
        errors.append("spec.metrics: at least one metric is required")
    for i, metric in enumerate(metrics):
        if not metric.get("name"):
            errors.append(f"spec.metrics[{i}].name: required")
        if not metric.get("provider"):
            errors.append(f"spec.metrics[{i}].provider: required")

    return errors
