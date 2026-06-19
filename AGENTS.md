# AGENTS.md

Operating instructions for any agent (human or AI) working in this repository.

## What this repo is

A plugin marketplace (`jessegonzalez/skills`) distributing agent skills in the
[agentskills.io](https://agentskills.io/specification.md) format. Today it ships
one skill — **argo-rollouts** — and is structured to grow.

## Layout (plugin-bundled, per the plugin-marketplaces spec)

.claude-plugin/marketplace.json        # the marketplace catalog
plugins/<plugin>/
  .claude-plugin/plugin.json           # the plugin manifest (authority)
  README.md                            # plugin overview + release-please-managed version
  skills/<skill>/                      # one agentskills.io skill
    SKILL.md                           # orientation layer (<500 lines)
    references/*.md                    # deep-dive docs
    scripts/*.py                       # PEP 723 manifest generators (uv run)
    tests/                             # pytest
    evals/                             # skill eval harness
    requirements.txt
githooks/                              # tracked hooks (core.hooksPath = githooks)
.github/                               # CI, templates, dependabot, validate_skill.py

Repo meta: README.md, CONTRIBUTING.md, CHANGELOG.md, LICENSE (MIT), SECURITY.md, TODO.md.

## The golden rule — documentation travels with the change

**Every change MUST update the documentation it affects, in the same commit.**
Stale docs are a bug, not a follow-up. If you touch the left column, update the right.

| When you change...                              | Update these                                                                  |
|-------------------------------------------------|-------------------------------------------------------------------------------|
| `scripts/*.py` CLI flags or output shape        | `scripts/README.md` flag table + `tests/` (+ `SKILL.md` if canonical)         |
| The canonical example (strategy/router)         | `SKILL.md`, `plugins/<p>/README.md` "Usage", CI smoke job, `scripts/README.md`, PR template    |
| Test count (add/remove tests)                   | `plugins/<p>/README.md` "tests/" line + CONTRIBUTING rule 2 (both cite the count)              |
| Skill frontmatter (name/description/version)    | `SKILL.md` + `plugins/<p>/.claude-plugin/plugin.json` (version authority) + `marketplace.json` (name/description mirror) |
| File / directory layout                         | README, CONTRIBUTING, CODEOWNERS, dependabot.yml, ci.yml, githooks/pre-commit, validate_skill.py default path |
| A version bump / release                        | Automatic via release-please (per plugin): `plugin.json`, `SKILL.md` `version:`, `plugins/<p>/README.md` version marker, `plugins/<p>/CHANGELOG.md`, `.release-please-manifest.json` (the root README is NOT version-managed — release-please cannot reach it) |
| A new `references/*.md`                         | SKILL.md routing table (so it's discoverable)                                 |
| A new plugin or skill                           | `marketplace.json` `plugins[]` + its `.claude-plugin/plugin.json` + `plugins/<p>/README.md` (with version marker) + `release-please-config.json` `packages{}` + `.release-please-manifest.json` |

When unsure whether a change is user-visible: update the doc anyway. The cost of
a one-line doc sync is near zero; the cost of a stale doc is a misled user or
agent. This table exists so the right update is a two-second lookup, not a hunt.

## The five rules

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the enforced rules. Most
load-bearing: `SKILL.md` `name` must equal its parent dir; new scripts need
tests; `description` <= 1024 chars; body < 500 lines; the `skill-spec` CI gate
stays green.

## Verification (all must pass before commit)

    .venv/bin/python -m pytest plugins/argo-rollouts/skills/argo-rollouts/tests -q
    .venv/bin/ruff check plugins/argo-rollouts/skills/argo-rollouts
    .venv/bin/python .github/scripts/validate_skill.py
    # smoke:
    SKILL=plugins/argo-rollouts/skills/argo-rollouts
    uv run "$SKILL/scripts/gen_rollout.py" --name guestbook --image guestbook:v2 --replicas 4 \
      --strategy canary --steps "20 5m,40 5m,60 5m,80 5m" \
      --traffic-routing alb --ingress guestbook-ingress --service-port 443 \
      --root-service guestbook-root --ping-pong \
      --stable-service guestbook-stable --canary-service guestbook-canary \
      --analysis-template success-rate --starting-step 2 > /tmp/r.yaml
    uv run "$SKILL/scripts/gen_analysis.py" --name success-rate --provider prometheus \
      --address http://prometheus:9090 --query 'sum(rate(http_requests_total[5m]))' \
      --success 'result[0] >= 0.95' --failure-limit 3 --interval 5m > /tmp/a.yaml
    uv run "$SKILL/scripts/validate.py" /tmp/r.yaml /tmp/a.yaml

These also run via `githooks/pre-commit` (ruff + pytest + spec) on every commit
and via the 4 CI jobs on every push.

## Commit convention

Conventional Commits, enforced by `githooks/commit-msg`. Doc-only changes use
`docs(scope): ...`.
