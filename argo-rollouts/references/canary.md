# Canary Strategy

A canary exposes a subset of traffic to the new version, then gradually increases exposure while you verify correctness. The controller walks an ordered list of **steps** under `spec.strategy.canary.steps`; each step runs only after the previous one is satisfied.

> Field path: `spec.strategy.canary` (kind `Rollout`, `apiVersion: argoproj.io/v1alpha1`).
> For strategy trade-offs vs blue-green, see `strategy-decisions.md`. For step semantics and rollback, see `state-machine.md`.

## Steps run only on update

Steps execute when `spec.template` changes — **never** on initial creation. The very first apply of a Rollout scales the ReplicaSet straight to `spec.replicas` (like a Deployment). "My steps were ignored" almost always means you are looking at the initial deploy.

## The step kinds

| Step | Purpose |
|---|---|
| `setWeight: <int>` | Set the % of traffic/replicas to the canary (0–100, or 0–`maxTrafficWeight`). |
| `pause: {}` / `pause: { duration: 10m }` | Wait indefinitely, or for a duration. Units `s`/`m`/`h`; bare numbers are seconds. |
| `analysis: { ... }` | Run a blocking inline AnalysisRun at this point. |
| `experiment: { ... }` | Launch an Experiment (baseline vs canary) as a blocking step. |
| `setCanaryScale: { ... }` | Pin canary replica count independently of traffic weight (router only). |
| `setHeaderRoute: { ... }` | Header-based routing to canary (Istio / Gateway API plugin). |
| `setMirrorRoute: { ... }` | Mirror/shadow a % of matching traffic to canary (Istio). |
| `plugin: { ... }` | Invoke a registered step plugin. |
| `replicaProgressThreshold: { ... }` | Promote once N% (or N) replicas are ready — useful with HPA. |

`setHeaderRoute`/`setMirrorRoute` require the route name in `trafficRouting.managedRoutes`. A bare `setHeaderRoute: { name: x }` with no `match` *removes* the route (same for mirror).

## Basic canary (no traffic router) — pod-ratio approximation

Without `trafficRouting`, the controller approximates the requested weight by the **ratio of canary to stable replicas**. With 5 replicas and `setWeight: 20`, it scales canary→1, stable→4. Weights that don't divide evenly are rounded (41% of 10 → 4 canary pods). Fine-grained canaries (1%, 5%) are impossible at low replica counts — they require a mesh or ingress.

```yaml
strategy:
  canary:
    maxSurge: "25%"        # default "25%"
    maxUnavailable: 0      # default "25%"; cannot be 0 if maxSurge is 0
    steps:
      - setWeight: 10
      - pause: { duration: 1h }
      - setWeight: 20
      - pause: {}          # manual gate
```

Omit `steps` entirely → canary degrades to standard rolling-update behavior governed only by `maxSurge`/`maxUnavailable`.

### `maxSurge` / `maxUnavailable` semantics

- **`maxSurge`** (`int` or `"%"`): pods scheduled *above* `spec.replicas`. Percentage rounds **up**. Default `25%`.
- **`maxUnavailable`** (`int` or `"%"`): pods that may be unavailable during the update. Percentage rounds **down**. Default `25%`.
- They **cannot both be 0**. `maxUnavailable: 0` is common and forces `maxSurge > 0` — this gives zero capacity loss during the rollout at the cost of surge pods.

## Traffic routing unlocks the rest

Adding `spec.strategy.canary.trafficRouting` flips two things at once:

1. **Traffic split becomes exact and independent of pod counts.** `setWeight: 20` means precisely 20% of requests, regardless of canary pod count.
2. **The stable ReplicaSet stays fully scaled** through the rollout so an abort can instantly redirect traffic.

The following fields are **no-ops without a router**: `scaleDownDelaySeconds`, `abortScaleDownDelaySeconds`, `dynamicStableScale`, `setCanaryScale`, `minPodsPerReplicaSet`, `setHeaderRoute`, `setMirrorRoute`, `pingPong`. See `traffic-routing.md` for per-provider configuration.

## Dynamic canary scale (router only)

By default the canary replica count tracks the current `setWeight`. `setCanaryScale` decouples them:

```yaml
steps:
  - setCanaryScale: { replicas: 3 }               # exactly 3 canary pods
  - setCanaryScale: { weight: 25 }                # 25% of spec.replicas
  - setCanaryScale: { matchTrafficWeight: true }  # back to default coupling
```

Use cases: scale the canary for testing while `setWeight: 0` (not yet public), header-based canaries, scaling to 100% for traffic shadowing, and isolating a leaky canary from the HPA (see `strategy-decisions.md`).

**Footgun:** after a `setCanaryScale` with explicit `replicas`/`weight`, subsequent `setWeight` steps **no longer change the replica count** — only traffic. You can accidentally send 90% of traffic to 10% of pods. Reset with `matchTrafficWeight: true` to restore the default coupling.

## Dynamic stable scale (router only, v1.1+)

By default the stable ReplicaSet stays at 100% for the whole update so an abort can instantly redirect traffic. Setting `dynamicStableScale: true` scales stable down as canary weight rises, halving total pod count (resource savings) at the cost of slower abort recovery:

```yaml
strategy:
  canary:
    dynamicStableScale: true
    abortScaleDownDelaySeconds: 600   # keep canary up briefly on abort (default 30)
```

## Header & mirror routes (router only)

Opt-in canaries (cookie-free) and traffic shadowing live here. Both require the route name in `trafficRouting.managedRoutes` (order = precedence); the controller inserts them above any manually-defined routes and removes all managed routes at end-of-rollout or abort. See `traffic-routing.md` for the full match syntax.

```yaml
steps:
  - setWeight: 20
  - setHeaderRoute:
      name: internal-testers          # must be in managedRoutes
      match:
        - headerName: x-env
          headerValue: { exact: staging }     # or prefix / regex
  - setMirrorRoute:
      name: shadow
      percentage: 35
      match:
        - method: { exact: GET }
          path: { prefix: / }
```

Header routing is the basis for **cookie-free opt-in canaries** (e.g. "internal testers opt in via a header"), which avoids the sticky-session skew that biases canary metrics.

## `replicaProgressThreshold` (HPA-friendly promotion)

Gate step advancement on a fraction (or absolute count) of ready replicas. Useful with HPA when you want the rollout to advance as soon as enough new pods are ready, rather than waiting on the full target count. Pair with `setCanaryScale` for tight control.

## Full field reference

```yaml
strategy:
  canary:
    canaryService: string            # required for traffic routing
    stableService: string            # required for traffic routing
    pingPong: { pingService: ..., pongService: ... }  # alt to canary/stable svc
    canaryMetadata: { labels: {}, annotations: {} }   # ephemeral pod metadata
    stableMetadata: { labels: {}, annotations: {} }
    maxSurge: "25%"
    maxUnavailable: 1
    scaleDownDelaySeconds: 30          # old-RS teardown delay (router only; default 30)
    scaleDownDelayRevisionLimit: 2
    abortScaleDownDelaySeconds: 30     # canary teardown delay on abort (router only)
    minPodsPerReplicaSet: 2            # HA floor per RS (router only); default 1
    dynamicStableScale: false          # shrink stable as canary grows (router only)
    trafficRouting: { istio|nginx|alb|smi|plugins: ... }
    analysis: { templates: [...], args: [...], startingStep: int }   # BACKGROUND analysis
    antiAffinity: { preferredDuringScheduling...: { weight: 1..100 } | requiredDuringScheduling...: {} }
    steps: [ ... ]
```

## HPA interaction

A single HPA targeting the Rollout sees both ReplicaSets' pods under one selector — it computes one average metric and scales `spec.replicas`. The controller then distributes those replicas across canary/stable per the current step. Without a router this is coarse; with a router a faulty canary can drag stable up via the combined average. Use `setCanaryScale` (pin canary count) or `dynamicStableScale` (shrink stable) to isolate. Full discussion: `strategy-decisions.md`.

## Common authoring mistakes

- **Bare `pause: {}` when a timed pause was intended.** Confirm intent — `{}` waits forever.
- **`maxUnavailable: 0` and `maxSurge: 0` together** — invalid.
- **`setCanaryScale` then expecting `setWeight` to also scale replicas** — it won't. Reset with `matchTrafficWeight: true`.
- **Requesting a 1% canary on a basic (no-router) rollout with few replicas** — impossible; need a router or more replicas.
- **Forgetting `managedRoutes:` for header/mirror steps** — the route is never created.
