# argo-rollouts skill

[![CI](https://github.com/jessegonzalez/skills/actions/workflows/ci.yml/badge.svg)](https://github.com/jessegonzalez/skills/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Spec: agentskills.io](https://img.shields.io/badge/spec-agentskills.io-8A2BE2)](https://agentskills.io/specification.md)

A **Claude / agent Skill** — in the [agentskills.io](https://agentskills.io/specification.md)
format — that helps agents and humans **author, operate, and troubleshoot
[Argo Rollouts](https://argoproj.github.io/argo-rollouts/)**, the Kubernetes
progressive-delivery controller.

The repository distributes the skill. The skill itself lives in
[`plugins/argo-rollouts/skills/argo-rollouts/`](./plugins/argo-rollouts/skills/argo-rollouts) and consists of:

- **[`SKILL.md`](./plugins/argo-rollouts/skills/argo-rollouts/SKILL.md)** — the orientation layer: the
  reconciler mental model, the field map, and a routing table into the
  references.
- **[`references/*.md`](./plugins/argo-rollouts/skills/argo-rollouts/references)** — 12 deep-dive docs
  (canary, blue-green, analysis, traffic routing, GitOps, troubleshooting…).
- **[`scripts/`](./plugins/argo-rollouts/skills/argo-rollouts/scripts)** — three PEP 723 self-contained
  CLIs you run with [`uv`](https://docs.astral.sh/uv/) and zero install:
  [`gen_rollout.py`](./plugins/argo-rollouts/skills/argo-rollouts/scripts/gen_rollout.py),
  [`gen_analysis.py`](./plugins/argo-rollouts/skills/argo-rollouts/scripts/gen_analysis.py),
  [`validate.py`](./plugins/argo-rollouts/skills/argo-rollouts/scripts/validate.py). See
  [`scripts/README.md`](./plugins/argo-rollouts/skills/argo-rollouts/scripts/README.md).
- **[`tests/`](./plugins/argo-rollouts/skills/argo-rollouts/tests)** — 61 pytest tests covering all three
  CLIs.

> **Field paths in this skill are verified against `argoproj.io/v1alpha1`.**
> When the docs and the skill disagree, trust the docs.

## Install

**Option A — plugin marketplace (Claude Code):**

```bash
claude plugin marketplace add jessegonzalez/skills
claude plugin install argo-rollouts@jessegonzalez-skills
```

…or, once GitHub Pages is live, from the hosted catalog URL:

```bash
claude plugin marketplace add https://jessegonzalez.github.io/skills/marketplace.json
```

**Option B — manual (any agent that loads `SKILL.md`):**

```bash
git clone https://github.com/jessegonzalez/skills.git
# Point your agent at the skill: plugins/argo-rollouts/skills/argo-rollouts/SKILL.md
#   opencode: add the dir to `skills.paths` in opencode.json
#   Claude Code: drop under ~/.claude/skills/
```

There is nothing to `pip install`. The helper scripts declare
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

Every script has `--help`. The full CLI reference is in
[`plugins/argo-rollouts/skills/argo-rollouts/scripts/README.md`](./plugins/argo-rollouts/skills/argo-rollouts/scripts/README.md).

## Develop

```bash
# Tests (no venv required)
cd plugins/argo-rollouts/skills/argo-rollouts && uv run --with pytest --with pyyaml python -m pytest tests/ -q && cd ..

# Lint
uvx ruff check plugins/argo-rollouts/skills/argo-rollouts/scripts plugins/argo-rollouts/skills/argo-rollouts/tests

# Validate the skill against the agentskills.io spec
python3 .github/scripts/validate_skill.py plugins/argo-rollouts/skills/argo-rollouts/SKILL.md
```

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the full workflow, commit
conventions, and the rule that `SKILL.md`'s `name` must always equal its
parent directory name.

## CI

[`.github/workflows/ci.yml`](./.github/workflows/ci.yml) runs four independent
jobs on every push to `main` and every PR against `main`:

| Job          | What it checks                                           |
|--------------|----------------------------------------------------------|
| `test`       | `pytest plugins/argo-rollouts/skills/argo-rollouts/tests` under Python 3.14 via `uv`. |
| `lint`       | `ruff check plugins/argo-rollouts/skills/argo-rollouts`. |
| `skill-spec` | `SKILL.md` conforms to the agentskills.io spec.          |
| `smoke`      | The `gen_*` → `validate` pipeline produces valid output. |

All four must stay green.

## License

[MIT](./LICENSE) — matching the skill's own `license: MIT`
frontmatter. Copyright 2026 Jesse Gonzalez.
