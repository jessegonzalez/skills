# Install, Configuration, Migration, Upgrades

For when to use Argo Rollouts at all (and when not to), see `strategy-decisions.md`. For day-2 plugin commands, see `kubectl-plugin.md`. For GitOps wiring, see `gitops-argocd.md`.

## Controller install

### Standard (cluster-scoped)

```bash
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts -f \
  https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml
```

Creates the `argo-rollouts` namespace with the controller + CRDs.

- **Custom namespace?** Update the ClusterRoleBinding's serviceaccount namespace reference in `install.yaml`.
- **Kubernetes < 1.15:** apply CRDs with `--validate=false` (newer CRD fields are rejected by older API servers).
- **GKE:** grant yourself cluster-admin first:

  ```bash
  kubectl create clusterrolebinding <you>-cluster-admin-binding \
    --clusterrole=cluster-admin --user=<you>@gmail.com
  ```

Container images live on **Quay** (`quay.io/argoproj/argo-rollouts`) — Docker Hub is deprecated due to rate limits.

### Namespace-scoped (multi-tenant isolation)

Use `namespace-install.yaml` (only namespace-level privileges). **CRDs are NOT included** — install them separately:

```bash
kubectl apply -k https://github.com/argoproj/argo-rollouts/manifests/crds?ref=stable
```

Use case: several Rollouts controllers in different namespaces on one cluster (tenant isolation). The `--namespaces` flag further restricts which namespaces a controller reconciles.

> Forgetting the separate CRD apply when using `namespace-install.yaml` is the classic "controller running but nothing happens" cause — see `troubleshooting.md` §3.

## kubectl plugin install

The plugin is optional but is the primary day-2 tool.

- **Brew:** `brew install argoproj/tap/kubectl-argo-rollouts`
- **Manual:**

  ```bash
  curl -LO https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-darwin-amd64
  chmod +x kubectl-argo-rollouts-darwin-amd64
  sudo mv kubectl-argo-rollouts-darwin-amd64 /usr/local/bin/kubectl-argo-rollouts
  ```

  (Replace `darwin-amd64` with your OS/arch, e.g. `linux-amd64`, `darwin-arm64`.)
- **Docker:** `docker run quay.io/argoproj/kubectl-argo-rollouts:master <cmd>`

Verify: `kubectl argo rollouts version`

**Shell completion** (kubectl ≥ 1.26): create a `kubectl_complete-argo-rollouts` script on `PATH`:

```sh
#!/usr/bin/env sh
kubectl argo rollouts __complete "$@"
```

Or for standalone use: `source <(kubectl-argo-rollouts completion bash)` (also `zsh`/`fish`/`powershell`).

## HA mode

Run multiple controller replicas with leader election:

- Set `--leader-elect` on the controller.
- Scale the controller Deployment to >1 replica.
- Tune `--leader-election-lease-duration` and `--leader-election-renew-deadline` for clock-skew tolerance (uses k8s client-go leaderelection).

### Other useful controller flags

- `--namespaces` — restrict to a set of namespaces (multi-tenant).
- `--instance-id` — only reconcile Rollouts with a matching instance label.
- `--nginx-ingress-classes` — restrict NGINX ingresses the controller will manage (default `nginx`; repeatable; `''` matches any).
- `--self-service-notification-enabled` — enable per-namespace notifications (`notifications.md`).

## Migrating a Deployment → Rollout

### Option A: Convert in place (3 field changes)

1. `apiVersion: apps/v1` → `argoproj.io/v1alpha1`
2. `kind: Deployment` → `Rollout`
3. `spec.strategy: {rollingUpdate|recreate}` → `spec.strategy: {canary: {...} | blueGreen: {...}}`

That's the whole migration. `spec.selector`, `spec.template`, `spec.replicas`, `minReadySeconds`, `revisionHistoryLimit` are identical.

⚠️ **For workloads already serving production traffic:** run the new Rollout **side-by-side** with the Deployment first (different name), confirm it's healthy, **then** delete/scale the Deployment. Converting in-place without a side-by-side window risks downtime. The side-by-side window doubles pod count temporarily — budget for it.

### Option B: Reference the Deployment via `workloadRef`

Keep the Deployment; let the Rollout adopt its pod template. Useful when other tooling expects a Deployment.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata: { name: my-app }
spec:
  replicas: 3
  selector: { matchLabels: { app: my-app } }
  workloadRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app
    scaleDown: onsuccess        # never | onsuccess | progressively
  strategy:
    canary:
      steps:
        - setWeight: 25
        - pause: { duration: 5m }
```

`scaleDown` controls how the old Deployment is retired:

- `never` — leave the Deployment scaled as-is.
- `onsuccess` — scale it to 0 once the Rollout is healthy (recommended).
- `progressively` — drain it as the Rollout scales up (rollback re-scales it).

Rollouts runs its own Pods alongside the Deployment during migration → **temporary 2× pod count**. The controller tracks the Deployment generation and exposes it as `status.workloadObservedGeneration` so you can confirm sync. To update, **change the Deployment's pod template** (not the Rollout's).

### Roll back to Deployments

Reverse: change `apiVersion`/`kind` back and drop `spec.strategy`, **or** (for `workloadRef`) scale the Deployment up, wait for Ready, scale the Rollout to 0. Always run side-by-side to avoid downtime.

## Triggering a rollout without an image change

- `kubectl argo rollouts set image ROLLOUT CONTAINER=IMG`
- `kubectl argo rollouts restart ROLLOUT` (cycles pods, same image)
- A new image is the canonical trigger; for ConfigMap-driven changes, hash the ConfigMap name into the pod template (and use `PruneLast=true` under Argo CD so the old ConfigMap survives until the rollout succeeds — see `gitops-argocd.md`).

## Upgrading the controller

The controller is stateless (no external state). Safe upgrade path:

1. Pick a window with **no active deployments** if possible.
2. Delete the old controller manifest; apply the new one.
3. New controller resumes any in-flight rollouts on startup.

In-flight rollouts during upgrade are paused while the controller is down and resume automatically — zero downtime, but try to avoid mid-deploy upgrades.

**Version skew** between controller and kubectl plugin: there is no separate API; the plugin just patches the Rollout. Old plugins may not understand new spec fields, but no breaking spec changes have been made intentionally — old plugins keep working with newer controllers (minus brand-new features). Recommendation: keep them roughly in sync.

## Reducing controller memory (large fleets)

On clusters with thousands of Rollouts, lower `revisionHistoryLimit` (default 10). One report: 27% memory reduction on 1290 rollouts by setting it to `0`. Trade-off: fewer old ReplicaSets → `undo` reach is shorter (see fast-track rollback in `state-machine.md`).

## What Argo Rollouts is NOT for

- Infrastructure apps (cert-manager, coredns, nginx-ingress, sealed-secrets).
- Long-running parallel versions (days/weeks). Designed for brief (15–20 min, max 1–2 hour) progressive rollouts.
- Multi-cluster or multi-app coordinated rollouts (one Rollout = one app, one cluster). Compose with external orchestration if you need more.
- Preview/ephemeral environments (use Argo CD PR generators instead).

Fuller "when NOT to use" discussion: `strategy-decisions.md`.

## Scope of Git

Argo Rollouts **never reads or writes Git**. It only reacts to the live `Rollout` object (regardless of how it got there: GitOps, kubectl, Helm, Flux). All "rollback to Git" concerns are handled by Argo CD or external glue (`gitops-argocd.md`).
