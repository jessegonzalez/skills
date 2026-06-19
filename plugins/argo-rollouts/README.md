# argo-rollouts

**Version:** v1.2.1 <!-- x-release-please-version -->

A skill — in the [agentskills.io](https://agentskills.io/specification.md)
format — that helps agents and humans **author, operate, and troubleshoot
[Argo Rollouts](https://argoproj.github.io/argo-rollouts/)**, the Kubernetes
progressive-delivery controller.

> **Field paths in this skill are verified against `argoproj.io/v1alpha1`.**
> When the docs and the skill disagree, trust the docs.

## What's in the skill

The skill lives in [`skills/argo-rollouts/`](./skills/argo-rollouts) and
consists of:

- **[`SKILL.md`](./skills/argo-rollouts/SKILL.md)** — the orientation layer:
  the reconciler mental model, the field map, and a routing table into the
  references.
- **[`references/*.md`](./skills/argo-rollouts/references)** — 12 deep-dive
  docs (canary, blue-green, analysis, traffic routing, GitOps,
  troubleshooting…).
- **[`scripts/`](./skills/argo-rollouts/scripts)** — three PEP 723
  self-contained CLIs you run with [`uv`](https://docs.astral.sh/uv/) and zero
  install:
  [`gen_rollout.py`](./skills/argo-rollouts/scripts/gen_rollout.py),
  [`gen_analysis.py`](./skills/argo-rollouts/scripts/gen_analysis.py),
  [`validate.py`](./skills/argo-rollouts/scripts/validate.py). See the
  [`scripts/README.md`](./skills/argo-rollouts/scripts/README.md) CLI
  reference.
- **[`tests/`](./skills/argo-rollouts/tests)** — 61 pytest tests covering all
  three CLIs.

## Usage

Run from the repo root. Every script also has `--help`.

```bash
# Generate a canary Rollout with AWS ALB traffic routing + ping-pong + an AnalysisTemplate gate
uv run plugins/argo-rollouts/skills/argo-rollouts/scripts/gen_rollout.py \
  --name guestbook --image guestbook:v2 --replicas 4 \
  --strategy canary --steps "20 5m,40 5m,60 5m,80 5m" \
  --traffic-routing alb --ingress guestbook-ingress --service-port 443 \
  --root-service guestbook-root --ping-pong \
  --stable-service guestbook-stable --canary-service guestbook-canary \
  --analysis-template success-rate --starting-step 2 > rollout.yaml

# Generate the matching AnalysisTemplate (Prometheus success-rate)
uv run plugins/argo-rollouts/skills/argo-rollouts/scripts/gen_analysis.py \
  --name success-rate --provider prometheus \
  --address http://prometheus:9090 \
  --query 'sum(rate(http_requests_total[5m]))' \
  --success 'result[0] >= 0.95' --failure-limit 3 --interval 5m > analysis.yaml

# Validate before applying
uv run plugins/argo-rollouts/skills/argo-rollouts/scripts/validate.py rollout.yaml analysis.yaml
```

The full per-flag reference lives in
[`skills/argo-rollouts/scripts/README.md`](./skills/argo-rollouts/scripts/README.md).

## Develop

Run these from the repo root:

```bash
# Tests (no venv required)
cd plugins/argo-rollouts/skills/argo-rollouts && uv run --with pytest --with pyyaml python -m pytest tests/ -q && cd ..

# Lint
uvx ruff check plugins/argo-rollouts/skills/argo-rollouts/scripts plugins/argo-rollouts/skills/argo-rollouts/tests

# Validate the skill against the agentskills.io spec
python3 .github/scripts/validate_skill.py plugins/argo-rollouts/skills/argo-rollouts/SKILL.md
```

For the full contributor workflow, commit conventions, and the five rules, see
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) and
[`AGENTS.md`](../../AGENTS.md).

## License

[MIT](../../LICENSE) — matching the skill's own `license: MIT` frontmatter.
Copyright 2026 Jesse Gonzalez.
