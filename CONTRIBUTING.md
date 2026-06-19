# Contributing

Thanks for helping improve the argo-rollouts skill! This is a short, opinionated
guide. The skill itself (under [`argo-rollouts/`](./argo-rollouts)) is the
deliverable; everything else in this repo exists to keep it trustworthy.

## TL;DR

```bash
# 1. Fork & clone, then enable hooks (one-time):
git config core.hooksPath githooks

# 2. Branch:
git checkout -b feat/my-change

# 3. Make changes. Tests + lint + spec are enforced by the pre-commit hook.
# 4. Conventional Commits are enforced by the commit-msg hook.
git commit -m "feat(analysis): add datadog provider example"
git push -u origin feat/my-change

# 5. Open a PR; the PR template's checklist walks you through sign-off.
```

## Prerequisites

| Tool       | Version  | Why                                            |
|------------|----------|------------------------------------------------|
| Python     | 3.14+    | Scripts target `>=3.9`, CI runs 3.14.          |
| `uv`       | 0.11+    | Runs PEP 723 scripts with zero install.        |
| `git`      | 2.30+    | `core.hooksPath` (used by our hooks).          |

Optional, local-only: `ruff` (`.venv/bin/ruff` is auto-detected by the hook).
On CI it's pulled in via `uvx`.

## The five rules

These are the rules that, if broken, tend to silently corrupt the skill.
They're all enforced by CI but please internalise them:

1. **`SKILL.md` `name` must equal its parent directory name.** The skill
   lives in `argo-rollouts/`, so `name:` is `argo-rollouts`. The
   `skill-spec` CI job and the `pre-commit` hook both check this.

2. **New scripts need tests.** Every CLI behaviour change in
   `argo-rollouts/scripts/` ships with new or updated tests in
   `argo-rollouts/tests/`. CI fails without it (the test count is currently
   55 — your change should bump it).

3. **New references must be linked from `SKILL.md`.** A reference doc that
   no one navigates to is dead weight. Add a row to the routing table at the
   top of `SKILL.md`.

4. **`SKILL.md` `description` stays ≤ 1024 chars; the body stays < 500
   lines.** Both are spec limits; the validator enforces them.

5. **The `skill-spec` CI gate stays green.** It runs
   [`python3 .github/scripts/validate_skill.py`](./.github/scripts/validate_skill.py)
   on every push.

## Commit convention — Conventional Commits

Every commit's first line must match:

```
<type>(<scope>)!: <subject>
```

- **`type`** — one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`,
  `test`, `build`, `ci`, `chore`, `revert`.
- **`scope`** (optional) — lowercase noun: `analysis`, `rollout`, `validate`,
  `references`, `scripts`, `ci`, `hooks`, `docs`…
- **`!`** (optional) — marks a **breaking change**.
- **`subject`** — short imperative description, no trailing period.

```text
feat(analysis): add Datadog provider examples
fix(validate): reject AnalysisTemplates missing a metric block
docs(references): expand traffic-routing examples for Gateway API
refactor(scripts): extract step-parsing into rollout_lib
ci: bump setup-uv to v3
feat!: drop Python 3.8 support          # BREAKING
```

Multi-line footers are fine:

```
feat(rollout)!: add dynamicStableScale default

BREAKING CHANGE: `--dynamic-stable-scale` now defaults to true for
traffic-routed canaries. Pin with `--no-dynamic-stable-scale` to keep the
old behaviour.

Closes #42
```

The `commit-msg` hook validates this; bypass with `--no-verify` only in
emergencies.

## Verification

Before pushing, run the four canonical commands from the repo root (also in
the PR template):

```bash
cd argo-rollouts && uv run --with pytest --with pyyaml python -m pytest tests/ -q && cd ..
uvx ruff check argo-rollouts/scripts argo-rollouts/tests
python3 .github/scripts/validate_skill.py argo-rollouts/SKILL.md
# smoke:
uv run argo-rollouts/scripts/gen_rollout.py --name guestbook --image guestbook:v2 \
  --replicas 4 --strategy canary --steps "20 5m,40 5m,60 5m,80 5m" \
  --traffic-routing istio --virtual-service guestbook-vsvc --routes primary \
  --stable-service guestbook-stable --canary-service guestbook-canary \
  --analysis-template success-rate --starting-step 2 > /tmp/r.yaml
uv run argo-rollouts/scripts/gen_analysis.py --name success-rate --provider prometheus \
  --address http://prometheus:9090 --query 'sum(rate(http_requests_total[5m]))' \
  --success 'result[0] >= 0.95' --failure-limit 3 --interval 5m > /tmp/a.yaml
uv run argo-rollouts/scripts/validate.py /tmp/r.yaml /tmp/a.yaml
```

## Hooks

Hooks live under [`githooks/`](./githooks) (tracked) and are activated with
`git config core.hooksPath githooks`. They run the three checks above plus
the commit-message check on every commit. See
[`githooks/README.md`](./githooks/README.md).

## Releases

We follow [Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/). New work goes under
`[Unreleased]` in [`CHANGELOG.md`](./CHANGELOG.md) and is moved to a
versioned heading on release.

## Licence

By contributing you agree your contributions are licensed under
[MIT](./LICENSE).
