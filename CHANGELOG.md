# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Going forward, [release-please](https://github.com/googleapis/release-please)
maintains this file from Conventional Commits.

## [Unreleased]

_No unreleased changes._

## [1.1.0] - 2026-06-19

### Added
- **Plugin marketplace** (`.claude-plugin/marketplace.json`) — install via
  `claude plugin marketplace add jessegonzalez/skills` then
  `claude plugin install argo-rollouts@jessegonzalez-skills`.
- **GitHub Pages** deployment (`.github/workflows/pages.yml`) serving the hosted
  marketplace catalog + a landing page at https://jessegonzalez.github.io/skills/.
- **Skill eval harness** (`argo-rollouts/evals/`) — 16 prompts × 2 configs via
  `opencode run --format json`. Latest glm-5.2 benchmark: trigger accuracy 100%,
  over-trigger 0%, quality +10% vs baseline.
- Version-controlled git hooks under `githooks/` (`pre-commit`, `commit-msg`)
  activated via `git config core.hooksPath githooks`.
- GitHub Actions CI (`.github/workflows/ci.yml`) with four jobs: `test`, `lint`,
  `skill-spec`, `smoke`.
- Skill-spec validator at `.github/scripts/validate_skill.py`.
- PR template, issue templates, `CODEOWNERS`, `dependabot.yml`.
- Release automation via release-please (`.github/workflows/release-please.yml`).

### Changed
- Relicensed from Apache-2.0 to **MIT**.
- Published as the `jessegonzalez/skills` repository.
- Bumped CI action versions: `actions/checkout@v7`, `actions/setup-python@v6`,
  `astral-sh/setup-uv@v7`; dependency floors `pyyaml>=6.0.3`, `pytest>=9.1.0`.

### Fixed
- `lint` CI job: set `setup-uv` `cache-dependency-glob` so it no longer
  hard-errors on the missing `uv.lock`.

## [1.0.0] - 2026-06-19

### Added
- Initial release of the **argo-rollouts** skill (agentskills.io format).
- `SKILL.md` orientation layer: reconciler mental model, field map, and a
  routing table into 12 reference documents.
- `references/` (12 docs):
  - `analysis.md` — AnalysisTemplates, metric providers (Prometheus, Datadog,
    Wavefront, New Relic, CloudWatch, Graphite, InfluxDB, Kayenta, Job, Web),
    success/failure conditions, `count`.
  - `blue-green.md` — `blueGreen` strategy, `activeService`/`previewService`,
    auto-promotion, scaleDownDelaySeconds.
  - `canary.md` — `canary` strategy, weighted steps, `setCanaryScale`,
    `dynamicStableScale`, `maxSurge`/`maxUnavailable`.
  - `experiments.md` — `Experiment` CRD, A/B testing, baseline-vs-canary.
  - `gitops-argocd.md` — Argo CD pairing, self-heal semantics, rollback
    interaction.
  - `install-config.md` — controller install, `kubectl argo rollouts` plugin,
    Deployment → Rollout migration.
  - `kubectl-plugin.md` — day-2 operations: `promote`, `abort`, `undo`,
    `retry`, `status`, `set image`.
  - `notifications.md` — Slack / Teams notification setup, trigger templates.
  - `state-machine.md` — phases, steps, abort / pause / rollback semantics.
  - `strategy-decisions.md` — choosing between canary, blue-green, and
    rolling.
  - `traffic-routing.md` — Istio, NGINX, SMI, AWS ALB, Traefik, Apisix, Gloo,
    Gateway API.
  - `troubleshooting.md` — stuck/aborted/mis-routing runbook.
- `scripts/` (PEP 723, runnable via `uv run`):
  - `gen_rollout.py` — Rollout manifest generator (canary / blue-green,
    traffic routing, analysis gates, custom steps).
  - `gen_analysis.py` — AnalysisTemplate generator (multi-provider).
  - `validate.py` — offline manifest validator.
  - `rollout_lib.py` — shared library.
  - `README.md` — CLI reference.
- `tests/` — 55 pytest tests across all three CLIs.

[Unreleased]: https://github.com/jessegonzalez/skills/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/jessegonzalez/skills/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jessegonzalez/skills/releases/tag/v1.0.0
