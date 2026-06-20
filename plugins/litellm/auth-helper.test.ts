import { test, expect } from "bun:test"
import { $ } from "bun"
import { AuthHelperPlugin } from "./auth-helper"

// Minimal hook harness: build a chat.headers input + output, invoke the hook.
async function callHeaders(
  hooks: Awaited<ReturnType<typeof AuthHelperPlugin>>,
  options: Record<string, unknown>,
  providerId = "litellm-prod"
) {
  const output = { headers: {} as Record<string, string> }
  // deno-lint-ignore no-explicit-any
  await (hooks as any)["chat.headers"](
    {
      provider: {
        source: "config",
        info: { id: providerId },
        options,
      },
    },
    output
  )
  return output
}

test("injects a Bearer token from the helper command (defaults)", async () => {
  const hooks = await AuthHelperPlugin({ $ } as never)
  const out = await callHeaders(hooks, {
    apiKeyHelper: { command: "echo tok-fixed-123" },
  })
  expect(out.headers.Authorization).toBe("Bearer tok-fixed-123")
})

test("caches the token within the TTL — one fetch serves repeated calls", async () => {
  const hooks = await AuthHelperPlugin({ $ } as never)
  // date +%s%N returns a different value on every invocation; if the cache
  // works, both calls surface the SAME token (the first fetch's output).
  const first = await callHeaders(hooks, {
    apiKeyHelper: { command: "date +%s%N", ttl: 3600 },
  })
  const second = await callHeaders(hooks, {
    apiKeyHelper: { command: "date +%s%N", ttl: 3600 },
  })
  expect(second.headers.Authorization).toBeDefined()
  expect(second.headers.Authorization).toBe(first.headers.Authorization)
  expect(second.headers.Authorization).toMatch(/^Bearer \d+$/)
})

test("refreshes after the TTL elapses", async () => {
  const hooks = await AuthHelperPlugin({ $ } as never)
  const first = await callHeaders(hooks, {
    apiKeyHelper: { command: "date +%s%N", ttl: 1 },
  })
  // ttl=1s, refresh buffer = max(5, floor(0.1)) = 5s → buffer (5s) > ttl,
  // so the token is always considered stale → a fresh fetch each call.
  await new Promise((r) => setTimeout(r, 20))
  const second = await callHeaders(hooks, {
    apiKeyHelper: { command: "date +%s%N", ttl: 1 },
  })
  expect(second.headers.Authorization).not.toBe(first.headers.Authorization)
})

test("supports a custom header with a bare (scheme-less) token", async () => {
  const hooks = await AuthHelperPlugin({ $ } as never)
  const out = await callHeaders(hooks, {
    apiKeyHelper: { command: "echo raw-key-xyz", scheme: "", header: "x-api-key" },
  })
  expect(out.headers["x-api-key"]).toBe("raw-key-xyz")
  expect(out.headers.Authorization).toBeUndefined()
})

test("is a no-op when no apiKeyHelper is configured", async () => {
  const hooks = await AuthHelperPlugin({ $ } as never)
  const out = await callHeaders(hooks, { baseURL: "http://example.com/v1" })
  expect(Object.keys(out.headers)).toHaveLength(0)
})

test("leaves the header untouched when the command fails", async () => {
  const hooks = await AuthHelperPlugin({ $ } as never)
  const out = await callHeaders(hooks, {
    apiKeyHelper: { command: "exit 3" },
  })
  expect(Object.keys(out.headers)).toHaveLength(0)
})
