---
name: Bug report
about: Something in the skill produces wrong output, misleading guidance, or broken scripts
title: "bug: "
labels: bug
assignees: ''
---

## What happened?

<!-- Describe the wrong behaviour. Include the exact command, input, and output. -->

```bash
$ uv run argo-rollouts/scripts/...
# output / stack trace
```

## What did you expect?

<!-- The correct behaviour, with a citation to the Argo Rollouts docs if relevant. -->

## Reproduction

1.
2.
3.

## Environment

- Repo commit: <!-- `git rev-parse --short HEAD` -->
- OS / platform:
- `python --version`:
- `uv --version`:
- Argo Rollouts controller version (if cluster-side): <!-- `kubectl argo rollouts version` -->

## Affected artefact(s)

- [ ] `SKILL.md` guidance
- [ ] `references/*.md`
- [ ] `scripts/gen_rollout.py`
- [ ] `scripts/gen_analysis.py`
- [ ] `scripts/validate.py`
- [ ] `scripts/rollout_lib.py`
- [ ] other:

## Anything else?

<!-- Manifest snippets, logs, screenshots, related issues. -->
