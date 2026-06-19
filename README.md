# jessegonzalez-skills

> A plugin marketplace distributing agent skills (agentskills.io format) for
> Claude Code, opencode, and any agent that loads `SKILL.md`.

[![CI](https://github.com/jessegonzalez/skills/actions/workflows/ci.yml/badge.svg)](https://github.com/jessegonzalez/skills/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Spec: agentskills.io](https://img.shields.io/badge/spec-agentskills.io-8A2BE2)](https://agentskills.io/specification.md)

This repository is a **plugin marketplace** (catalog at
[`.claude-plugin/marketplace.json`](./.claude-plugin/marketplace.json)). Each
plugin bundles one or more skills in the
[agentskills.io](https://agentskills.io/specification.md) format — a
self-describing `SKILL.md` plus references and scripts that any compatible
agent can load. It currently ships the **argo-rollouts** plugin and is
structured to grow: adding a plugin is a new directory under `plugins/` plus a
catalog entry; nothing else at the root changes.

## Plugins

Each plugin's version is maintained automatically by release-please and shown
in its own README (linked below).

| Plugin | Description | Docs |
|---|---|---|
| [`argo-rollouts`](./plugins/argo-rollouts/) | Author, operate, and troubleshoot Argo Rollouts: canary and blue-green strategies, AnalysisTemplate metric gates, traffic routing, and PEP 723 manifest generators. | [README](./plugins/argo-rollouts/README.md) |

## Install

**Option A — plugin marketplace (Claude Code):**

```bash
claude plugin marketplace add jessegonzalez/skills
claude plugin install argo-rollouts@jessegonzalez-skills
```

…or, once GitHub Pages is live, add the marketplace from its hosted catalog
URL:

```bash
claude plugin marketplace add https://jessegonzalez.github.io/skills/marketplace.json
```

**Option B — manual clone (any agent that loads `SKILL.md`):**

```bash
git clone https://github.com/jessegonzalez/skills.git
# Point your agent at the skill you want, e.g.:
#   plugins/argo-rollouts/skills/argo-rollouts/SKILL.md
#   opencode: add the dir to `skills.paths` in opencode.json
#   Claude Code: drop under ~/.claude/skills/
```

There is nothing to `pip install`. The helper scripts declare their
dependencies inline ([PEP 723](https://peps.python.org/pep-0723/)) and run via
[`uv`](https://docs.astral.sh/uv/).

## Repository layout

The marketplace is **plugin-bundled** (per the plugin-marketplaces spec): each
plugin owns its manifest, skills, and docs under `plugins/<plugin>/`.

```
.claude-plugin/marketplace.json        # the marketplace catalog (name, description, plugin list)
plugins/<plugin>/
  .claude-plugin/plugin.json           # the plugin manifest (version authority)
  README.md                            # plugin-specific docs (linked from the table above)
  skills/<skill>/
    SKILL.md                           # orientation layer (<500 lines)
    references/*.md                    # deep-dive docs
    scripts/*.py                       # PEP 723 manifest generators (uv run)
    tests/                             # pytest
    evals/                             # skill eval harness
githooks/                              # tracked hooks (core.hooksPath = githooks)
.github/                               # CI, templates, validate_skill.py
```

## Developing

Contributions are welcome. Before you start:

- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — prerequisites, the five rules,
  commit conventions, and the verification commands.
- [`AGENTS.md`](./AGENTS.md) — operating instructions for any agent (human or
  AI) working in this repo, including the golden rule: **documentation travels
  with the change**.
- Enable the tracked hooks once (they enforce ruff, pytest, the agentskills.io
  spec check, and Conventional Commits on every commit):

  ```bash
  git config core.hooksPath githooks
  ```

  See [`githooks/README.md`](./githooks/README.md) for details and bypass
  instructions.

## CI

[`.github/workflows/ci.yml`](./.github/workflows/ci.yml) runs four independent
jobs on every push to `main` and every PR against `main`:

| Job          | What it checks                                                    |
|--------------|-------------------------------------------------------------------|
| `test`       | `pytest` across each plugin's `tests/` (Python 3.14 via `uv`).    |
| `lint`       | `ruff check` across each plugin's skill directory.                |
| `skill-spec` | Each `SKILL.md` conforms to the agentskills.io spec.              |
| `smoke`      | The `gen_*` → `validate` pipeline produces valid manifests.       |

All four must stay green.

## License

[MIT](./LICENSE). Copyright 2026 Jesse Gonzalez.
