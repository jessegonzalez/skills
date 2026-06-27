# litellm

**Version:** v1.0.1 <!-- x-release-please-version -->

> An opencode custom model provider that fronts a [LiteLLM](https://github.com/BerriAI/litellm) (or any OpenAI-compatible) proxy, plus a generic auth-token helper plugin for short-lived credentials.

## Status

**Phase 1 — provider config (proven).** A static provider configuration that
makes opencode route requests through a LiteLLM proxy.

**Phase 2 — `apiKeyHelper` plugin (proven).** A generic opencode plugin
(`auth-helper.ts`) that runs a shell command to fetch an auth token (JWT,
x-api-key, or anything else) and injects it into each LLM request, caching the
token and refreshing it before its TTL expires. Defaults to `Bearer`/`Authorization`
with a 3600s TTL.

> **Scope note:** LiteLLM is an OpenAI-compatible proxy; opencode has no native
> "litellm" provider type. This is an opencode custom provider built on the
> bundled `@ai-sdk/openai-compatible` package, plus an opencode plugin. Neither
> is a Claude Code marketplace plugin, so neither is registered in
> `.claude-plugin/marketplace.json` or covered by release-please.

## Configuration

### Static provider (phase 1)

Add a provider entry to your `opencode.json` (project, or global
`~/.config/opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "litellm-prod": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LiteLLM Production",
      "options": {
        "baseURL": "https://your-litellm-instance.example.com/v1",
        "apiKey": "<your-litellm-api-key>"
      },
      "models": {
        "gpt-4o": { "id": "gpt-4o", "name": "GPT-4o (via LiteLLM)" },
        "claude-3-7-sonnet": { "id": "claude-3-7-sonnet", "name": "Claude 3.7 Sonnet (via LiteLLM)" }
      }
    }
  }
}
```

Then use it: `opencode run --model litellm-prod/gpt-4o "..."`, or set
`"model": "litellm-prod/gpt-4o"` as the default.

### Dynamic auth (phase 2 — `apiKeyHelper` plugin)

Install the plugin by copying [`auth-helper.ts`](./auth-helper.ts) into your
opencode plugins directory:

```
.opencode/plugins/auth-helper.ts          # project-scoped
~/.config/opencode/plugins/auth-helper.ts # global
```

Then add an `apiKeyHelper` block to any provider's `options`. The plugin reads
it automatically — no per-provider wiring beyond the config:

```json
{
  "provider": {
    "litellm-prod": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LiteLLM Production",
      "options": {
        "baseURL": "https://your-litellm-instance.example.com/v1",
        "apiKey": "placeholder",
        "apiKeyHelper": {
          "command": "okta-jwt --client-id $OKTA_CLIENT_ID --scope litellm",
          "scheme": "Bearer",
          "header": "Authorization",
          "ttl": 3600
        }
      },
      "models": {
        "gpt-4o": { "id": "gpt-4o", "name": "GPT-4o (via LiteLLM)" }
      }
    }
  }
}
```

| Field | Default | Meaning |
|---|---|---|
| `command` | _(required)_ | Shell command whose stdout is the token (trailing whitespace trimmed). |
| `scheme` | `"Bearer"` | Prefix scheme; the header value becomes `"<scheme> <token>"`. Set `""` for a bare token (e.g. an `x-api-key`). |
| `header` | `"Authorization"` | Header name to set. |
| `ttl` | `3600` | Seconds to cache the token before re-fetching. Refresh happens within a 10% buffer (clamped to 5–60s) before expiry. |

How it works: on every LLM request the plugin's `chat.headers` hook runs the
`command`, injects the resulting token (prefixed by `scheme`) into `header`,
and caches the token keyed by provider. On subsequent requests within the TTL
the cached token is reused; once `ttl - buffer` elapses it re-fetches. A token
fetch failure is logged to stderr (`[auth-helper] failed for <provider>: ...`)
and leaves the header untouched for that request.

## Gotchas

- **`id` is required on every model entry.** A model defined as
  `"gpt-4o": { "name": "..." }` (no `id`) fails with
  `ProviderModelNotFoundError: Model not found: litellm-prod/gpt-4o`. Always
  repeat the key as `"id"`.
- **Models are NOT auto-discovered.** Defining a provider with no `models` map
  does NOT cause opencode to populate models from the proxy's `GET /v1/models`.
  Every model you want to use must be listed explicitly (with `id`). (opencode
  does issue a `GET /v1/models` for validation, but it does not register the
  returned models as selectable.)
- **`@ai-sdk/openai-compatible` is bundled** in the opencode binary — the `npm`
  field is a marker that maps to the bundled package. No network install or
  Bun cache pre-warming is needed.
- **A placeholder `apiKey` is still required** when using `apiKeyHelper`. The AI
  SDK provider constructor errors without an `apiKey`; the plugin then overrides
  the real `Authorization` header on each request. (Proven: the request carries
  the helper's token, not the placeholder.)
- **The plugin overrides the SDK's `apiKey`-derived header.** If you set both
  `apiKey` and `apiKeyHelper`, the helper's header wins for the header it
  targets (default `Authorization`).
- **Tokens are cached in-process.** The cache does not persist across opencode
  restarts — the helper re-runs once on the first request after startup. This is
  fine for a 3600s TTL; for very short TTLs, expect a fetch on each cold start.

## Verification

**Phase 1** — Proven end-to-end against a local OpenAI-compatible mock: opencode
loaded the provider from a file-based `opencode.json`, resolved the model, issued
`GET /v1/models` + `POST /v1/chat/completions`, and parsed the streamed (chunked
SSE) response.

**Phase 2** — Proven against the same mock plus a token-printing script that
returns a unique value on every call. With `apiKeyHelper` configured and the
plugin installed under `.opencode/plugins/`, opencode issued multiple
`POST /v1/chat/completions` requests all carrying `Authorization: Bearer <token>`
where `<token>` was the helper's output (not the placeholder `apiKey`), and all
requests in the session shared one token — confirming the helper ran once and the
cache served the rest.

## Development

The plugin ships with a TypeScript type-check (`tsc --noEmit`, strict) and a
`bun:test` unit suite covering header injection, caching, TTL refresh, custom
headers, the no-op path, and command-failure handling. From `plugins/litellm/`:

```bash
bun install        # fetch devDeps (@opencode-ai/plugin, @types/bun, typescript)
bun run typecheck  # strict type-check
bun test           # unit tests
```

These also run in CI (the **Plugin** job). `@opencode-ai/plugin` provides the
types that resolve at runtime inside opencode; the devDependency here is purely
so the plugin is type-checked and tested outside the runtime.

## Roadmap

- **Phase 3 — real targets.** Point `baseURL` at a real LiteLLM instance and set
  `apiKeyHelper.command` to the JWT minting command for your IdP (e.g. an
  `okta-jwt` CLI, a `gcloud auth print-identity-token`, or a small script that
  hits the token endpoint). The plugin is already JWT-ready — only the command
  string changes; no plugin code edit is needed. Requires: the LiteLLM model
  list, the IdP domain/clientId/authServer/scopes, and the JWT claim shape
  LiteLLM validates.

## License

MIT
