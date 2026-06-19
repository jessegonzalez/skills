# litellm

> An opencode custom model provider that fronts a [LiteLLM](https://github.com/BerriAI/litellm) (or any OpenAI-compatible) proxy.

## Status

**Phase 1 — provider config (proven).** This documents the static provider
configuration that makes opencode route requests through a LiteLLM proxy.
Phase 2 will add an opencode plugin (`.opencode/plugins/`) that injects
short-lived Okta JWTs as the `Authorization` header on a background refresh
cadence.

> **Scope note:** LiteLLM is an OpenAI-compatible proxy; opencode has no native
> "litellm" provider type. This is an opencode custom provider built on the
> bundled `@ai-sdk/openai-compatible` package. It is **not** a Claude Code
> marketplace plugin, so it is intentionally not registered in
> `.claude-plugin/marketplace.json` or covered by release-please.

## Configuration

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
- **Static `apiKey` only (phase 1).** For dynamic credentials (Okta JWT), the
  `apiKey`/headers must be injected by a plugin at runtime — see phase 2.

## Verification (phase 1 proof)

Proven end-to-end against a local OpenAI-compatible mock: opencode loaded the
provider from a file-based `opencode.json`, resolved the model, issued
`GET /v1/models` + `POST /v1/chat/completions`, and parsed the streamed
(chunked SSE) response. The mock proxy confirmed request routing; the
assistant surfaced the streamed phrase.

## Roadmap

- **Phase 2 — Okta JWT refresh (opencode plugin).** An
  `.opencode/plugins/litellm-auth.ts` plugin that mints a JWT from Okta
  (client-credentials or authorization-code flow), injects it as
  `Authorization: Bearer <jwt>` into the provider's requests, and refreshes it
  on a background timer before its ~1h TTL expires. Likely mechanism: the
  `chat.headers` callback hook or the special `provider`/`auth` object hooks
  (per the customize-opencode skill). Requires: Okta domain/clientId/authServer/
  scopes, the LiteLLM model list, and the JWT claim shape LiteLLM validates.

## License

MIT
