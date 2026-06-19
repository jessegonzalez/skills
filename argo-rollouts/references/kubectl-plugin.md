# `kubectl argo rollouts` Plugin

The `kubectl argo rollouts` plugin is the primary day-2 interface. It is a thin client: it **patches the `Rollout` object** or reads its `status`. There is no separate API server. It speaks to the Kubernetes API using your kubeconfig credentials (so it has your RBAC permissions).

For install instructions, see `install-config.md`. For the state machine these commands drive, see `state-machine.md`. For the symptom→cause→fix runbook, see `troubleshooting.md`.

## The five-second mental model for any incident

1. `get rollout <name> -w` → see current phase, weights, pause reasons.
2. If `Degraded` after an abort → re-apply the stable manifest (or `set image` to the stable image).
3. If `Progressing` and stuck on a `pause: {}` → `promote` (or `promote --full`).
4. If an AnalysisRun is `Failed`/`Error` → inspect `kubectl argo rollouts get analysisrun ...` to see which metric tripped.
5. If traffic isn't moving → check `trafficRouting` refs and Service selectors (`troubleshooting.md`).

## Watching & inspecting

### `get rollout` — the primary live view

```bash
kubectl argo rollouts get rollout NAME          # tree view, one-shot
kubectl argo rollouts get rollout NAME -w       # tree view, watch (live)
kubectl argo rollouts get rollout NAME -o json  # raw object
kubectl argo rollouts get rollout NAME -o yaml
```

**What to look for** in the tree output:

- Which ReplicaSet is `stable` vs the one currently being promoted.
- `ReplicaSet` rows show `ready/desired` and a weight % (canary).
- The `Steps`/`Strategy` panel shows the current step index and whether it's paused and why (e.g. `StepPause`, `AnalysisRunInconclusive`, `BlueGreenPause`).
- `STATUS` column: `Healthy` / `Progressing` / `Paused` / `Degraded` / `Aborted`.

Tree-view icons: `⟳` Rollout · `Σ` Experiment · `α` AnalysisRun · `#` Revision · `⧉` ReplicaSet · `□` Pod · `⊞` Job.

### `get` for other kinds

```bash
kubectl argo rollouts get experiment NAME [-w]
kubectl argo rollouts get analysisrun NAME
```

### `status` — script-friendly (use in CI)

```bash
kubectl argo rollouts status NAME              # blocks until done; exit 0 healthy, non-zero on failure
kubectl argo rollouts status NAME --watch=false
kubectl argo rollouts status NAME --timeout=10m
```

Returns non-zero when the rollout ends `Degraded`/`Aborted`. Use `--timeout` for the overall wait (not `--request-timeout`, which is per HTTP call). This is the canonical CI integration point.

### `list`

```bash
kubectl argo rollouts list rollouts             # all rollouts in namespace
kubectl argo rollouts list rollouts -A          # all namespaces
kubectl argo rollouts list rollouts -o json
kubectl argo rollouts list experiments
```

### `lint`

```bash
kubectl argo rollouts lint rollout.yaml         # validate before applying
```

### `dashboard`

```bash
kubectl argo rollouts dashboard                 # local web UI on http://localhost:3100
```

## Driving an update — the day-2 triad

### `promote` — advance / un-pause

```bash
kubectl argo rollouts promote NAME              # advance past current pause to next step
kubectl argo rollouts promote NAME --full       # SKIP ALL remaining pauses → 100% (force-promote)
kubectl argo rollouts promote NAME --skip-current-step   # advance past current step entirely
```

- Default `promote`: un-pauses (resumes) the current step and continues normally.
- `--full`: jump straight to fully promoted — use when confident.
- Also resumes a manually-`pause`d rollout.
- For blue-green with `autoPromotionEnabled: false`, this flips the active Service to the new ReplicaSet.

### `abort` — kill the in-flight rollout, revert to stable

```bash
kubectl argo rollouts abort NAME
```

- Sets canary weight to 0 (canary ReplicaSet scaled down after `abortScaleDownDelaySeconds`, default 30; `0` keeps it alive).
- For blue-green, flips `activeService` back to the previous ReplicaSet.
- Does **not** change Git. Cluster reverts; manifest still says the new image.
- Rollout shows `Aborted`/`Degraded`. Fix forward in Git, then re-apply.

### `undo` — revert to a prior revision

```bash
kubectl argo rollouts undo NAME                          # previous revision
kubectl argo rollouts undo NAME --to-revision=3     # specific revision
```

- Uses `revisionHistoryLimit` history (default 10 old ReplicaSets kept; `0` disables undo).
- **Fast rollback:** if the old ReplicaSet is still scaled up within `scaleDownDelaySeconds`, the controller instantly flips the Service selector — no re-deploy. See `state-machine.md` for the fast-track vs full distinction.
- For an even faster revert, just `kubectl apply` the previous manifest.

## Lifecycle commands

### `pause` / resume

```bash
kubectl argo rollouts pause NAME        # manual pause (sets spec.paused: true)
```

Resume via `promote` (or `argocd app actions run ... resume` under Argo CD). Manual pause halts step progression but HPA autoscaling continues.

### `retry` — retry after abort or ProgressDeadlineExceeded

```bash
kubectl argo rollouts retry rollout NAME
kubectl argo rollouts retry experiment NAME
```

Use after `abort` or a failed analysis to retry the same revision.

### `restart` — rolling restart of pods

```bash
kubectl argo rollouts restart NAME              # restart all pods (sets spec.restartAt=now)
kubectl argo rollouts restart NAME --restart-at=2025-01-01T00:00:00Z
```

Controller ensures each pod's `creationTimestamp` ≥ `restartAt`. Does not change the image — just cycles pods while honoring the strategy.

### `terminate` — kill an AnalysisRun or Experiment

```bash
kubectl argo rollouts terminate analysisrun NAME
kubectl argo rollouts terminate analysisrun NAME --force
kubectl argo rollouts terminate experiment NAME
```

Useful when an AnalysisRun is stuck (bad provider URL, no end condition).

## Mutation / creation

### `set image` — start a new rollout by changing the image

```bash
kubectl argo rollouts set image ROLLOUT_NAME CONTAINER=IMAGE[:TAG]
kubectl argo rollouts set image my-app my-app=my-app:v2
kubectl argo rollouts set image my-app my-app=my-app:v2 --dry-run   # preview the patch
```

Equivalent to editing `spec.template` — triggers a new rollout.

### `create` — materialize an AnalysisRun/Experiment for testing

```bash
kubectl argo rollouts create analysisrun --from-analysistemplate TEMPLATE [--arg-name=x --arg-value=y]
kubectl argo rollouts create analysisrun --from-clusteranalysistemplate TEMPLATE
kubectl argo rollouts create experiment --from-manifest experiment.yaml
```

Great for dry-running an analysis in isolation before wiring it into a Rollout.

### `notifications`

```bash
kubectl argo rollouts notifications trigger get
kubectl argo rollouts notifications trigger run ROLLOUT TRIGGER
kubectl argo rollouts notifications template get
kubectl argo rollouts notifications template notify SERVICE TEMPLATE
```

See `notifications.md`.

## Equivalent `kubectl patch` (GitOps / CI without the plugin)

Since there's no separate API, "promote" / "resume" / "restart" are just patches — useful in CI where you don't control the toolchain:

```bash
# Resume a manual pause (equivalent to `promote` of a manually-paused rollout)
kubectl patch rollout NAME --type merge -p '{"spec":{"paused":false}}'

# Restart pods (equivalent to `restart`)
kubectl patch rollout NAME --type merge -p '{"spec":{"restartAt":"<RFC3339 UTC>"}}'

# Abort (set the abort flag — controller reverts traffic to stable)
kubectl patch rollout NAME --type merge -p '{"status":{"abort":true}}'  # via subresource if enabled
```

Under Argo CD, prefer `argocd app actions run <APP> resume` and `argocd app actions run <APP> restart` (built-in Lua resource actions) so the action is audited.

## Global flags worth knowing

```
-n, --namespace NS             namespace scope
    --kubeconfig PATH
    --context NAME
    --loglevel info             plugin log level
-v, --kloglevel N               k8s client log level
    --as USER | --as-group G    impersonation (RBAC debugging)
```

## A complete "I just shipped v2" watch session

```bash
# Terminal 1 — trigger and watch
kubectl argo rollouts set image my-app my-app=my-app:v2
kubectl argo rollouts get rollout my-app -w

# If it looks bad:
kubectl argo rollouts abort my-app
kubectl argo rollouts undo my-app          # or fix-forward in Git

# If it looks good mid-canary:
kubectl argo rollouts promote my-app --full
```
