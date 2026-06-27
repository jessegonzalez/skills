# Changelog

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
