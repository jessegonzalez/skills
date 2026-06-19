# GitOps with Argo CD

Argo Rollouts is a **standalone** controller — it does not require Argo CD. But the two pair naturally: Argo CD declaratively syncs the Rollout manifest from Git; Argo Rollouts drives the in-cluster deployment strategy. Internalize one fact and most GitOps-with-Rollouts confusions dissolve:

> **Argo Rollouts is Git-blind.** It reconciles Kubernetes state, never reads or writes Git. There is no Argo Rollouts "API" beyond the Kubernetes API + the kubectl plugin (which itself just patches/reads the `Rollout`).

For day-2 commands under GitOps, see `kubectl-plugin.md`. For state-machine semantics, see `state-machine.md`. For notifications on abort/pause, see `notifications.md`.

## Division of labor

```
   Git (source of truth for desired manifest)
     │
     ▼  (sync)
   Argo CD ──applies──► Rollout object (live spec)
                          │
                          ▼  (reconcile)
                    Argo Rollouts controller
                          │ owns: ReplicaSets, Service selectors,
                          │       AnalysisRuns, Experiments, mesh CRs
                          ▼
                     Live cluster state
                     (status.stableRS, status.phase, ...)
```

- Argo CD writes **desired state** (the `Rollout` manifest, e.g. image tag N+1).
- Argo Rollouts reads that and drives the **delivery mechanics** (canary walk, analysis, traffic shift), writing **status** and mutating Services/mesh CRs.

**Rule of thumb:** let Argo Rollouts own the things it mutates (ReplicaSets, canary/stable/active/preview Services, Istio VirtualService weights). Don't have Argo CD fight those.

## The "endless rollback loop" — why it does NOT happen

The classic worry: "If Rollouts reverts to N and Git says N+1, won't Argo CD re-apply N+1 forever?" **No.** Walk through it:

1. Git has N+1; Argo CD syncs → live `Rollout` spec = N+1.
2. Rollouts begins the strategy; N+1 fails analysis → **aborts**, reverts **live cluster** traffic to stable (N). It does **not** change the `Rollout` spec back to N.
3. Argo CD compares Git's `Rollout` spec (N+1) against live spec (N+1) → **no diff** → Application stays `Healthy`/`Synced` (the *spec* matches; only the *runtime* rolled back).
4. The `Rollout`'s `status` shows `Degraded`/`Aborted`; Argo CD's Lua health check surfaces that.

Resolution = **roll forward**: fix the issue, push N+2 to Git, Argo CD syncs, Rollouts tries again. You do *not* need to revert Git, and you do *not* need Argo CD's `argocd app rollback` (that points the app at an older Git commit — rarely needed when Rollouts is present). If you truly want Git updated on rollback, wire external glue (a notification → CI job that opens a PR). The controller won't do it.

## Argo CD's built-in Rollouts awareness

Argo CD ships Lua customizations for `Rollout`:

- **Health check** maps Rollout phase → Argo CD health: `Progressing`→Progressing, `Paused`→**Suspended**, `Healthy`→Healthy, `Degraded`/`Aborted`→Degraded. A paused rollout shows the Argo CD Application as **Suspended**, not unhealthy.
- **Resource actions** (clickable in UI, or `argocd app actions run <APP> <ACTION>`):
  - `resume` — unpause a paused Rollout (`spec.paused: false`).
  - `restart` — set `spec.restartAt` → controller rolling-restarts pods without a new ReplicaSet.

```bash
argocd app actions run <APP> restart
argocd app actions run <APP> resume
```

This is the GitOps-friendly way to do day-2 ops *without* leaving the Argo CD UX or bypassing Git auditing.

## Promoting / aborting from CI or GitOps

Since there's no separate API, "promote" = a patch. Use whichever client you have:

```bash
kubectl argo rollouts promote NAME [--full]                                     # plugin
kubectl argo rollouts abort NAME                                                # plugin

# Equivalent raw patches (CI-friendly, no plugin needed):
kubectl patch rollout NAME --type merge -p '{"spec":{"paused":false}}'           # resume
kubectl patch rollout NAME --type merge -p '{"spec":{"restartAt":"<RFC3339 UTC>"}}'  # restart
```

**Design pattern:** let the `pause: {}` step be the human/CI gate. A rollout reaches e.g. 20%, pauses indefinitely; CI that's satisfied with canary metrics calls `promote`. If metrics fail, the analysis step aborts automatically. Git stays declarative; the promote/abort decision is operational, not a Git commit.

```yaml
steps:
  - setWeight: 5
  - pause: { duration: 30m }   # bake; optionally run smoke tests via a Job/Web analysis step
  - setWeight: 25
  - pause: { duration: 30m }
  - setWeight: 50
  - pause: {}                  # INDEFINITE — human/CI promotes via CLI/Argo CD action
```

## Common pitfalls & fixes

### Self-heal fights a mid-flight rollout
Argo CD self-heal sees the controller-modified ReplicaSets/Services as drift and tries to "correct" them mid-deployment → flapping.

**Fix:** for the Application that owns the Rollout, either set `spec.syncPolicy.selfHeal: false`, or scope the Application to manage *only* the Rollout + AnalysisTemplate + Service skeletons, and let Rollouts own the rest. Services' selectors will be rewritten by the controller regardless; that's expected.

### Both controllers managing the same Service
If Argo CD tries to enforce a fixed selector on the active/canary Service while Rollouts is rewriting it with pod-template-hash, you get a fight.

**Fix:** let Rollouts "own" these Services (annotate them `argo-rollouts.argoproj.io/managed-by-rollouts`). Argo CD can still create them initially; just don't fight their selectors.

### Istio VirtualService weight flapping
The Rollout rewrites VirtualService weights during an update; Argo CD sees the drift and snaps them back.

**Fix:**

```yaml
spec:
  ignoreDifferences:
    - group: networking.istio.io
      kind: VirtualService
      jqPathExpressions:
        - .spec.http[].route[].weight
  syncPolicy:
    syncOptions: [ApplyOutOfSyncOnly=true, RespectIgnoreDifferences=true]
```

### ConfigMap/Secret rollouts + premature pruning
Hashing a ConfigMap to trigger a Rollout works, but if Argo CD prunes the old ConfigMap immediately, experiments and rollbacks break (they reference the old hash).

**Fix:** defer pruning until the rollout succeeds:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config-7270e14e6
  annotations:
    argocd.argoproj.io/sync-options: PruneLast=true
```

### "Degraded" forever after abort
After an abort the cluster is healthy (running the previous good version) but the Rollout object is Degraded and Git still has the bad revision. That's **correct**. Resolve by pushing a fix (v3) or reverting Git to v1.

### Status fields in Git / sync ordering
Don't put Rollout `status` fields in Git (read-only). Use Argo CD sync waves to order: install AnalysisTemplates/Services first (wave `-1`), then the Rollout (wave `0`).

## `workloadRef` for split ownership

When CI/another controller already owns a `Deployment` and you don't want to migrate the manifest, have the Rollout reference it (full migration recipe: `install-config.md`):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
spec:
  replicas: 5
  selector: { matchLabels: { app: x } }
  workloadRef:
    apiVersion: apps/v1
    kind: Deployment
    name: x
    scaleDown: onsuccess      # never | onsuccess | progressively
  strategy: { canary: { steps: [...] } }
```

- `never` — Deployment keeps running its own pods (side-by-side; double capacity during migration).
- `onsuccess` — Deployment scaled to 0 once the Rollout is healthy.
- `progressively` — as Rollout scales up, Deployment scales down.

The controller annotates the Rollout with `rollout.argoproj.io/workload-generation` and exposes `status.workloadObservedGeneration` so you can tell whether the Rollout has caught up to the referenced Deployment's current generation. To update, **change the Deployment's pod template** (not the Rollout's).

## Scope, HA, and multi-cluster realities

- **Single-cluster, single-application.** The controller must run in **every** cluster that hosts Rollout workloads (unlike Argo CD, Rollouts cannot manage external clusters from a central install).
- **HA controller:** run multiple replicas with `--leader-elect` (client-go leader election; tune `--leader-election-lease-duration` / `--leader-election-renew-deadline` for clock-skew tolerance).
- **No multi-app dependency orchestration.** If "frontend rollout must abort if backend rollout fails," build that on top (one Rollout per app; make services bw/fw compatible; wire notifications).
- **Application-of-Applications:** manage Rollouts as Argo CD `Application` resources (one per cluster/env), pointing at a shared Git path with env-specific kustomize overlays. Rollouts CRD + controller must be installed on **every** cluster that runs Rollouts — it can't be centralized the way Argo CD can.

## Practical wiring checklist

- [ ] Argo CD `Application` syncs the Rollout manifest only (not the ReplicaSets Argo Rollouts creates).
- [ ] `AnalysisTemplate`/`ClusterAnalysisTemplate` synced before first rollout.
- [ ] canary/stable/active/preview Services synced once; selectors left to the controller.
- [ ] Self-heal disabled or scoped for the Rollout Application.
- [ ] Mesh resources (e.g. Istio VirtualService) synced from Git; Rollouts rewrites only the `weight` fields (`ignoreDifferences` configured).
- [ ] Notifications wired so humans know when an abort happened (`notifications.md`).
