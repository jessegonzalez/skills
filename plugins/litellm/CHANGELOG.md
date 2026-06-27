# Changelog

## 1.0.1 (2026-06-27)

## What's Changed
* build(deps)(deps-dev): bump @opencode-ai/plugin from 1.4.5 to 1.17.8 in /plugins/litellm by @dependabot[bot] in https://github.com/jessegonzalez/skills/pull/20
* build(deps)(deps): update pytest requirement from >=9.1.0 to >=9.1.1 in /plugins/argo-rollouts/skills/argo-rollouts by @dependabot[bot] in https://github.com/jessegonzalez/skills/pull/19
* docs: remove stale TODO and orphaned root CHANGELOG by @jessegonzalez in https://github.com/jessegonzalez/skills/pull/21
* chore(release): register litellm as a release-please-managed plugin by @jessegonzalez in https://github.com/jessegonzalez/skills/pull/22


**Full Changelog**: https://github.com/jessegonzalez/skills/compare/litellm-v1.0.0...litellm-v1.0.1

## [1.0.0](https://github.com/jessegonzalez/skills/releases/tag/litellm-v1.0.0)

### Features

* **litellm:** add `apiKeyHelper` opencode plugin with bun:test suite + CI
  (#18). Generic auth-token helper: reads an `apiKeyHelper` block from a
  provider's `options`, runs the configured shell command to fetch a token
  (JWT, x-api-key, or other), injects it into each LLM request header
  (`Authorization: Bearer <token>` by default), and caches the token with a
  3600s TTL + pre-expiry refresh. Ships with 6 bun:test cases and a dedicated
  CI job.
* **litellm:** opencode custom provider config example (phase 1) (#16).
  Documents the `@ai-sdk/openai-compatible` provider entry for routing
  opencode requests through a LiteLLM (or any OpenAI-compatible) proxy.
