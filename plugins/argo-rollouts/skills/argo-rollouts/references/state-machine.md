# Rollout State Machine

This is the authoritative reference for *how a Rollout advances*: its phases, conditions, and the precise semantics of pause/abort/rollback. Read this whenever a user asks "why is my rollout stuck", "what does promote do", "how does rollback work", or when you need to reason about step ordering.

For day-2 commands that drive this state machine, see `kubectl-plugin.md`. For the diagnostic runbook, see `troubleshooting.md`.

## Reconciler loop (the engine)

The controller reconciles on any change to a `Rollout`, owned `ReplicaSet`, `AnalysisRun`, or `Experiment`, plus a resync interval. Each pass:

1. Computes the **desired** ReplicaSet from `.spec.template` (hash it → `currentPodHash`).
2. Compares against `status.stableRS` (the known-good hash) and the last promoted hash.
3. If `currentPodHash == stableRS` and no in-flight update → **Healthy**; just reconcile replicas (HPA may change `spec.replicas`).
4. If `currentPodHash != stableRS` → an update is in flight; execute the current step and only advance when its gate is satisfied.
5. On initial creation (no stable RS yet) → scale straight to `spec.replicas`, mark that RS stable. **Steps are skipped on the very first deploy** (same as Deployment).

## Phases

A Rollout's `status.phase` is one of:

| Phase | Meaning | Traffic |
|-------|---------|---------|
| `Healthy` | `currentPodHash == stableRS`, fully available, no in-flight update. | 100% to stable. |
| `Progressing` | An update is in flight and actively advancing (scaling RS, walking steps). | Per current step weight. |
| `Paused` | Held by a `pause` step, manual pause, `autoPromotionEnabled: false`, or an `Inconclusive` analysis. | Held at current weight. |
| `Degraded` | Update failed: analysis `Failed`, or `progressDeadlineAbort` triggered, or post-promotion analysis failed (blue-green). Can also describe the cluster state after an abort. | Reverted toward stable. |
| `Aborted` | Explicitly aborted (`kubectl argo rollouts abort`) or auto-aborted. Canary weight → 0; canary RS scaled down after `abortScaleDownDelaySeconds`. | 100% to stable. |

Argo CD's Lua health check maps these to its own `Progressing`/`Suspended`/`Degraded`/`Healthy` health states — `Paused` shows as **Suspended** in Argo CD (not unhealthy). See `gitops-argocd.md`.

## Status conditions & pause reasons

`status.conditions` exposes `Healthy`, `Progressing` (with reasons like `ReplicaSetUpdated`, `NewReplicaSetAvailable`), etc. `status.pauseConditions` enumerates *why* it paused, e.g.:

- `StepPause` — a `pause` step (timed `{duration: ...}` or indefinite `{}`).
- `BlueGreenPause` — blue-green waiting for manual promotion (`autoPromotionEnabled: false`, no `autoPromotionSeconds`).
- `AnalysisRunInconclusive` — analysis neither succeeded nor failed; needs a human.

When debugging a paused rollout, **read `status.pauseConditions[*].reason`** — it tells you exactly which gate is holding things up.

## Step types and their semantics (`spec.strategy.canary.steps`)

Steps are an ordered list; the controller executes them in order and only advances when the current one is satisfied. Each item is one of:

- **`setWeight: <int 0–100>`** — set the canary traffic/replica ratio. For traffic-routed canaries this also rewrites the mesh/ingress CR. (Percent of `maxTrafficWeight` if that field is set; default 100.)
- **`pause: { duration: 30m }`** — timed pause (`s`/`m`/`h`). `pause: {}` → indefinite until `promote`/`resume`.
- **`setCanaryScale:`** — decouple canary *replica count* from traffic weight (traffic-routed only). `{replicas: N}`, `{weight: W}`, or `{matchTrafficWeight: true}` (default).
- **`analysis:`** — inline step that starts an `AnalysisRun` and **blocks** until it is terminal. Successful → advance; Failed → abort; Inconclusive → pause.
- **`experiment:`** — spin up parallel ReplicaSets (e.g. baseline+canary) for A/B/statistical comparison; may run analyses over them.
- **`setHeaderRoute:`** — (Istio / Gateway API plugin) header-based routing to canary. Requires the route name in `trafficRouting.managedRoutes`.
- **`setMirrorRoute:`** — (Istio) mirror a % of matching traffic to canary; response is discarded. Requires `managedRoutes`.
- **`plugin:`** — a step plugin's custom behavior.
- **`replicaProgressThreshold:`** — gate advancement on a % or absolute number of ready replicas (useful with HPA for fast promotion).

A bare `setHeaderRoute: { name: x }` with no `match` *removes* the route (same for mirror). `managedRoutes` ordering sets route **precedence** — Argo places them above any manually-defined routes, and **removes all managed routes at end-of-rollout or on abort** (never put manually-created routes in that list).

## Promotion (`promote` / `resume`)

- `kubectl argo rollouts promote NAME` advances to the **next** pause. `--full` skips all remaining pauses and completes the rollout. Equivalent: patch the step index / `spec.paused`.
- `kubectl argo rollouts resume NAME` clears a **manual** pause (one set by `kubectl argo rollouts pause` or `spec.paused: true`). It does *not* skip timed step pauses the way `promote` does.
- `pause` + `resume` round-trip a user-controlled pause; `promote` is for advancing through the strategy.

For blue-green with `autoPromotionEnabled: false`, `promote` flips the active Service to the new ReplicaSet.

## Abort & auto-abort

- `kubectl argo rollouts abort NAME` sets the rollout to aborted: canary weight → 0, `AnalysisRun`s terminated, phase → `Aborted`/`Degraded`. Traffic returns to the stable RS. For traffic-routed canaries, the canary RS scales down after `abortScaleDownDelaySeconds` (default 30; 0 = keep it up).
- **Auto-abort triggers:** an analysis run going `Failed`; `progressDeadlineAbort: true` when `progressDeadlineSeconds` elapses; a blue-green `postPromotionAnalysis` failing (which also flips the active service back).
- **Abort does not touch Git.** The cluster reverts; the manifest still says the new image. Fix forward in Git, then re-apply.

## Rollback (`undo`) — fast-track vs full

There are two regimes, and which one you're in depends on whether the old ReplicaSet is still alive:

1. **Fast-track rollback.** While the previous RS is still scaled up (within `scaleDownDelaySeconds`, default 30s, tracked by the `argo-rollouts.argoproj.io/scale-down-deadline` annotation on the RS), `undo` / re-applying the old manifest makes the controller immediately re-point the active/stable Service selector at the old hash and strip the scale-down annotation. It does **not** replay the strategy — it just reverts the selector.
2. **Full rollback.** Once the old RS has been scaled down (deadline passed or scaled to 0), rolling back means re-introducing an old template as if it were new — the strategy steps run again from the top (blue-green re-deploys preview; canary re-walks `setWeight: 5 → ...`).

The `rollbackWindow.revisions` field (at `spec.strategy.<canary|blueGreen>.rollbackWindow.revisions`) widens the set of revisions eligible for fast-track beyond just the most recent one.

**Implication:** if you might need to roll back, don't set `scaleDownDelaySeconds` too low, and consider `revisionHistoryLimit` (default 10) — old RS objects must exist to fast-track. Lowering `revisionHistoryLimit` saves controller memory at scale but narrows the fast-track window.

## Mid-rollout template change

If `.spec.template` changes *during* an in-flight rollout (e.g. someone pushes another image tag mid-canary), the controller **aborts the currently-in-flight RS** and starts a new one from the updated template. There is no "queue" — the newest desired state always wins, restarting the strategy from step 0 against the previous stable RS.

## `progressDeadlineSeconds` and `progressDeadlineAbort`

- `progressDeadlineSeconds` (default 600) — if the rollout makes no progress for this long, a `ProgressDeadlineExceeded` condition is set. By default this does **not** abort.
- `progressDeadlineAbort: true` — turn that condition into an actual abort. Enable when you want stalls to auto-rollback rather than hang.

## Key status fields to read

| Field | What it tells you |
|---|---|
| `status.phase` | Current phase (see above). |
| `status.stableRS` | The hash considered known-good. |
| `status.currentPodHash` | The hash the controller is trying to reach. Equal to `stableRS` → fully promoted. |
| `status.currentStepIndex` | Which step is executing. |
| `status.controllerPause`, `status.pauseConditions` | Whether/why it's held. |
| `status.canary.weights` / `status.alb.*` / `status.istio.*` | Router-specific status. |
| `status.abort`, `status.message` | Abort state and human-readable cause. |

Compare `status.stableRS` and `status.currentPodHash` first — equal means fully promoted, different means an update is in flight (or aborted).
