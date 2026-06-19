# Blue-Green Strategy

Blue-green (a.k.a. red-black) runs the new version to completion alongside the old one, then switches a Service selector to cut all traffic over at once. Only one version receives production traffic at any time.

> Field path: `spec.strategy.blueGreen` (kind `Rollout`, `apiVersion: argoproj.io/v1alpha1`).
> The YAML key is **`blueGreen`** (camelCase) — not `bluegreen` or `blue-green`.
> For trade-offs vs canary, see `strategy-decisions.md`. For analysis gates, see `analysis.md`.

## How the traffic switch works

The controller maintains a unique `rollouts-pod-template-hash` label per ReplicaSet. At promotion it **injects that hash into the `activeService`'s `spec.selector`**, so the Service instantly points at the new pods. Because kube-proxy updates iptables asynchronously across nodes, you must wait before killing the old ReplicaSet — hence `scaleDownDelaySeconds` (default 30, keep ≥ 30).

The `previewService` is repointed to the newest ReplicaSet *before* promotion, giving you a private endpoint to test the candidate version.

## Sequence of events during an update

1. Steady state: revision 1 ReplicaSet is referenced by both `activeService` and `previewService`.
2. User changes `spec.template` → revision 2 ReplicaSet is created at size 0.
3. `previewService` is repointed to revision 2; `activeService` stays on revision 1.
4. Revision 2 scales to `spec.replicas` (or `previewReplicaCount` if set).
5. Once revision 2 pods are fully available, `prePromotionAnalysis` runs (if configured).
6. On success, the rollout **pauses** if `autoPromotionEnabled: false` or `autoPromotionSeconds` is set.
7. Resumed (manually, or after `autoPromotionSeconds`).
8. If `previewReplicaCount` was used, revision 2 scales up to `spec.replicas`.
9. **Promotion**: `activeService` is repointed to revision 2.
10. `postPromotionAnalysis` runs (if configured). On failure → abort, traffic returns to revision 1.
11. On success, revision 2 becomes "stable".
12. After `scaleDownDelaySeconds`, revision 1 is scaled down.

## Minimal example

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata: { name: rollout-bluegreen }
spec:
  replicas: 2
  revisionHistoryLimit: 2
  selector: { matchLabels: { app: rollout-bluegreen } }
  template:
    metadata: { labels: { app: rollout-bluegreen } }
    spec:
      containers:
        - name: rollouts-demo
          image: argoproj/rollouts-demo:blue
          ports: [{ containerPort: 8080 }]
  strategy:
    blueGreen:
      activeService: rollout-bluegreen-active   # REQUIRED
      previewService: rollout-bluegreen-preview # optional
      autoPromotionEnabled: false               # default true
```

The two Services are plain Kubernetes `Service` objects you create yourself; the controller mutates their selectors. They must select the same base labels as `spec.selector` (e.g. `app: rollout-bluegreen`). The controller does not create them.

## Manual-gate + pre/post-promotion analysis

The most defensible blue-green pattern: gate before cutover on the preview stack, gate after cutover on prod traffic, and require a human to flip the switch.

```yaml
strategy:
  blueGreen:
    activeService: my-app-active
    previewService: my-app-preview
    autoPromotionEnabled: false           # human promote
    scaleDownDelaySeconds: 600            # keep old RS up during post-promo analysis
    prePromotionAnalysis:                 # gate on PREVIEW before cutover
      templates:
        - templateName: smoke-tests
      args:
        - name: service-name
          value: my-app-preview.default.svc.cluster.local
    postPromotionAnalysis:                # gate on ACTIVE after cutover; failure reverts
      templates:
        - templateName: success-rate
      args:
        - name: service-name
          value: my-app-active.default.svc.cluster.local
```

`scaleDownDelaySeconds` must be long enough for post-promotion analysis to finish — the controller cancels AnalysisRuns at scale-down time. If omitted, the controller waits for analysis (min 30s). Don't set `revisionHistoryLimit: 0` if you rely on this safety net.

## Cost-optimized blue-green with HPA

Without pinning, blue + green scale in unison (2× cost during deploys). `previewReplicaCount` keeps the preview small; only stable autoscales. After promotion, the preview becomes the new stable and HPA resumes managing its full scale.

```yaml
strategy:
  blueGreen:
    activeService: my-app-active
    previewService: my-app-preview
    previewReplicaCount: 1               # pin preview; HPA manages stable only
    autoPromotionEnabled: false
```

## Full field reference

```yaml
strategy:
  blueGreen:
    activeService: string                # REQUIRED — service switched at promotion
    previewService: string               # optional — points at newest RS before promotion
    autoPromotionEnabled: true           # default true; false => pause before cutover
    autoPromotionSeconds: 30             # auto-promote after N seconds paused
    previewReplicaCount: 1               # run preview at reduced scale; scales up on promote
    scaleDownDelaySeconds: 30            # default 30; keep >=30 for iptables propagation
    scaleDownDelayRevisionLimit: 2       # cap old RSs kept scaled-up during the delay
    abortScaleDownDelaySeconds: 30       # preview-RS teardown delay on abort (default 30; 0 = keep)
    maxUnavailable: 0                    # default 0 for blue-green
    antiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution: { weight: 1 }
      # OR requiredDuringSchedulingIgnoredDuringExecution: {}
    prePromotionAnalysis: { templates: [...], args: [...] }   # see analysis.md
    postPromotionAnalysis: { templates: [...], args: [...] }  # failure => abort back
    activeMetadata: { labels: {}, annotations: {} }   # stamped onto active pods
    previewMetadata: { labels: {}, annotations: {} }  # stamped onto preview pods only
```

## When to use which knobs

- **`autoPromotionEnabled: false`** — a human (or external system) runs `kubectl argo rollouts promote` after eyeballing the preview stack.
- **`autoPromotionSeconds`** — timed promotion ("give me 30 min of preview, then cut over"). Ignored if `autoPromotionEnabled: false`.
- **`previewReplicaCount`** — save resources during preview (e.g. run 1 replica for testing, scale to full on promote). The controller will not switch the active service until preview matches `spec.replicas`.
- **`prePromotionAnalysis`** — gate the cutover on metrics from the *preview* Service (smoke tests, synthetic checks). Failure aborts before any prod traffic moves.
- **`postPromotionAnalysis`** — gate *after* cutover on real prod metrics. Failure aborts and rolls traffic back to the previous stable ReplicaSet.
- **`activeMetadata` / `previewMetadata`** — merge ephemeral labels/annotations into respective pods; use with the downward API so the app can self-detect "am I the preview?"

## `pingPong` (zero-downtime for long-lived connections)

A Service selector swap drops in-flight WebSocket/gRPC streams. With `pingPong`, the rollout alternates which of two persistent services (`pingService`/`pongService`) is "stable" instead of flipping selectors, tracked in `status.canary.stablePingPong`. This is the **ALB-recommended** alternative to plain blue-green, where the ALB controller's deregister-before-register behavior would otherwise cause brief downtime. Supported with ALB, Istio, and plugin routers. When `pingPong` is set, `canaryService`/`stableService` are not required. Full mechanics: `traffic-routing.md`.

## Gotchas

- **AWS ALB + blue-green is risky.** The ALB ingress controller deregisters pods before registering new ones, which can briefly leave the target group with zero healthy pods → downtime the Rollouts controller cannot prevent. Use canary + ALB or `pingPong` instead for ALB-fronted services.
- **`scaleDownDelaySeconds < 30` can drop traffic** during the iptables propagation window. Don't.
- **The Services must exist and match the rollout selector.** The controller does not create them.
- **`postPromotionAnalysis` failure auto-aborts** — make sure the previous stable RS isn't gone (don't set `revisionHistoryLimit: 0` if you rely on this safety net).
- Blue-green is the **simplest** strategy and the only one that safely handles apps that can't run two versions at once (queue workers, single-writer DBs, file-lock apps) — because only one version is ever *live* at a time.
