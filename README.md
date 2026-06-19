# argo-rollouts skill

[![CI](https://github.com/jessegonzalez/skills/actions/workflows/ci.yml/badge.svg)](https://github.com/jessegonzalez/skills/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Spec: agentskills.io](https://img.shields.io/badge/spec-agentskills.io-8A2BE2)](https://agentskills.io/specification.md)

A **Claude / agent Skill** — in the [agentskills.io](https://agentskills.io/specification.md)
format — that helps agents and humans **author, operate, and troubleshoot
[Argo Rollouts](https://argoproj.github.io/argo-rollouts/)**, the Kubernetes
progressive-delivery controller.

The repository distributes the skill. The skill itself lives in
[`argo-rollouts/`](./argo-rollouts) and consists of:

- **[`SKILL.md`](./argo-rollouts/SKILL.md)** — the orientation layer: the
  reconciler mental model, the field map, and a routing table into the
  references.
- **[`references/*.md`](./argo-rollouts/references)** — 12 deep-dive docs
  (canary, blue-green, analysis, traffic routing, GitOps, troubleshooting…).
- **[`scripts/`](./argo-rollouts/scripts)** — three PEP 723 self-contained
  CLIs you run with [`uv`](https://docs.astral.sh/uv/) and zero install:
  [`gen_rollout.py`](./argo-rollouts/scripts/gen_rollout.py),
  [`gen_analysis.py`](./argo-rollouts/scripts/gen_analysis.py),
  [`validate.py`](./argo-rollouts/scripts/validate.py). See
  [`scripts/README.md`](./argo-rollouts/scripts/README.md).
- **[`tests/`](./argo-rollouts/tests)** — 55 pytest tests covering all three
  CLIs.

> **Field paths in this skill are verified against `argoproj.io/v1alpha1`.**
> When the docs and the skill disagree, trust the docs.

## Install

```bash
git clone https://github.com/jessegonzalez/skills.git
# Then point your agent (Claude Code, etc.) at the skill directory:
#   argo-rollouts/argo-rollouts/SKILL.md
```

That's it — there is nothing to `pip install`. The helper scripts declare
their dependencies inline (PEP 723) and run via `uv`.

## Enable the local git hooks (recommended)

The repo ships version-controlled hooks under [`githooks/`](./githooks) that
run `ruff`, `pytest`, and the agentskills.io spec check on every commit, and
enforce Conventional Commits. They are **not** auto-activated on a fresh
clone — opt in once:

```bash
git config core.hooksPath githooks
git config --get core.hooksPath   # should print: githooks
```

See [`githooks/README.md`](./githooks/README.md) for details and bypass
instructions.

## Usage

```bash
# Generate a canary Rollout with Istio traffic routing + an AnalysisTemplate gate
uv run argo-rollouts/scripts/gen_rollout.py \
  --name guestbook --image guestbook:v2 --replicas 4 \
  --strategy canary --steps "20 5m,40 5m,60 5m,80 5m" \
  --traffic-routing istio \
  --virtual-service guestbook-vsvc --routes primary \
  --stable-service guestbook-stable --canary-service guestbook-canary \
  --analysis-template success-rate --starting-step 2 > rollout.yaml

# Generate the matching AnalysisTemplate (Prometheus success-rate)
uv run argo-rollouts/scripts/gen_analysis.py \
  --name success-rate --provider prometheus \
  --address http://prometheus:9090 \
  --query 'sum(rate(http_requests_total[5m]))' \
  --success 'result[0] >= 0.95' --failure-limit 3 --interval 5m > analysis.yaml

# Validate before applying
uv run argo-rollouts/scripts/validate.py rollout.yaml analysis.yaml
```

Every script has `--help`. The full CLI reference is in
[`argo-rollouts/scripts/README.md`](./argo-rollouts/scripts/README.md).

## Develop

```bash
# Tests (no venv required)
cd argo-rollouts && uv run --with pytest --with pyyaml python -m pytest tests/ -q && cd ..

# Lint
uvx ruff check argo-rollouts/scripts argo-rollouts/tests

# Validate the skill against the agentskills.io spec
python3 .github/scripts/validate_skill.py argo-rollouts/SKILL.md
```

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the full workflow, commit
conventions, and the rule that `SKILL.md`'s `name` must always equal its
parent directory name.

## CI

[`.github/workflows/ci.yml`](./.github/workflows/ci.yml) runs four independent
jobs on every push to `main` and every PR against `main`:

| Job          | What it checks                                           |
|--------------|----------------------------------------------------------|
| `test`       | `pytest argo-rollouts/tests` under Python 3.14 via `uv`. |
| `lint`       | `ruff check argo-rollouts`.                              |
| `skill-spec` | `SKILL.md` conforms to the agentskills.io spec.          |
| `smoke`      | The `gen_*` → `validate` pipeline produces valid output. |

All four must stay green.

## License

[MIT](./LICENSE) — matching the skill's own `license: MIT`
frontmatter. Copyright 2026 Jesse Gonzalez.
