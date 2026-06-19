# Experiments (A/B Testing, Baseline-vs-Canary)

The `Experiment` CRD runs one or more **ephemeral ReplicaSets** (and optionally AnalysisRuns) for a limited time, then tears them down. It is the building block for A/B testing and Kayenta-style baseline-vs-canary comparisons.

> CRDs: standalone `Experiment` and the `experiment:` step inside a canary Rollout. Field version `argoproj.io/v1alpha1`.
> For analysis mechanics, see `analysis.md`. For strategy trade-offs, see `strategy-decisions.md`.

## When experiments beat canary

- **You need statistical comparison before serving real traffic.** A canary gate asks "is the canary OK at this weight?"; an experiment asks "is canary meaningfully different from baseline?" with parallel non-production traffic.
- **A/B/C testing**: run multiple versions concurrently for a long duration, with metrics compared across all of them.
- **Pre-rollout validation**: launch a new version with labels that exclude it from the live Service, run tests, then let the Rollout continue.
- **Kayenta automated canary analysis**: launch baseline and canary ReplicaSets in parallel, run identical workloads, and let Kayenta score the canary.

## Standalone Experiment

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Experiment
metadata:
  name: example-experiment
spec:
  duration: 20m                              # from when ALL ReplicaSets are healthy
  progressDeadlineSeconds: 30
  templates:
    - name: purple
      replicas: 1
      selector: { matchLabels: { app: canary-demo, color: purple } }
      template: { ... }                       # a PodTemplateSpec
      service: { name: purple-svc }           # optional: creates a Service
    - name: orange
      replicas: 1
      selector: { matchLabels: { app: canary-demo, color: orange } }
      template: { ... }
  analyses:
    - name: purple
      templateName: http-benchmark
      args: [{ name: host, value: purple }]
    - name: compare-results
      templateName: compare
      requiredForCompletion: true             # blocks Experiment completion until done
```

## Lifecycle

1. Create + scale a ReplicaSet per `spec.templates` (and a Service if `service:` is set).
2. Wait for all ReplicaSets to become available (else fail after `progressDeadlineSeconds`).
3. State: `Pending` → `Running`.
4. Start an `AnalysisRun` for each entry in `spec.analyses`.
5. If `duration:` is set, wait it out; otherwise (or with `requiredForCompletion: true`) wait for those analyses.
6. A failed/errored AnalysisRun fails the whole Experiment.
7. On completion, scale ReplicaSets to 0 and terminate incomplete AnalysisRuns.
8. With no `duration` and no `requiredForCompletion`, runs until `spec.terminate: true`.

ReplicaSet names are `<experiment-name>-<template-name>`.

## As a canary step (blocking)

```yaml
strategy:
  canary:
    steps:
      - experiment:
          duration: 1h
          templates:
            - name: baseline
              specRef: stable                 # borrow the stable RS pod spec
            - name: canary
              specRef: canary                 # borrow the canary RS pod spec
          analyses:
            - name: mann-whitney
              templateName: mann-whitney
              args:
                - { name: baseline-hash, value: "{{templates.baseline.podTemplateHash}}" }
                - { name: canary-hash,   value: "{{templates.canary.podTemplateHash}}" }
```

If the Experiment fails or errors, the **Rollout aborts**. The pod-template-hash values are available as `{{templates.<name>.podTemplateHash}}` and `{{templates.<name>.replicaset.name}}` — use them to scope per-version queries in the AnalysisTemplate.

> The Experiment's ReplicaSets get **different** pod-hashes than the Rollout's own canary/stable ReplicaSets, even with identical PodSpecs. This is intentional so metrics can be delineated (the experiment is *not* the same as the live canary).

## Weighted experiment step (traffic routing, v1.1+)

With traffic routing enabled (SMI, ALB, or Istio), an experiment template can take a `weight:` and receive real traffic. Argo Rollouts auto-creates a Service for each weighted template.

```yaml
steps:
  - experiment:
      duration: 1h
      templates:
        - name: experiment-baseline
          specRef: stable
          weight: 5
        - name: experiment-canary
          specRef: canary
          weight: 5
```

Above: 5% → experiment-canary, 5% → experiment-baseline, 90% → old stack. The auto-created Service is named after the ReplicaSet and inherits ports/selector from the `specRef`.

## Experiment Service without a weight

Want a Service but no traffic routing? Set `service:` on the template:

```yaml
templates:
  - name: experiment-baseline
    specRef: stable
    service: { name: test-service }
```

## Dry-run & measurement retention

Both are supported on Experiments (see `analysis.md`): set `spec.dryRun` and `spec.measurementRetention` with `metricName` (regex ok) + `limit`.
