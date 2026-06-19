# Traffic Routing

Without a traffic router, a canary approximates its weight by the **ratio of replica counts** (kube-proxy). With a router, Argo Rollouts achieves true percentage-based splitting (down to 1%), plus header/mirror routing and dynamic scaling.

> Field path: `spec.strategy.canary.trafficRouting`. **Requires** `canaryService` and `stableService` (exceptions: Istio subset-level splitting and `pingPong`).
> For HPA/scale interaction, see `strategy-decisions.md`. For full step semantics, see `canary.md` and `state-machine.md`.

## What changes when you add `trafficRouting`

1. **Traffic split becomes exact and independent of pod counts.** `setWeight: 20` means precisely 20% of requests, regardless of how many canary pods exist — because the router (mesh/ingress) enforces it.
2. **The stable ReplicaSet stays fully scaled up** through the rollout so it can absorb 100% instantly on rollback.

Without a router, `scaleDownDelaySeconds`, `abortScaleDownDelaySeconds`, `dynamicStableScale`, `setCanaryScale`, `minPodsPerReplicaSet`, `setHeaderRoute`, `setMirrorRoute`, and `pingPong` are **all no-ops / ignored**.

## The non-negotiable preconditions

```yaml
strategy:
  canary:
    canaryService: gb-canary      # MUST pre-exist; controller owns its selector
    stableService: gb-stable      # MUST pre-exist; controller owns its selector
    trafficRouting: { ... }       # the router block
```

- Both Services must already exist in the namespace before the Rollout references them.
- The controller patches these Services' selectors onto `rollouts-pod-template-hash` values — **never hand-edit their selectors** (it'll fight you, or break on the next reconcile).
- The controller adds an `argo-rollouts.argoproj.io/managed-by-rollouts` annotation to Services/Ingresses it owns; if the Rollout is deleted, it tries to revert them to their pre-rollout state.

## Provider matrix

`spec.strategy.canary.trafficRouting` accepts one primary provider block (plus optional mixed secondaries). Core providers (no new ones accepted in core — extensions are **plugins**, including Gateway API):

| Provider | Key | Backend resource it rewrites | Notable features |
|----------|-----|------------------------------|------------------|
| **Istio** | `istio` | `VirtualService` route weights / destinations | Richest: header & mirror routes, multiple vsvcs, ping-pong, subset-level. |
| **NGINX Ingress** | `nginx` | canary `Ingress` w/ `nginx.ingress.kubernetes.io/canary-weight` annotation | `stableIngress` or `stableIngresses[]`; `annotationPrefix`; `maxTrafficWeight` ≠ 100; extra canary annotations. |
| **AWS ALB** | `alb` | weighted target groups on one ALB listener (via `Ingress` annotations) | Needs `ingress`, `servicePort`, and `rootService` (required for ping-pong). |
| **SMI** | `smi` | `TrafficSplit` resource | Provider-agnostic (Linkerd etc.); optional `rootService`, `trafficSplitName`. |
| **Ambassador / Apache APISIX / Traefik / Kong / Google Cloud** | plugin or named | Ambassador `Mapping`, `ApisixRoute`, `TraefikService`, etc. | Traefik requires `weightedTraefikServiceName`. |
| **Gateway API / custom** | plugin | any Gateway API implementation | The only path for new providers. |

## What the controller mutates

- **Host-level (NGINX/ALB/SMI/Istio-host):** the canary & stable `Service.spec.selector` get the current `rollouts-pod-template-hash` injected; the mesh/ingress object's weights are updated.
- **Istio subset-level:** the `DestinationRule.subsets[].labels` get the hash; the `VirtualService.http[].route[].weight` is updated. The Service is *not* modified.

## Istio — host-level (two services)

You deploy: Rollout, `stable-svc`, `canary-svc`, and a `VirtualService` whose route destinations match those service names.

```yaml
strategy:
  canary:
    canaryService: canary-svc
    stableService: stable-svc
    trafficRouting:
      istio:
        virtualService:
          name: rollout-vsvc          # required
          routes: [primary]           # required if the VS has multiple HTTP routes; optional otherwise
```

```yaml
# VirtualService — start 100/0; Argo Rollouts rewrites the weights in place
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata: { name: rollout-vsvc }
spec:
  gateways: [istio-rollout-gateway]
  hosts: [istio-rollout.dev.argoproj.io]
  http:
    - name: primary                   # matches trafficRouting.istio.virtualService.routes
      route:
        - destination: { host: stable-svc }
          weight: 100
        - destination: { host: canary-svc }
          weight: 0
```

Cross-namespace destinations: use `<svc>.<namespace>` as the host. Multiple VirtualServices: use `virtualServices: [{ name, routes }]` instead of `virtualService`.

## Istio — subset-level (one service + DestinationRule, v1.0+)

Better for east-west / intra-cluster canaries (avoids forcing callers to pick a DNS name).

```yaml
trafficRouting:
  istio:
    virtualService:
      name: rollout-vsvc
      routes: [primary]
    destinationRule:
      name: rollout-destrule         # required
      canarySubsetName: canary       # required
      stableSubsetName: stable       # required
      additionalSubsetNames: [experiment]   # optional; Argo subtracts their fixed weight from stable
```

Istio TCP routing (v1.2.2+): `virtualService.tcpRoutes: [{ port: 3000 }]` (port optional, must match a match rule).

## NGINX

You provide a primary Ingress routing to `stableService`. Argo Rollouts creates a *canary Ingress* with `nginx.ingress.kubernetes.io/canary: "true"` and `canary-weight: <n>`.

```yaml
trafficRouting:
  nginx:
    stableIngress: primary-ingress          # OR stableIngresses: [...] for multi-ingress (v1.5+)
    annotationPrefix: nginx.ingress.kubernetes.io   # optional override
    additionalIngressAnnotations:           # optional extra canary annotations
      canary-by-header: X-Canary
      canary-by-header-value: iwantsit
    canaryIngressAnnotations:               # optional full annotation keys (no prefix injection)
      mygroup.com/key: value
```

The controller only touches Ingresses whose `kubernetes.io/ingress.class` or `spec.ingressClassName` is `nginx`. Match a different class via the controller flag `--nginx-ingress-classes` (repeatable; `''` matches any).

## AWS ALB

```yaml
trafficRouting:
  alb:
    ingress: gb-ingress            # required — the ALB-managed Ingress
    servicePort: 443               # required — must match the Service the ALB targets
    annotationPrefix: alb.ingress.kubernetes.io   # optional
    rootService: gb-root           # required when pingPong is enabled
```

ALB adds weighted forwarding rules to a single listener. **Blue-green + ALB can cause brief downtime** because the ALB controller deregisters pods before registering new ones — prefer canary + ALB or `pingPong`.

## SMI

```yaml
trafficRouting:
  smi:
    rootService: root-svc                    # optional
    trafficSplitName: rollout-example-traffic-split  # optional
```

SMI weighted traffic is available for the **weighted Experiment step** (alongside ALB and Istio).

## Header & mirror routes (Istio / Gateway API plugin)

These require listing the route name in `trafficRouting.managedRoutes`. **Order in that list = route precedence** — Rollouts places them above any manually-defined routes. All managed routes are removed at end-of-rollout or on abort (never list manually-created routes there).

```yaml
strategy:
  canary:
    trafficRouting:
      istio:
        virtualService: { name: rollout-vsvc, routes: [primary] }
        managedRoutes:
          - name: set-header
          - name: mirror-route
    steps:
      - setWeight: 20
      - setHeaderRoute:                 # send matching requests fully to canary
          name: set-header
          match:
            - headerName: version
              headerValue: { exact: "2" }   # or prefix / regex (not all routers support all)
      - setMirrorRoute:                 # copy matching traffic to canary (response discarded)
          name: mirror-route
          percentage: 35
          match:
            - method: { exact: GET }
              path: { prefix: / }
      - pause: { duration: 10m }
      - setHeaderRoute: { name: set-header }   # no match => REMOVES the route
      - setMirrorRoute:  { name: mirror-route }
```

Match semantics: within one `match` block conditions are AND; across `match` blocks they're OR; each matcher takes exactly one of `exact`/`regex`/`prefix`. Header routing is the basis for **cookie-free opt-in canaries** ("internal testers opt in via a header"), avoiding sticky-session skew.

## Ping-Pong — zero-downtime for long-lived connections (v1.7+)

A Service selector swap drops in-flight long-lived connections (WebSocket, gRPC streams). Ping-pong instead uses **two persistent Services** and alternates which is "stable" (tracked in `status.canary.stablePingPong`). Promotion = flip the stable designation, no selector change on live pods. Supported with ALB, Istio, and plugin-based routers. When `pingPong` is set, `canaryService`/`stableService` are **not** required.

```yaml
strategy:
  canary:
    pingPong:
      pingService: gb-ping
      pongService: gb-pong
    trafficRouting:
      alb: { ingress: gb-ingress, servicePort: 443, rootService: gb-root }
```

## `maxTrafficWeight`

Default is 100. Set higher (e.g. 1000) when your platform's denominator is different — `setWeight` values are then interpreted as fractions of `maxTrafficWeight`.

## Mixed providers

You can use more than one router at once — e.g. SMI in the mesh + NGINX at the edge, or Istio + ALB. Each provider block under `trafficRouting` is reconciled independently. This matters for topologies where traffic crosses both a mesh and an ingress controller.

## `scaleDownDelaySeconds` — why it exists (router canaries)

After promotion, the controller switches the **stable Service selector** to the new RS. But the mesh/ingress still has rules pointing at pods behind the old selector, and propagation isn't instant. `scaleDownDelaySeconds` (default 30) keeps the old RS alive long enough for routers to re-target. Setting it too low causes brief 5xx/no-route windows after promotion. (Ignored for basic no-router canaries, where pod-count *is* the traffic signal.)

## GitOps reconciliation (Istio weights flap)

A Rollout rewrites VirtualService weights during an update → your Git copy drifts → an `apply`/auto-sync reverts them → Argo Rollouts snaps them back. Avoid the flap with Argo CD `ignoreDifferences`:

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

Full GitOps discussion: `gitops-argocd.md`.

## Mental model for "traffic didn't shift"

When a user reports the canary isn't getting traffic, check in order:

1. Is `trafficRouting` actually set? (If not, traffic follows pod count — look at replica ratios instead.)
2. Do `canaryService`/`stableService` exist and have selectors on the right `rollouts-pod-template-hash`?
3. Did the router CR actually get rewritten? (`kubectl describe virtualservice` / the ingress / `kubectl get trafficsplit` — look for the weight).
4. Is the rollout actually *at* a step where weight is set, or still `Progressing` to the canary RS being ready?
5. For mesh routers: is the workload enrolled in the mesh / has the right sidecar / correct host headers?

Full diagnostic runbook: `troubleshooting.md`.

## Common routing mistakes

- **`trafficRouting` set but `canaryService`/`stableService` missing** (host-level) → controller can't wire it up; traffic never shifts.
- **VirtualService route destinations don't match the service names** → "traffic isn't moving". Names are exact, including cross-namespace `<svc>.<ns>`.
- **`routes:` omitted when the VirtualService has multiple HTTP routes** → ambiguous; the controller can't pick.
- **Forgetting `managedRoutes:`** for header/mirror steps → the route is never created.
- **Class mismatch (NGINX)** → Ingress isn't reconciled because its class doesn't match `--nginx-ingress-classes`.
- **Hand-editing `canaryService`/`stableService` selectors** → the controller overwrites on the next reconcile.
- **GitOps auto-sync reverting weights** → configure `ignoreDifferences` (above).
