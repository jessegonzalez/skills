# Strategy Decisions & Trade-offs

Use this when a user is **choosing** a strategy, asking about **HPA + canary** interaction, anti-affinity, sticky sessions, or whether Argo Rollouts is even the right tool. Always present at least two options and name what the user gives up.

## Master decision matrix

| | Blue/Green | Basic Canary | Canary + router | Experiment step |
|---|---|---|---|---|
| Adoption complexity | Low | Medium | High | Highest |
| Needs a traffic provider | No | No | Yes | Optional (weighted) |
| Works with queue workers / shared locks | Yes | No | No | No |
| Traffic switch | All-or-nothing | Gradual % | Gradual % | Side-by-side, no live traffic by default |
| Traffic control | 0% or 100% | coarse (pod count) | fine-grained (1%) | parallel comparison |
| Advanced routing (header/mirror) | No | No | Yes | No |
| Failure blast radius | Massive (if cutover breaks) | Low | Low | Lowest (no prod traffic by default) |

Heuristic from upstream: **start with blue-green, graduate to canary once your metrics and traffic router are trustworthy.** Canaries require the app to be stateless and share-nothing across versions.

## When NOT to use Argo Rollouts

Push back (don't force-fit) when:

- **The app can't run two versions concurrently.** DB-migrating services, single-writer queues, apps with shared file locks, single-tenant schema-with-breaking-migrations. Blue-green still works (only one version active) but canary won't.
- **It's "infrastructure."** Upstream explicitly does **not** recommend Rollouts for cert-manager, nginx-ingress, coredns, sealed-secrets, etc. — use plain Deployments.
- **Long-lived parallel releases.** Rollouts assumes *one stable + one preview*. Running 1.3 stable with 1.4 preview for a week, then deploying 1.5, has ambiguous semantics (the project treats 1.5 as a hotfix of 1.4; rollback target stays 1.3). Keep rollouts short (minutes to ~2h max).
- **Multi-cluster / multi-app orchestrated rollouts.** Rollouts is single-cluster, single-application, and knows nothing about cross-service dependencies. "Roll back frontend when backend fails" requires orchestration on top.
- **Preview/ephemeral environments.** That's Argo CD ApplicationSet PR generators, not Rollouts.
- **No metrics and no intent to build any.** The endgame is *automated* promotion/rollback. If a human will stare at dashboards for 2h after each deploy, Rollouts adds ceremony without value.

## Blue-green specifics

Key fields under `spec.strategy.blueGreen` (full reference: `blue-green.md`):

- `activeService` *(required)* — Service receiving prod traffic; controller swaps its selector to the new RS at cutover.
- `previewService` *(optional)* — points at the new RS before cutover; lets you smoke-test the green stack via a separate DNS/URL.
- `previewReplicaCount` *(optional)* — pin the preview RS to fewer pods (cost control with HPA — only stable RS autoscales).
- `autoPromotionEnabled` *(default true)* — `false` → manual promote required (the common "pause before cutover" pattern).
- `autoPromotionSeconds` — auto-promote after N seconds of readiness.
- `scaleDownDelaySeconds` *(default 30, keep ≥ 30)* — wait before scaling old RS down (iptables/mesh propagation; also the fast-track rollback window).
- `prePromotionAnalysis` / `postPromotionAnalysis` — gates. Post-promotion failure reverts traffic to the prior stable RS.

Cutover is an atomic Service selector swap. There is **no** gradual traffic shift in blue-green; use canary if you need that.

## Canary specifics

Key fields under `spec.strategy.canary` (full reference: `canary.md`):

- `maxSurge` / `maxUnavailable` — same semantics as Deployment. **Constraint: not both 0.** `maxUnavailable: 0` + `maxSurge: 1` = no capacity loss during rollout (safe default). Defaults are `25%` each.
- `steps` — ordered list (semantics: `state-machine.md`).
- `canaryService` / `stableService` — required for `trafficRouting`; controller owns their selectors.
- `trafficRouting` — the router block (`traffic-routing.md`).
- `analysis` — background analysis (`analysis.md`).
- `scaleDownDelaySeconds` *(default 30, router only)* — delay before scaling stable RS down after promotion.
- `abortScaleDownDelaySeconds` *(default 30, 0 = keep, router only)* — delay before scaling canary RS down on abort.
- `dynamicStableScale` *(default false, router only)* — shrink stable RS as canary grows; trades away the "stable can always serve 100%" guarantee.
- `setCanaryScale` (step) — pin canary replicas independent of traffic (the HPA-isolation knob).
- `minPodsPerReplicaSet` *(default 1, router only)* — HA floor for each RS at tiny weights.
- `pingPong` — zero-downtime for long-lived TCP/gRPC.
- `antiAffinity` — see below.

## HPA + canary — the deep gotcha

A single HPA targets the Rollout and sees **both** RSes' pods under one selector — it computes one average metric and scales `spec.replicas`. The controller then distributes those replicas across canary/stable per the current weight.

- **Without a router:** canary gets `⌈total × W/100⌉` pods; stable gets the rest. Works but coarse.
- **With a router, single HPA (default):** a canary with a memory leak or CPU spike raises the *combined* average → HPA scales **both** versions up. The canary's pathology drags the stable fleet with it. **This is the #1 canary+HPA footgun.**
- **Mitigation — `setCanaryScale`:** pin the canary RS to a fixed replica count per step; HPA scaling then only flows to stable. Traffic weight is still exact (router), so e.g. `setWeight: 80` + `setCanaryScale.replicas: 1` sends 80% of traffic to one canary pod.
- **Mitigation — `dynamicStableScale: true`:** shrink stable as canary grows (lower total footprint), at the cost of the guarantee that stable can absorb 100% instantly on rollback.
- **Mitigation — separate HPAs per RS:** not natively supported by a single Rollout. Practically, `setCanaryScale` is the supported isolation knob.

Blue-green + HPA: by default both active and preview RSes scale together (2× cost during rollout). `previewReplicaCount` pins the preview so only stable autoscales.

## Anti-affinity (`spec.strategy.<canary|blueGreen>.antiAffinity`)

`preferredDuringSchedulingIgnoredDuringExecution` (soft, with `weight` 1–100) or `requiredDuringSchedulingIgnoredDuringExecution` (hard). Spreads canary/stable (or active/preview) pods across nodes/zones so a node failure doesn't take out one whole version. Use soft in multi-AZ clusters where hard anti-affinity can't be satisfied; use hard when correctness demands it and you have enough nodes.

## Sticky sessions & session draining gotchas

- **Sticky sessions break canaries.** A cookie-pinned client stays on stable and never sees the canary, so canary traffic % is skew and metrics are biased. Prefer header-based routing (`setHeaderRoute`) for opt-in canary exposure of known clients.
- **No native session draining.** Rollouts doesn't wait for in-flight requests on the old RS before scale-down. Mitigations: keep `scaleDownDelaySeconds` ≥ your longest request + mesh propagation; use `preStop` + `terminationGracePeriodSeconds` on the pod; or adopt `pingPong` for long-lived gRPC/TCP where selector swaps drop connections.
- **Long-lived connections (WebSocket, gRPC streams):** a Service selector swap cuts them. `pingPong` exists precisely for this — it alternates which persistent service is "stable" without a selector flip.

## Application-compatibility checklist before adopting canary

Confirm with the app owners:

1. Can two versions serve traffic concurrently (schema compat, API bw/fw compat)?
2. Are caches/state shared in a way that breaks under split traffic?
3. Do you have a metric that resolves success/failure in 5–15 min? (Dry-run it first.)
4. Is there a traffic router in the cluster (or is blue-green/basic canary acceptable)?
5. For workers/queue consumers: canary is usually a no-go without source changes.
