---
name: argo-rollouts
description: Author, operate, and troubleshoot Argo Rollouts, the Kubernetes progressive delivery controller. Covers the Rollout CRD, canary and blue-green strategies, AnalysisTemplates with metric gates (Prometheus, Datadog, Wavefront, New Relic, CloudWatch, Graphite, InfluxDB, Kayenta, Job, Web), traffic routing via Istio, NGINX, SMI, AWS ALB, Traefik, Apisix, Gloo, Gateway API, experiments and A/B testing, the kubectl argo rollouts plugin, GitOps with Argo CD, and Slack/Teams notifications. Use whenever the user mentions progressive delivery, canary or blue-green deploys, weighted traffic shifting, metric-based promotion or auto-rollback, converting a Deployment to a Rollout, or says things like "promote/abort/undo the rollout" or "my canary isn't getting traffic" - even without naming Argo Rollouts.
license: MIT
compatibility: Scripts are self-contained (PEP 723) and run via `uv run scripts/...` with zero install, or `python3 scripts/...` with PyYAML. Tests need pytest (see requirements.txt). Operates on Kubernetes clusters with the Argo Rollouts controller and the `kubectl argo rollouts` plugin.
metadata:
  author: argo-rollouts-skill
  version: "1.1.0"
  spec: agentskills.io
allowed-tools: Bash(uv:*) Bash(python3:*) Bash(.venv/bin/python:*) Bash(kubectl:*) Bash(kubectl-argo-rollouts:*) Read Write Edit Glob Grep
---

# Argo Rollouts

Argo Rollouts is a Kubernetes controller + CRDs that adds progressive delivery (canary, blue-green, metric-gated promotion, experiments) as a richer replacement for the stock `Deployment`. Treat it as a **Deployment-compatible workload whose reconciler is a state machine that walks deployment steps instead of doing a blind rolling update.**

You are helping a user design, write, convert, debug, or operate Rollouts. **Always reason from the reconciler mental model first** (below). Ground every YAML suggestion and every troubleshooting step in how the controller actually moves traffic and replicas. Field paths here are verified against `argoproj.io/v1alpha1`; when the docs and this skill disagree, trust the docs and tell the user.

## How to use this skill

This file is the orientation layer. For depth, read the matching reference. For manifests, **prefer the generator scripts** over hand-writing YAML (faster, less context, always valid).

| When the user wants to... | Use |
|---|---|
| Generate a Rollout or AnalysisTemplate manifest | `scripts/gen_rollout.py`, `scripts/gen_analysis.py` (see below) |
| Validate a manifest before applying | `scripts/validate.py FILE` |
| Author/tune a canary or pick a strategy | `references/canary.md`, `references/strategy-decisions.md` |
| Author/tune a blue-green | `references/blue-green.md` |
| Add metric gates or write an AnalysisTemplate | `references/analysis.md` |
| Split traffic with Istio/NGINX/ALB/SMI/Gateway API | `references/traffic-routing.md` |
| Reason about phases, steps, abort, rollback semantics | `references/state-machine.md` |
| Operate day-2 (promote, abort, undo, watch) | `references/kubectl-plugin.md` |
| Diagnose a stuck/aborted/mis-routing rollout | `references/troubleshooting.md` |
| Do A/B testing or baseline-vs-canary comparisons | `references/experiments.md` |
| Pair with Argo CD (GitOps, rollback semantics, self-heal) | `references/gitops-argocd.md` |
| Set up Slack/Teams notifications | `references/notifications.md` |
| Install the controller/plugin or migrate Deployments | `references/install-config.md` |

## The reconciler mental model (read this before answering anything non-trivial)

Internalize these and most user questions answer themselves:

1. **A `Rollout` is a `Deployment` superset.** `spec.selector`, `spec.template`, `spec.replicas`, `minReadySeconds`, `revisionHistoryLimit` are identical. The only structural change is `spec.strategy`: instead of `rollingUpdate`/`recreate`, you set `spec.strategy.canary` or `spec.strategy.blueGreen`. That is the whole Deployment→Rollout migration in three fields (`apiVersion`, `kind`, `strategy`).
2. **The controller drives updates by managing ReplicaSets, not Pods.** Any `spec.template` change creates a new ReplicaSet ("revision"). The new one is the **canary/desired**; the last fully-promoted one is **stable**. Each ReplicaSet carries a unique `rollouts-pod-template-hash` label.
3. **Traffic moves one of two ways.** *No traffic router:* split is approximated by **pod-count ratio** (kube-proxy); with 5 replicas you cannot do better than ~20% granularity. *With a router* (`spec.strategy.canary.trafficRouting`): the controller rewrites the mesh/ingress CR to split traffic **exactly, independent of pod counts** - this unlocks `setCanaryScale`, `setHeaderRoute`/`setMirrorRoute`, `dynamicStableScale`.
4. **Services are the swivel.** The controller owns two Services' selectors (`stableService`/`canaryService`, or `activeService`/`previewService`) and patches them onto the `rollouts-pod-template-hash` of the ReplicaSet that should receive that traffic. When debugging "traffic not shifting," **start at the Service selectors** and never hand-edit them.
5. **`AnalysisRun` is the gate object.** An `AnalysisTemplate` is the *recipe* (queries + conditions); an `AnalysisRun` is the *instantiation* the controller creates and watches. Its terminal phase maps to rollout actions: `Successful`→proceed, `Failed`→abort, `Inconclusive`→pause, `Error`→pause.
6. **The stable ReplicaSet is the source of truth for "known-good."** `status.stableRS` tracks which hash is considered stable. Rollback = revert to stable; promotion = a new hash becomes stable.
7. **Initial deploy skips the strategy.** On first creation, the controller scales the ReplicaSet straight to `spec.replicas` (like a Deployment). Strategy steps run only on subsequent `spec.template` changes. "My steps were ignored" usually means they are looking at the initial deploy.

## The five CRDs

| CRD | Scope | Role |
|-----|-------|------|
| `Rollout` | namespace | The workload. Owns ReplicaSets/Services, drives the strategy. Drop-in for `Deployment`. |
| `AnalysisTemplate` | namespace | Reusable metric recipe, parameterized with `args`. |
| `ClusterAnalysisTemplate` | cluster | Same, shareable across namespaces (`clusterScope: true`). |
| `AnalysisRun` | namespace | Instantiation of templates for a specific rollout/experiment. Terminal-phaseed like a Job. |
| `Experiment` | namespace | Short-lived parallel ReplicaSets for A/B or statistical comparison. |

## Decision framework: which strategy?

| Question | Use |
|----------|-----|
| App **cannot** run two versions in parallel (DB locks, queue workers, shared files)? | **Blue-green** (only one version "active") - or don't use Rollouts. |
| No mesh/ingress available, coarse traffic control is fine? | **Blue-green** or **basic canary** (pod-ratio only). |
| Fine-grained exact percentages, header/mirror routing, or A/B? | **Canary + a traffic router.** |
| Compare baseline vs canary side-by-side with statistics before real traffic? | **Experiment** step. |
| Just want RollingUpdate but with `undo`/`promote`/`abort`? | **Canary with no steps** (uses `maxSurge`/`maxUnavailable`). |

Heuristic from upstream: **start with blue-green, graduate to canary once your metrics and traffic router are trustworthy.** Canaries require the app to be stateless and share-nothing across versions. Full trade-off matrix and HPA/anti-affinity gotchas: `references/strategy-decisions.md`.

## Decision framework: which traffic router?

`spec.strategy.canary.trafficRouting` takes exactly one primary block. Core providers: `istio` (richest: `setHeaderRoute`, `setMirrorRoute`, `pingPong`), `nginx` (canary annotations), `alb` (weighted target groups), `smi` (provider-agnostic via `TrafficSplit`). Gateway API and others are plugins. **`canaryService` + `stableService` are mandatory whenever `trafficRouting` is set**, and the mesh/ingress objects must reference those service names back. Per-provider config and `managedRoutes` precedence: `references/traffic-routing.md`.

## Decision framework: where to put analysis?

| Where | Field | Blocks? | Best for |
|-------|-------|---------|----------|
| Background | `spec.strategy.canary.analysis` | No | Continuous SLO guardrail; abort on regression. Use `startingStep:` to delay until canary has traffic. |
| Inline step | `steps: [{ analysis: ... }]` | Yes | Point-in-time gate ("after 5%, run smoke tests"). |
| BlueGreen pre-promotion | `blueGreen.prePromotionAnalysis` | Yes | Validate preview stack before prod traffic. |
| BlueGreen post-promotion | `blueGreen.postPromotionAnalysis` | Yes (failure reverts) | Validate after cutover; on failure flips service back. |

Key knobs: `successCondition`/`failureCondition` (expr-lang over `result`), `failureLimit`/`consecutiveSuccessLimit` (one must apply), `interval`+`count`. A metric with no conditions and no `count` **runs forever** - a classic "analysis never completes" cause. Full provider list, args, dry-run, NaN handling: `references/analysis.md`.

## When NOT to use Argo Rollouts

Push back (don't force-fit) when: queue workers / shared-locked resources / single-tenant schemas that can't run two versions; multi-cluster orchestration (Rollouts is single-cluster); infra apps; or you need parallel releases living for days (Rollouts targets brief 15-20 min deployments).

## Generate manifests programmatically (prefer this over hand-writing YAML)

Hand-writing Rollout YAML is verbose and error-prone (wrong camelCase, missing `canaryService`, mismatched selectors). The bundled generators build valid manifests from a few flags and keep context usage low. They are **self-contained** — `uv` installs their one dependency (PyYAML) automatically on first run, so there is no separate install step.

### Available scripts

- **`scripts/gen_rollout.py`** — generates a `Rollout` (canary or blue-green, optional traffic routing, optional background analysis).
- **`scripts/gen_analysis.py`** — generates an `AnalysisTemplate` for any provider (prometheus, datadog, wavefront, ...).
- **`scripts/validate.py`** — checks a manifest for the common mistakes (wrong apiVersion, mismatched selectors, traffic routing without `canaryService`, both `maxSurge`/`maxUnavailable` zero, ...). Prints errors to stderr; exits 0 if valid, 1 on errors, 2 on usage error.
- **`scripts/rollout_lib.py`** — shared library and the importable Python API (`build_rollout`, `build_analysis_template`, `validate_rollout`).

Paths in the commands below are relative to this skill directory. `uv run` is the zero-install path; if `uv` is unavailable, use `python3 scripts/...` with PyYAML installed.

**Canary with a Prometheus gate and Istio traffic routing:**
```bash
uv run scripts/gen_rollout.py \
  --name guestbook --image guestbook:v2 --replicas 4 --port 8080 \
  --strategy canary --steps "20 5m,40 5m,60 5m,80 5m" \
  --traffic-routing istio --virtual-service guestbook-vsvc --routes primary \
  --stable-service guestbook-stable --canary-service guestbook-canary \
  --analysis-template success-rate --starting-step 2 \
  > rollout.yaml

uv run scripts/gen_analysis.py \
  --name success-rate --provider prometheus \
  --address http://prometheus:9090 \
  --query 'sum(rate(http_requests_total{status!~"5.."}[5m]))/sum(rate(http_requests_total[5m]))' \
  --success 'result[0] >= 0.95' --failure-limit 3 --interval 5m \
  > analysis.yaml

uv run scripts/validate.py rollout.yaml analysis.yaml
```

**Blue-green with a manual gate:**
```bash
uv run scripts/gen_rollout.py \
  --name my-app --image my-app:v1 --strategy bluegreen --replicas 3 \
  --active-service my-app-active --preview-service my-app-preview --manual-gate
```

Both generators also expose a Python API (`build_rollout(**kwargs) -> dict`, `build_analysis_template(**kwargs) -> dict`, `validate_rollout(doc) -> list[str]`) so you can construct manifests in code. The contract is proven by the test suite in `tests/` — run it with `python -m pytest tests/` after `pip install -r requirements.txt`. See `scripts/README.md` for the full flag reference.

## Day-2 operations: the kubectl plugin is primary

There is **no separate Argo Rollouts API** - the plugin just patches the `Rollout` object or reads status. The critical triad:

- **`promote`** - "looks good, advance." `kubectl argo rollouts promote NAME` (next step) or `--full` (skip all pauses to 100%).
- **`abort`** - "this is bad, send traffic back to stable now." Sets canary weight→0 / flips active service back. **Does not touch Git.**
- **`undo`** - "go back to a specific older revision." Uses revision history. Fast-track only while the old ReplicaSet is still scaled up (within `scaleDownDelaySeconds`).

```bash
kubectl argo rollouts get rollout NAME -w      # live tree (RS/pods/analysis/steps)
kubectl argo rollouts list rollouts
kubectl argo rollouts pause NAME               # manual pause (resume via promote)
kubectl argo rollouts retry rollout NAME       # retry after abort/deadline
kubectl argo rollouts restart NAME             # rolling pod restart, no new RS
kubectl argo rollouts terminate NAME           # stop an AnalysisRun/Experiment
kubectl argo rollouts status NAME              # scriptable; exits non-zero on failure
kubectl argo rollouts lint FILE.yaml           # validate before applying
kubectl argo rollouts dashboard                # local UI
```

Full cheatsheet with flags and what to look for in output: `references/kubectl-plugin.md`.

## Common mistakes to avoid

These fail silently or look mysterious - check them first:

- **Field is `blueGreen`, not `bluegreen` or `blue-green`.** YAML key is camelCase: `spec.strategy.blueGreen`.
- **`canaryService`/`stableService` are required for traffic routing**, and the mesh/ingress objects (e.g. Istio `VirtualService`) must reference those service names back. A mismatch is the #1 cause of "traffic isn't shifting."
- **`pause: {}` vs `pause: { duration: 10m }`.** The former waits forever; the latter auto-advances. Units `s`/`m`/`h`; bare numbers are seconds.
- **`maxUnavailable: 0` requires `maxSurge > 0`** (and vice versa). Both cannot be zero.
- **Analysis with `count: 0` inside a step will not execute.** `count: 0` ("run forever") is only meaningful for background analysis.
- **Initial creation skips steps and analysis.** Trigger a real `spec.template` update before claiming "steps ignored."
- **Blue-green + AWS ALB can cause brief downtime** - the ALB controller deregisters before registering. Prefer canary+ALB or `pingPong`.
- **HPA + basic canary fights**: a leaking canary raises the average metric and HPA scales **stable** up. Use a traffic router or `setCanaryScale`/`dynamicStableScale`.
- **Helm and Argo Rollouts both consume `{{ }}`.** Escape analysis args as `{{ `{{ args.x }}` }}` in Helm-rendered manifests.
- **GitOps (Argo CD) can flap Istio weights**: add `ignoreDifferences` for `VirtualService` `.spec.http[].route[].weight`.

## Troubleshooting: first questions

| Symptom | First check |
|---------|-------------|
| Stuck/not progressing | `get rollout NAME -w` → phase + `status.pauseConditions[].reason`; check `progressDeadlineSeconds`/`progressDeadlineAbort`. |
| Canary traffic not shifting | Are `canaryService`/`stableService` selectors pointing at the right `rollouts-pod-template-hash`? Did the router rewrite its CR? Check `.status.canary.weights`. |
| Analysis Error/Failed | Provider reachable? `kubectl get analysisrun`; read `status.message` + `phase`. Guard empty Prometheus results (`len(result)==0`). |
| Wrong ReplicaSet active | Compare `status.stableRS` vs `status.currentPodHash`. A mid-rollout template change abandons the in-flight RS. |
| Service selector mismatch / 502s | Controller owns Service selectors - don't hand-edit. Missing/typo'd `canaryService`/`activeService` is the usual cause. |

Full symptom→cause→fix runbook (12 scenarios incl. HPA, ALB downtime, Argo CD fights, "analysis never completes"): `references/troubleshooting.md`.

## Writing manifests: the checklist

When authoring or editing a Rollout for the user, verify:

1. `apiVersion: argoproj.io/v1alpha1` and `kind: Rollout` (not `apps/v1`).
2. `spec.selector` matches `spec.template.metadata.labels`.
3. Exactly one of `spec.strategy.canary` or `spec.strategy.blueGreen`.
4. Blue-green has `activeService`; canary-with-traffic-routing has `canaryService` + `stableService` + a matching `trafficRouting` block referencing real Services/VirtualServices/Ingresses.
5. Every `pause` is intentional: `{}` for manual gates, `{ duration: ... }` for time-boxed.
6. Any referenced `AnalysisTemplate` exists (same namespace, or `clusterScope: true`) and its required `args` are supplied by the Rollout.
7. `revisionHistoryLimit` (default 10) is set explicitly if the user cares about `undo` or controller memory at scale.

`scripts/validate.py` checks rules 1-4 and 6 programmatically - run it before suggesting the user apply.
