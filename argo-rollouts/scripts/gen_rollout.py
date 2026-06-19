# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""CLI generator for Argo Rollouts ``Rollout`` manifests.

Thin wrapper over :func:`rollout_lib.build_rollout`. Run with ``--help`` for
the full flag reference, or see ``scripts/README.md`` for examples.

Self-contained: ``uv run scripts/gen_rollout.py ...`` installs PyYAML
automatically. Fallback: ``python3 scripts/gen_rollout.py`` with PyYAML
installed. Exit codes: 0 = success, 2 = bad arguments/values.
"""

from __future__ import annotations

import argparse
import sys

from rollout_lib import STRATEGIES, TRAFFIC_ROUTERS, build_rollout, emit_yaml


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for ``gen_rollout``."""
    p = argparse.ArgumentParser(
        prog="gen_rollout.py",
        description="Generate an Argo Rollouts Rollout manifest as YAML.",
    )
    p.add_argument("--name", required=True, help="Rollout name (also used for the app label and container name).")
    p.add_argument("--image", required=True, help="Container image, e.g. 'guestbook:v2'.")
    p.add_argument("--replicas", type=int, default=1, help="Desired replica count (default: 1).")
    p.add_argument("--namespace", help="Optional metadata.namespace.")
    p.add_argument("--port", type=int, default=8080, help="containers[0].ports[0].containerPort (default: 8080).")
    p.add_argument("--strategy", choices=list(STRATEGIES), default="canary", help="Progressive-delivery strategy (default: canary).")
    p.add_argument("--steps", help='Canary steps, e.g. "20 5m,40 5m,60 5m,80 5m". Each "<W> <D>" becomes {setWeight: W},{pause: {duration: D}}.')
    p.add_argument("--traffic-routing", choices=list(TRAFFIC_ROUTERS), default="none", dest="traffic_routing", help="Traffic router (default: none = pod-ratio canary).")
    p.add_argument("--stable-service", dest="stable_service", help="Stable Service name (required when --traffic-routing != none).")
    p.add_argument("--canary-service", dest="canary_service", help="Canary Service name (required when --traffic-routing != none).")
    p.add_argument("--active-service", dest="active_service", help="Active Service name (required for bluegreen).")
    p.add_argument("--preview-service", dest="preview_service", help="Preview Service name (bluegreen only, optional).")
    p.add_argument("--virtual-service", dest="virtual_service", help="Istio VirtualService name (required when --traffic-routing=istio).")
    p.add_argument("--routes", help="Comma-separated Istio VirtualService route names, e.g. 'primary' or 'r1,r2'.")
    p.add_argument("--analysis-template", dest="analysis_template", help="Background AnalysisTemplate name to gate the canary.")
    p.add_argument("--starting-step", type=int, dest="starting_step", help="canary.analysis.startingStep (delay background analysis until this step index).")
    p.add_argument("--manual-gate", action="store_true", dest="manual_gate", help="Bluegreen: set autoPromotionEnabled=false (require kubectl promote).")
    p.add_argument("--max-surge", dest="max_surge", help='maxSurge (IntOrString, e.g. "25%%" or 1).')
    p.add_argument("--max-unavailable", dest="max_unavailable", help='maxUnavailable (IntOrString, e.g. "25%%" or 1).')
    p.add_argument("--output", default="-", help="Output file path or '-' for stdout (default: -).")
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)

    try:
        doc = build_rollout(
            name=args.name,
            image=args.image,
            replicas=args.replicas,
            namespace=args.namespace,
            port=args.port,
            strategy=args.strategy,
            steps=args.steps,
            traffic_routing=args.traffic_routing,
            stable_service=args.stable_service,
            canary_service=args.canary_service,
            active_service=args.active_service,
            preview_service=args.preview_service,
            virtual_service=args.virtual_service,
            routes=args.routes,
            analysis_template=args.analysis_template,
            starting_step=args.starting_step,
            manual_gate=args.manual_gate,
            max_surge=args.max_surge,
            max_unavailable=args.max_unavailable,
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
