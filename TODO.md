# TODO

## Execution order

1. **Test the skill locally** (validate before push) via `opencode run` — pass the skill/plugin directory. Use `opencode run --help` for the exact invocation.
2. **Path A — publish**, but the remote is named **`skills`** (not `argo-rollouts`). Only push after the local test passes.
3. **Path B — skill evals loop**: trigger-precision + output-quality, with-skill vs baseline.
4. **Path C–I — finish** with coverage extension + ops.

## Backlog

- [ ] **Plugin marketplace** — GitHub Pages-hosted, to easily install plugins / skills / agents / prompts. Spec: https://code.claude.com/docs/en/plugin-marketplaces.md
- [ ] **Test the skill before push** — use `opencode run --help` for passing a plugin directory for testing. Use this as the opportunity for **C–I** (model/router, evals, etc.) and to instruct the Git Workflow agent for improvements.
- [ ] **Reference repo** — `gh repo disler/the-library` as inspiration, or use directly.
- [ ] **LiteLLM provider** — add a provider with **JWT auth** and **background refresh on a 1-hour TTL**.
