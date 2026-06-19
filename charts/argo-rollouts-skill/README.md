# argo-rollouts-skill

A companion **workload** Helm chart to the
[argo-rollouts skill](../../argo-rollouts/SKILL.md). It renders an Argo Rollouts
`Rollout` (canary or blue-green) with optional Istio traffic routing and a
Prometheus `AnalysisTemplate` gate — using the same field paths the skill
documents (`argoproj.io/v1alpha1`).

> This chart deploys a **Rollout workload**, not the Argo Rollouts controller.
> Install the controller separately (e.g. via the official chart) before use.

## Install

```bash
# Minimal canary (pod-ratio, no mesh)
helm install my-app ./charts/argo-rollouts-skill

# Canary with Istio traffic routing + a Prometheus gate
helm install my-app ./charts/argo-rollouts-skill -f - <<EOF
strategy: canary
canary:
  trafficRouting:
    enabled: true
    config:
      istio:
        virtualService:
          name: my-app-vsvc
          routes: [primary]
analysis:
  enabled: true
  startingStep: 2
  provider:
    prometheus:
      address: http://prometheus:9090
      query: |
        sum(rate(http_requests_total{status!~"5.."}[5m]))
        / sum(rate(http_requests_total[5m]))
EOF

# Blue-green with a manual gate
helm install my-app ./charts/argo-rollouts-skill \
  --set strategy=bluegreen --set image.repository=api --set image.tag=v2
```

## Verify locally without a cluster

```bash
helm lint ./charts/argo-rollouts-skill
helm template my-app ./charts/argo-rollouts-skill                      # minimal
helm template my-app ./charts/argo-rollouts-skill --set strategy=bluegreen
helm template my-app ./charts/argo-rollouts-skill --set canary.trafficRouting.enabled=true \
     --set 'canary.trafficRouting.config.istio.virtualService.name=my-vsvc'
```

## Values

| Key | Default | Description |
|-----|---------|-------------|
| `replicas` | `4` | Desired replica count. |
| `strategy` | `canary` | `canary` or `bluegreen`. |
| `image.{repository,tag,pullPolicy,port}` | `argoproj/rollouts-demo`, `blue`, … | Container image. `port` becomes `containerPort`. |
| `canary.trafficRouting.enabled` | `false` | Emit stable+canary Services + a `trafficRouting` block. |
| `canary.trafficRouting.config` | `{}` | The full `spec.strategy.canary.trafficRouting` object. |
| `canary.steps` | 20/40/60/80 @ 5m | The canary `steps[]` list. |
| `bluegreen.{previewService,autoPromotionEnabled,scaleDownDelaySeconds}` | `true`, `false`, `30` | Blue-green knobs. |
| `analysis.enabled` | `false` | Render a background `AnalysisTemplate` and reference it. |
| `analysis.{startingStep,interval,successCondition,failureLimit,provider}` | … | Analysis gate config; `provider` is the full provider block. |
| `service.port` | `80` | Port on the stable/canary/active/preview Services. |
