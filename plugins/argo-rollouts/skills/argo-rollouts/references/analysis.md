# Analysis (Metric-Based Promotion Gates)

Analysis turns "shift traffic" into "shift traffic *only if the new version is healthy*." Three CRDs back it:

- **`AnalysisTemplate`** — namespace-scoped, parameterized recipe ("how to measure").
- **`ClusterAnalysisTemplate`** — cluster-scoped, shareable across namespaces (reference with `clusterScope: true`).
- **`AnalysisRun`** — an instantiation the controller creates per rollout/experiment, with terminal phases like a `Job`.

An `AnalysisRun` is to an `AnalysisTemplate` what a `Pod` is to a `PodTemplate`. For where to attach analysis to a rollout, see `state-machine.md`; for inline/background/pre-promotion mechanics, see below.

> Field version: `argoproj.io/v1alpha1`. For step ordering, see `canary.md`; for blue-green gates, see `blue-green.md`.

## The four integration points

| Point | Field | Blocks? | Use when |
|-------|-------|---------|----------|
| **Background** | `spec.strategy.canary.analysis` | No | Continuous SLO guardrail; abort on regression. Use `startingStep: N` (0-indexed) to delay creation until step N (i.e. until enough canary traffic exists to produce signal). |
| **Inline step** | `steps: [{ analysis: { ... } }]` | Yes | Point-in-time gate: "after 20%, run smoke tests, then continue." |
| **BlueGreen pre-promotion** | `blueGreen.prePromotionAnalysis` | Yes — blocks cutover | Validate preview stack *before* any prod traffic. |
| **BlueGreen post-promotion** | `blueGreen.postPromotionAnalysis` | Yes — failure reverts | Validate *after* cutover; on failure flips active service back. |

## AnalysisRun phases (and what each does to the rollout)

| Phase | Trigger | Effect on Rollout |
|-------|---------|-------------------|
| `Successful` | `successCondition` met (or `count` exhausted with success prevailing) | Advance / promote. |
| `Failed` | `failureCondition` true past `failureLimit`, or `successCondition` false with no failure cond | **Abort** the rollout (canary→0; blue-green post-promo → revert). |
| `Inconclusive` | Terminal but neither success nor failure (e.g. value between thresholds) | **Pause** the rollout for human judgement. |
| `Error` | Controller couldn't take a measurement (bad URL, expr parse error, provider down) | Counts toward `consecutiveErrorLimit`; if exhausted, typically `Inconclusive`/pause. |
| `Running` | In progress | Step blocks (inline); background continues. |

## A metric's anatomy

```yaml
metrics:
  - name: success-rate
    interval: 5m           # sampling interval. Omit → single measurement.
    count: 5               # number of measurements; omit → run until rollout ends (background); 0 in a step → never runs
    initialDelay: 5m       # wait before first measurement (let metrics populate)
    successCondition: result[0] >= 0.95     # expr-lang over `result`
    failureCondition: result[0] < 0.50      # optional; if absent, "not success" → fail
    failureLimit: 3                       # tolerate N failures (default 0 = no tolerance; -1 disables)
    consecutiveSuccessLimit: 4            # need N consecutive successes (default 0 = disabled)
    consecutiveErrorLimit: 3              # tolerate N provider errors (default 4)
    dryRun: false           # collect without gating
    provider:
      prometheus:
        address: http://prometheus:9090
        query: |
          sum(rate(...)) / sum(rate(...))
```

### `failureLimit` vs `consecutiveSuccessLimit` — one must apply

- `failureLimit` applicable when ≥ 0 (default 0 = no failures tolerated). Set `-1` to disable.
- `consecutiveSuccessLimit` applicable when > 0 (default 0 = disabled).
- **Validation error if neither is applicable.** Typical patterns:
  - Default behavior (tolerate zero failures): leave both unset.
  - "Wait for N good in a row" (event-driven promotion): `failureLimit: -1`, `consecutiveSuccessLimit: 4`.
  - "Need N good, allow M bad total": `failureLimit: 3`, `consecutiveSuccessLimit: 4` → `failureLimit` takes priority if violated.
- On premature termination (background analysis ending with rollout, or step analysis with `count` unreached on abort): always terminated `Successful` **unless** `failureLimit` is currently violated → `Failed`. `consecutiveSuccessLimit` doesn't affect termination status.

**The #1 "stuck analysis" cause:** a background/inline metric with no `count`, no `consecutiveSuccessLimit`, and `failureLimit: 0` that never trips → runs forever. Always give the metric a terminal path. (Background analysis that intentionally runs until rollout ends is the exception — it's only "stuck" if the rollout itself is.)

## Conditions language (`successCondition` / `failureCondition`)

Both use [expr-lang](https://github.com/expr-lang/expr) over `result`. Prometheus returns a vector → index with `result[0]`. Helpers for pathological values:

```yaml
# Empty Prometheus vector — tolerate no-data
successCondition: len(result) == 0 || result[0] >= 0.95

# Fail when +Inf
failureCondition: isInf(result)

# Handle NaN explicitly
successCondition: isNaN(result) || result[0] >= 0.95

# Datadog nil (no-data) — use default()
successCondition: default(result, 0) < 0.05
```

Forgetting these is the most common cause of an AnalysisRun stuck in `Error` with a confusing message.

## Args, secrets, and dynamic values

Args are resolved **at AnalysisRun creation time**, not continuously. Placeholder syntax: `{{ args.<name> }}`.

```yaml
spec:
  args:
    - name: service-name                          # required (no default)
    - name: prometheus-port
      value: 9090                                 # default (optional in caller)
    - name: api-token
      valueFrom:
        secretKeyRef: { name: token-secret, key: apiToken }  # injected from Secret
```

Caller-supplied args (in the Rollout) override defaults and fill requireds. Powerful `valueFrom` sources in the Rollout's `args`:

- `podTemplateHashValue: Stable | Latest` — inject the `rollouts-pod-template-hash` so the metric query can filter on the exact RS. **Canonical pattern for per-version success-rate queries** — without it, the query blends stable+canary and the gate becomes meaningless.
- `fieldRef.fieldPath` — read any Rollout metadata/status/pod-template field, e.g. `metadata.labels['region']`, `status.alb.canaryTargetGroup.name`, `spec.template.metadata.labels.version`.

Secrets: an `AnalysisRun` can only read Secrets in **its own namespace** (= the Rollout's namespace). The `AnalysisTemplate` declares the ref; the run resolves it.

## Dry-run and measurement retention

- **`dryRun: [{ metricName: <name|regex> }]`** — the metric is queried and recorded, but its result **does not** affect the outcome. Use to validate a new metric in prod before letting it gate. `.*` matches all. A "Dry Run Summary" is appended to the run's message.
- **`measurementRetention: [{ metricName: <name|regex>, limit: N }]`** — keep the last N measurements (default 10).
- Both can be set on the `AnalysisTemplate`, or overridden per-`analysis` stanza in a Rollout step / Experiment.

## TTL & history limits

- `ttlStrategy` (AnalysisRun spec, v1.7+): `secondsAfterCompletion` / `secondsAfterSuccess` / `secondsAfterFailure`.
- Rollout-level: `spec.analysis.successfulRunHistoryLimit` and `unsuccessfulRunHistoryLimit` (default 5 each) bound how many completed runs the controller retains.

## Multiple templates & composition

A Rollout or AnalysisTemplate can reference several templates; the controller **merges** their `metrics` + `args` into one AnalysisRun.

- Two metrics with the same name across templates → **error**.
- Two args with the same name but different defaults → **error**.
- Same template referenced multiple times in a chain → kept once (cycles de-duped).

```yaml
analysis:
  templates:
    - templateName: success-rate
    - templateName: latency
    - templateName: error-budget
      clusterScope: true              # ClusterAnalysisTemplate
```

## Metric providers

Core-maintained (no new providers accepted in core — new integrations are **plugins**):

| Provider | `provider.<key>` | Notes |
|---|---|---|
| Prometheus | `prometheus: { address, query }` | Vector result; index `[0]` |
| Datadog | `datadog: { apiVersion, query, ... }` | Use `default()` for no-data |
| New Relic | `newRelic: { ... }` | NRQL |
| Wavefront | `wavefront: { ... }` | |
| Graphite | `graphite: { address, query }` | |
| InfluxDB | `influxdb: { ... }` | |
| CloudWatch | `cloudWatch: { ... }` | |
| Kayenta | `kayenta: { ... }` | Automated Canary Analysis |
| Job | `job: { spec }` | A Kubernetes Job; success = pod exit 0 (great for custom smoke tests) |
| Web | `web: { url, headers?, method?, jsonPath?, timeout? }` | HTTP call; `jsonPath` extracts the value |

The **Job** and **Web** providers are escape hatches when no metrics backend fits — e.g. "run my pytest container, abort if it fails" or "call my existing health endpoint".

## ClusterAnalysisTemplate — when to use

When the same recipe (e.g. "HTTP 5xx rate < 1%") should be shared by many Rollouts across namespaces without duplication. Reference with `clusterScope: true`. The resulting **AnalysisRun always runs in the Rollout's namespace** (so Secret refs and RBAC stay local).

## Testing an AnalysisTemplate in isolation

Don't wait for a rollout to test your query. Materialize a one-off AnalysisRun:

```bash
kubectl argo rollouts create analysisrun \
  --from-analysistemplate success-rate \
  --arg-name service-name --arg-value my-app.default.svc.cluster.local
# or for a ClusterAnalysisTemplate:
kubectl argo rollouts create analysisrun --from-clusteranalysistemplate success-rate ...
```

Watch: `kubectl get analysisrun -w`. Terminate if stuck: `kubectl argo rollouts terminate analysisrun NAME`.

## Composition example (background, delayed, parameterized)

```yaml
# Rollout excerpt
strategy:
  canary:
    canaryService: gb-canary
    stableService: gb-stable
    trafficRouting: { istio: { virtualService: { name: gb-vsvc } } }
    analysis:
      startingStep: 2                      # don't query until setWeight 40% (step index 2)
      templates:
        - templateName: success-rate
      args:
        - name: service-name
          value: gb-svc.default.svc.cluster.local
        - name: latest-hash
          valueFrom: { podTemplateHashValue: Latest }
    steps:
      - setWeight: 20
      - pause: { duration: 10m }
      - setWeight: 40                      # analysis starts here
      - pause: { duration: 10m }
```

```yaml
# AnalysisTemplate excerpt — note version-specific query via pod-template-hash
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata: { name: success-rate }
spec:
  args:
    - name: service-name
    - name: latest-hash
  metrics:
    - name: success-rate
      interval: 5m
      successCondition: result[0] >= 0.95
      failureLimit: 3
      provider:
        prometheus:
          address: http://prometheus.observability:9090
          query: |
            sum(rate(requests_total{pod_template_hash="{{args.latest-hash}}",code!~"5.."}[5m]))
            /
            sum(rate(requests_total{pod_template_hash="{{args.latest-hash}}"}[5m]))
```
