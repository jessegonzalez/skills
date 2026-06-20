import type { Plugin } from "@opencode-ai/plugin"

// Generic auth-token helper plugin.
//
// Reads an `apiKeyHelper` block from each provider's `options` and, on every
// LLM request, injects the helper's token into the request headers. The token
// is cached in-memory and refreshed before its TTL expires.
//
// Provider config (in opencode.json):
//   "options": {
//     "baseURL": "...",
//     "apiKey": "placeholder",                    // required by the AI SDK; overridden by this plugin
//     "apiKeyHelper": {
//       "command": "okta-jwt --client-id xyz",   // shell command; stdout = token
//       "scheme": "Bearer",                        // default; "" = bare token
//       "header": "Authorization",                 // default
//       "ttl": 3600                                // default (seconds)
//     }
//   }

interface HelperConfig {
  command: string
  scheme: string
  header: string
  ttl: number
}

interface CacheEntry {
  token: string
  fetchedAt: number
}

const DEFAULT_SCHEME = "Bearer"
const DEFAULT_HEADER = "Authorization"
const DEFAULT_TTL = 3600

function refreshBufferSeconds(ttlSeconds: number): number {
  return Math.min(60, Math.max(5, Math.floor(ttlSeconds * 0.1)))
}

export const AuthHelperPlugin: Plugin = async ({ $ }) => {
  const cache = new Map<string, CacheEntry>()

  async function getToken(providerId: string, cfg: HelperConfig): Promise<string> {
    const bufferMs = refreshBufferSeconds(cfg.ttl) * 1000
    const ttlMs = cfg.ttl * 1000
    const now = Date.now()
    const entry = cache.get(providerId)
    if (entry && now - entry.fetchedAt < ttlMs - bufferMs) {
      return entry.token
    }
    const result = await $`sh -c ${cfg.command}`.quiet().nothrow()
    const token = String(result.stdout).trim()
    if (result.exitCode !== 0 || !token) {
      throw new Error(
        `apiKeyHelper for provider "${providerId}" exited ${result.exitCode} with empty output`
      )
    }
    cache.set(providerId, { token, fetchedAt: now })
    return token
  }

  return {
    "chat.headers": async (input, output) => {
      const opts = (input.provider?.options ?? {}) as Record<string, unknown>
      const raw = opts.apiKeyHelper as Partial<HelperConfig> | undefined
      if (!raw || typeof raw.command !== "string" || !raw.command) return

      const cfg: HelperConfig = {
        command: raw.command,
        scheme: typeof raw.scheme === "string" ? raw.scheme : DEFAULT_SCHEME,
        header:
          typeof raw.header === "string" && raw.header ? raw.header : DEFAULT_HEADER,
        ttl: typeof raw.ttl === "number" && raw.ttl > 0 ? raw.ttl : DEFAULT_TTL,
      }

      const providerId =
        input.provider?.info?.id ?? input.model?.providerID ?? "unknown"

      try {
        const token = await getToken(providerId, cfg)
        const value = cfg.scheme ? `${cfg.scheme} ${token}` : token
        output.headers[cfg.header] = value
      } catch (e) {
        console.error(`[auth-helper] failed for ${providerId}: ${String(e)}`)
      }
    },
  }
}
