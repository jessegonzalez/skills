# Argo Rollouts manifest generators

These three scripts generate and validate Argo Rollouts manifests from a few
flags, so you can avoid hand-writing YAML (and the common mistakes that come
with it: wrong camelCase, missing `canaryService`, mismatched selectors).

* `gen_rollout.py` — build a `Rollout` manifest.
* `gen_analysis.py` — build an `AnalysisTemplate` manifest.
* `validate.py` — lint a manifest before applying.

Run with `--help` for the per-flag reference. Each script also has a Python
API in `rollout_lib.py` for embedding in other tools.

## Setup

```bash
pip install -r argo-rollouts/requirements.txt   # just PyYAML >= 6.0
# or use the bundled venv:
.venv/bin/python argo-rollouts/scripts/gen_rollout.py --help
```

## Python API

The CLIs are thin wrappers over `rollout_lib`. Import and call directly when
you want manifests in code:

```python
import yaml
from rollout_lib import (
    build_rollout,
    build_analysis_template,
    validate_rollout,
    emit_yaml,
)

doc = build_rollout(
    name="guestbook",
    image="guestbook:v2",
    strategy="canary",
    steps="20 5m,40 5m",
    traffic_routing="istio",
    stable_service="guestbook-stable",
    canary_service="guestbook-canary",
    virtual_service="guestbook-vsvc",
    routes="primary",
)
print(emit_yaml(doc))

errors = validate_rollout(doc)
assert not errors, errors
```

All builders take **keyword-only args** mirroring the CLI flags (underscores
instead of dashes — `traffic_routing` not `traffic-routing`).

---

## `gen_rollout.py`

### Flags

| Flag | Type | Default | Notes |
|---|---|---|---|
| `--name NAME` | str | *(required)* | Rollout name; also used as the app label and container name. |
| `--image IMAGE` | str | *(required)* | Container image, e.g. `guestbook:v2`. |
| `--replicas N` | int | `1` | Desired replica count. |
| `--namespace NS` | str | *(none)* | Optional `metadata.namespace`. |
| `--port PORT` | int | `8080` | `containers[0].ports[0].containerPort`. |
| `--strategy` | `canary` \| `bluegreen` | `canary` | Progressive-delivery strategy. |
| `--steps "W D,..."` | str | *(none)* | Canary steps; `"20 5m,40 5m"` becomes `{setWeight: 20},{pause: {duration: "5m"}}`. Weight-only (`"20"`) and duration-only (`"5m"`) chunks are also supported. Omit for rolling-update behavior. |
| `--traffic-routing` | `istio` \| `nginx` \| `alb` \| `smi` \| `none` | `none` | Traffic router. `none` = pod-ratio canary. |
| `--stable-service NAME` | str | *(none)* | Required when `--traffic-routing != none`. |
| `--canary-service NAME` | str | *(none)* | Required when `--traffic-routing != none`. |
| `--active-service NAME` | str | *(none)* | Required for bluegreen. |
| `--preview-service NAME` | str | *(none)* | Bluegreen only. |
| `--virtual-service NAME` | str | *(none)* | Required when `--traffic-routing=istio`. |
| `--routes r1,r2` | str | *(none)* | Comma-list of Istio VirtualService route names. |
| `--ingress NAME` | str | *(none)* | Required when `--traffic-routing=alb` (the ALB-managed Ingress). |
| `--service-port PORT` | int | *(none)* | Required when `--traffic-routing=alb` (port the ALB targets). |
| `--root-service NAME` | str | *(none)* | ALB root service; required for `--ping-pong` with `alb`. |
| `--annotation-prefix PFX` | str | *(none)* | ALB annotation prefix override. |
| `--ping-pong` | flag | off | Enable `canary.pingPong` (zero-downtime for long-lived connections); requires `--traffic-routing`. |
| `--analysis-template NAME` | str | *(none)* | Background AnalysisTemplate. |
| `--starting-step N` | int | *(none)* | `canary.analysis.startingStep` (delay analysis until step index). |
| `--manual-gate` | flag | off | Bluegreen: set `autoPromotionEnabled: false`. |
| `--max-surge VAL` | str | *(none)* | k8s IntOrString, e.g. `"25%"` or `1`. |
| `--max-unavailable VAL` | str | *(none)* | k8s IntOrString; cannot also be `0` if `--max-surge=0`. |
| `--output FILE` | path | `-` (stdout) | Output path. |

### Examples

**Canary + AWS ALB traffic routing + ping-pong + Prometheus gate** (matches SKILL.md):

```bash
.venv/bin/python argo-rollouts/scripts/gen_rollout.py \
  --name guestbook --image guestbook:v2 --replicas 4 --port 8080 \
  --strategy canary --steps "20 5m,40 5m,60 5m,80 5m" \
  --traffic-routing alb --ingress guestbook-ingress --service-port 443 \
  --root-service guestbook-root --ping-pong \
  --stable-service guestbook-stable --canary-service guestbook-canary \
  --analysis-template success-rate --starting-step 2 \
  > rollout.yaml
```

**Blue-green with a manual gate** (matches SKILL.md):

```bash
.venv/bin/python argo-rollouts/scripts/gen_rollout.py \
  --name my-app --image my-app:v1 --strategy bluegreen --replicas 3 \
  --active-service my-app-active --preview-service my-app-preview --manual-gate
```

**Basic rolling-update canary** (no steps, pod-ratio only):

```bash
.venv/bin/python argo-rollouts/scripts/gen_rollout.py \
  --name api --image api:v3 --replicas 6 --max-surge 25% --max-unavailable 0
```

---

## `gen_analysis.py`

### Flags

| Flag | Type | Default | Notes |
|---|---|---|---|
| `--name NAME` | str | *(required)* | AnalysisTemplate name. |
| `--provider` | one of `prometheus`, `datadog`, `wavefront`, `newrelic`, `cloudwatch`, `graphite`, `influxdb`, `kayenta`, `job`, `web` | *(required)* | Metric provider. |
| `--query Q` | str | *(none)* | Required for `prometheus`/`graphite`/`influxdb`/`datadog`. |
| `--address URL` | str | *(none)* | Required for `prometheus`/`graphite`/`influxdb` (e.g. `http://prometheus:9090`). |
| `--success EXPR` | str | *(none)* | `successCondition`, e.g. `result[0] >= 0.95`. |
| `--failure EXPR` | str | *(none)* | `failureCondition` (optional). |
| `--failure-limit N` | int | `0` | `failureLimit`. |
| `--consecutive-success-limit N` | int | `0` | `consecutiveSuccessLimit` (0 = success logic disabled). |
| `--interval DUR` | str | *(none)* | Go duration between evaluations, e.g. `5m`. |
| `--count N` | int | *(none)* | Number of evaluations before terminating. |
| `--metric-name NAME` | str | `success-rate` | Name of the metric. |
| `--arg NAME=VALUE` | repeatable | *(none)* | Template args (repeat the flag). |
| `--output FILE` | path | `-` (stdout) | Output path. |

### Provider shapes

| Provider | Generated block | Notes |
|---|---|---|
| `prometheus`, `graphite`, `influxdb` | `provider: {<name>: {address, query}}` | Fully supported. |
| `datadog` | `provider: {datadog: {apiVersion: v1, query}}` | v1 shape; v2 (`queries`/`formula`) needs hand-editing. |
| `wavefront`, `newrelic`, `cloudwatch`, `kayenta`, `job`, `web` | `provider: {<name>: {query}}` | **Best-effort stub.** These providers have provider-specific shapes; hand-edit the output before applying. See `references/analysis.md`. |

### Example

```bash
.venv/bin/python argo-rollouts/scripts/gen_analysis.py \
  --name success-rate --provider prometheus \
  --address http://prometheus:9090 \
  --query 'sum(rate(http_requests_total{status!~"5.."}[5m]))/sum(rate(http_requests_total[5m]))' \
  --success 'result[0] >= 0.95' --failure-limit 3 --interval 5m \
  > analysis.yaml
```

---

## `validate.py`

### Usage

```bash
.venv/bin/python argo-rollouts/scripts/validate.py FILE [FILE ...]
```

Loads each YAML file (multi-doc safe), dispatches by `kind`, prints errors to
stderr in the form `FILE: kind: <message>`, and exits `0` if everything is
valid or `1` if any error was found.

### Rules checked (Rollout)

1. `apiVersion == argoproj.io/v1alpha1` and `kind == Rollout`.
2. Exactly one of `spec.strategy.canary` / `spec.strategy.blueGreen`.
   Flags the lowercase `bluegreen` typo.
3. `spec.selector.matchLabels` is a subset of `spec.template.metadata.labels`.
4. If `trafficRouting` is set → `canaryService` and `stableService` required.
5. If `blueGreen` is set → `activeService` required.
6. `maxSurge` and `maxUnavailable` cannot both be `0` (string or int form).
7. Every `analysis.templates[]` entry has a `templateName`.
8. Each canary step has exactly one of the known step keys
   (`setWeight`/`pause`/`analysis`/`experiment`/`setCanaryScale`/
   `setHeaderRoute`/`setMirrorRoute`/`plugin`/`replicaProgressThreshold`).

### Rules checked (AnalysisTemplate)

`apiVersion`/`kind` correct; at least one metric in `spec.metrics[]`; each
metric has a `name`; each metric has a `provider`.

### Example

```bash
.venv/bin/python argo-rollouts/scripts/validate.py rollout.yaml analysis.yaml
```

---

## Running the tests

```bash
.venv/bin/python -m pytest argo-rollouts/tests/ -v
.venv/bin/ruff check argo-rollouts/scripts/ argo-rollouts/tests/
```
