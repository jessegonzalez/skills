<!-- Thanks for contributing! Please fill in every section. -->

## Summary

<!-- One or two sentences: what does this change do? -->

## Motivation

<!-- Why? Link issues, design docs, or user pain. -->

## Changes

Tick everything this PR touches. (Untouched sections are fine to leave blank.)

- [ ] `SKILL.md` (frontmatter or body)
- [ ] `references/*.md`
- [ ] `scripts/*.py` (CLI behaviour)
- [ ] `tests/` (new coverage for the change)
- [ ] docs (`README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, hook/CI files)
- [ ] other: <!-- describe -->

## Verification

Commands the author ran from the repo root (all must pass):

```bash
# 1. Tests
cd argo-rollouts && uv run --with pytest --with pyyaml python -m pytest tests/ -q && cd ..

# 2. Lint
uvx ruff check argo-rollouts/scripts argo-rollouts/tests    # or: .venv/bin/ruff check ...

# 3. Skill spec
python3 .github/scripts/validate_skill.py argo-rollouts/SKILL.md

# 4. Smoke (generator → validator)
uv run argo-rollouts/scripts/gen_rollout.py --name guestbook --image guestbook:v2 \
  --replicas 4 --strategy canary --steps "20 5m,40 5m,60 5m,80 5m" \
  --traffic-routing istio --virtual-service guestbook-vsvc --routes primary \
  --stable-service guestbook-stable --canary-service guestbook-canary \
  --analysis-template success-rate --starting-step 2 > /tmp/r.yaml
uv run argo-rollouts/scripts/gen_analysis.py --name success-rate --provider prometheus \
  --address http://prometheus:9090 --query 'sum(rate(http_requests_total[5m]))' \
  --success 'result[0] >= 0.95' --failure-limit 3 --interval 5m > /tmp/a.yaml
uv run argo-rollouts/scripts/validate.py /tmp/r.yaml /tmp/a.yaml    # must exit 0
```

Results: <!-- e.g. "55 passed", "All checks passed!", "OK", "EXIT=0" -->

## Spec-compliance checklist

- [ ] `SKILL.md` `name` equals its parent directory name (`argo-rollouts`).
- [ ] `SKILL.md` `description` ≤ 1024 chars.
- [ ] `SKILL.md` body < 500 lines.
- [ ] Every new `references/*.md` is linked from `SKILL.md`.
- [ ] Every new/changed `scripts/*.py` CLI has test coverage in `tests/`.
- [ ] `requirements.txt` left in sync if new runtime deps were introduced.

## Backward compatibility / migration

<!-- If user-facing manifest output changes shape, call it out and explain. -->
<!-- If it's a breaking change, the commit message uses `feat!:` or a `BREAKING CHANGE:` footer. -->
