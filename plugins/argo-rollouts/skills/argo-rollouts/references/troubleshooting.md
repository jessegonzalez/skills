# Troubleshooting Runbook

Symptom → likely cause → fix. **Always start with the four diagnostic commands:**

```bash
kubectl argo rollouts get rollout NAME -w                          # tree: phase, weights, pause reasons
kubectl get rollout NAME -o yaml                                   # full status incl. conditions & pauseConditions
kubectl get events --sort-by=.lastTimestamp -n NS | tail -40
kubectl logs -n argo-rollouts deploy/argo-rollouts --tail=300 | grep NAME
```

Read `status.phase`, `status.message`, `status.pauseConditions[]` (and its `reason`), `status.conditions[]`, and compare `status.stableRS` vs `status.currentPodHash`.

For deeper mechanism (why the controller does X), see `state-machine.md`. For command flags, see `kubectl-plugin.md`.

---

## 1. Rollout stuck / "Paused" and not progressing

**Symptoms:** `get rollout -w` shows `Paused` indefinitely; no new ReplicaSet activity; `status.pauseConditions[].reason` tells you which kind.

**Causes & fixes by reason:**

- `StepPause` — a `pause: {}` (indefinite) step. **Fix:** `kubectl argo rollouts promote NAME` (next step) or `--full` (to 100%). Prefer `pause: { duration: 5m }` for automated flows.
- `BlueGreenPause` — blue-green with `autoPromotionEnabled: false` waiting for a human. **Fix:** `kubectl argo rollouts promote NAME`.
- `AnalysisRunInconclusive` — an AnalysisRun finished neither success nor failure (value between thresholds, or no success/failure condition defined). **Fix:** decide manually — `promote` to continue or `abort` to revert.
- Manual `spec.paused: true` (set by `kubectl argo rollouts pause` or in the manifest). **Fix:** `promote` to resume.
- `progressDeadlineSeconds` exceeded but `progressDeadlineAbort: false` (default) — the rollout is stuck-but-not-aborted. **Fix:** either `abort` and `undo`, or set `progressDeadlineAbort: true` so future stalls auto-abort.

---

## 2. Rollout "Aborted" / "Degraded"

**Symptoms:** STATUS `Aborted` or `Degraded`; canary weight back at 0; `status.abort: true`.

**Causes & fixes:**

- An AnalysisRun **Failed** → `kubectl get analysisrun -l rollouts-pod-template-hash=<hash> -o yaml`. Inspect `status.metricResults[].measurements[].phase` and `message`. Fix the metric/app, then `kubectl argo rollouts retry rollout NAME`.
- `progressDeadlineAbort: true` + slow/dead pods → check pod readiness, image pull, probes. Fix and `retry`.
- Readiness probe failing on new pods → `kubectl describe pod`, check events, image, config. The new ReplicaSet will never go `Available`.
- Resource quota / scheduling → `kubectl describe rs` shows events; check `kubectl get resourcequota`.

**Recovery:** `abort` already reverted traffic to stable. To retry the same revision: `retry rollout`. To go back a revision: `undo`. To fix-forward: push the fixed manifest (GitOps) and re-apply.

---

## 3. New ReplicaSet never created / not scaling

**Symptoms:** `spec.template` changed but no new ReplicaSet appears, or pods not progressing.

**Causes & fixes:**

- **Controller not running / not watching this namespace.** `kubectl get pods -n argo-rollouts`; check the controller is up and its `--namespaces` flag (if any) includes yours. The controller must run on *every* cluster that hosts Rollout workloads.
- **CRD not installed** (common with `namespace-install.yaml`, which excludes CRDs). `kubectl get crd rollouts.argoproj.io` — if missing, install CRDs separately: `kubectl apply -k https://github.com/argoproj/argo-rollouts/manifests/crds?ref=stable`.
- **RBAC** — controller service account lacks permissions in the namespace. Check controller logs for forbidden errors.
- **Invalid manifest** — `kubectl argo rollouts lint file.yaml` before apply.
- **ReplicaSet owned by a Deployment** — if a Deployment with the same name exists and the Rollout uses `workloadRef`, ensure the Deployment is scaled to 0 and `scaleDown` semantics are what you intended.

---

## 4. Traffic not shifting to the canary (basic canary, no mesh)

**Symptoms:** `setWeight: 50` but traffic still ~100% to old version.

**Cause:** Without `trafficRouting`, traffic split = **pod-count ratio**. With few replicas, ratios are coarse (e.g. 4 replicas, 20% = `ceil(4*0.2)` = 1 pod = 25% actual). Also `maxSurge`/`maxUnavailable` constrain how fast pods change.

**Fix:**

- Use a **traffic router** (`trafficRouting.istio`/`nginx`/`alb`/`smi`) for exact, pod-count-independent weights. See `traffic-routing.md`.
- Or increase replicas so ratios land closer to the desired weight.
- Check `maxSurge`/`maxUnavailable` aren't zeroed out improperly (one of them must be non-zero).

---

## 5. Traffic not shifting (with a traffic router)

**Symptoms:** Weight set, but mesh/ingress still sends everything to stable.

**Causes & fixes:**

- **Istio VirtualService not updated.** Verify the VirtualService name and route names in `trafficRouting.istio.virtualService.{name,routes}` match the actual VirtualService. If there are multiple routes and you omit `routes:`, the controller can't pick. `kubectl get virtualservice VS -o yaml` and check `http[].route[].destination.weight` was rewritten.
- **NGINX**: the controller creates a *canary* ingress with `nginx.ingress.kubernetes.io/canary-weight` annotations. Check `kubectl get ingress`. The `stableIngress` name must match. Custom annotation prefix? Set `trafficRouting.nginx.annotationPrefix`.
- **ALB**: target group weights are managed via the ALB ingress annotations. ALB blue-green has a known **downtime risk** (controller deregisters old before registering new) — prefer canary with ALB, or `pingPong`. Check `trafficRouting.alb.ingress` + `servicePort` are set.
- **SMI**: the TrafficSplit object must exist (or `rootService`/`trafficSplitName` configured). `kubectl get trafficsplit`.
- **Selector mismatch** on canary/stable Services — the controller rewrites selectors with `rollouts-pod-template-hash`; if the Services were created by hand with the wrong selector or were since edited, traffic won't flow. `kubectl get svc canary-svc stable-svc -o yaml` and confirm selector matches the ReplicaSet's pod-template-hash label.
- **`argo-rollouts.argoproj.io/managed-by-rollouts` annotation missing** on a Service/Ingress means the controller won't touch it (it only manages resources it annotated).
- **Mesh enrollment**: workload not enrolled, missing sidecar, wrong host headers.

---

## 6. Wrong ReplicaSet active / Service pointing at old version

**Symptoms:** After promotion, traffic still hits the old version.

**Causes & fixes:**

- **iptables propagation delay.** `scaleDownDelaySeconds` default is 30s for exactly this reason — nodes need time to update iptables after the Service selector changes. Don't set it below 30. Wait it out.
- **Service selector stale.** `kubectl get svc ACTIVE_SVC -o yaml` — the `rollouts-pod-template-hash` value in its selector should match the *new* ReplicaSet's hash. If not, the controller didn't reconcile (check logs / RBAC) or the Service isn't annotated `managed-by-rollouts`.
- **`previewService` confusion** — preview always points to the *newest* ReplicaSet; active only flips on promotion. If you're hitting preview, you're hitting the candidate, not prod.
- **Mid-rollout template change** abandons the in-flight ReplicaSet and starts fresh from step 0 — see `state-machine.md`.

---

## 7. AnalysisRun never completes / runs forever

**Symptoms:** `kubectl get analysisrun` shows `Running` indefinitely; rollout blocks at an inline analysis step.

**Causes & fixes:**

- **No terminal conditions.** A metric with no `successCondition`, no `failureCondition`, no `count`, and no `failureLimit`/`consecutiveSuccessLimit` runs forever. Add `count` (number of samples) and/or explicit conditions. See `analysis.md`.
- **`failureLimit: 0` (default) never tripped AND success never earned** — `consecutiveSuccessLimit: 0` (default) means success logic is *disabled*, so you must set `consecutiveSuccessLimit ≥ 1` to ever succeed, or rely on `count` ending the run.
- **Provider errors** — bad Prometheus URL, missing API key, network policy. Errors are distinct from failures; check `consecutiveErrorLimit` (default 4). Look at `status.metricResults[].measurements[].phase: Error` and the `message`. `kubectl argo rollouts terminate analysisrun NAME` to stop a stuck run.
- **`interval` too long** — e.g. `interval: 1h` with `count: 5` = 5 hours. Tune to your deployment window (best practice: metrics that resolve in 5–15 min).
- **Background analysis** intentionally runs until rollout completes; that's expected — it's only "stuck" if the rollout itself is stuck.

---

## 8. HPA fighting the rollout

**Symptoms:** Replica counts jump unexpectedly mid-rollout; canary weight effectively changes on its own; stable pods scale up because canary is leaking.

**Causes & fixes:**

- **Basic canary + single HPA** — HPA sees canary+stable as one pool; a faulty canary (memory leak, CPU spin) raises the average and scales *stable* up, defeating the canary signal.
  - **Fix A:** Use a **traffic router** so weight is independent of pod count.
  - **Fix B:** Add `setCanaryScale` steps to pin canary pod count; HPA then only affects stable.
  - **Fix C:** `dynamicStableScale: true` to shrink stable as canary grows.
- **HPA scaling during abort** — for basic canary (no mesh), after an abort the stable ReplicaSet may need manual scaling back up to handle load.
- **Blue-green + HPA** — both blue and green scale in unison (2× cost). Use `previewReplicaCount` to pin the preview and let HPA manage only stable.

Full HPA discussion: `strategy-decisions.md`.

---

## 9. Argo CD keeps "fighting" the rollout / Istio weights flap

**Symptoms:** Argo CD shows `OutOfSync` or repeatedly syncs mid-rollout; rollout never settles; Istio weights flap back and forth.

**Causes & fixes:**

- **Self-heal on** while a rollout is in progress — Argo CD sees the in-cluster ReplicaSet/Service drift (controller-modified) and tries to "correct" it. **Fix:** disable self-heal for the Rollout Application (`spec.syncPolicy.selfHeal: false`), or scope Argo CD to manage *only* the Rollout manifest and let Rollouts own Services/ReplicaSets.
- **Both managing Services** — let Argo Rollouts own the canary/stable/active Services (don't also manage them from Argo CD). Annotate them `argo-rollouts.argoproj.io/managed-by-rollouts`.
- **Istio VirtualService weights flap** — the Rollout controller rewrites `.spec.http[].route[].weight` during an update; Argo CD sees the drift and snaps it back. **Fix:** add `ignoreDifferences` for `VirtualService` weights:

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

Full GitOps patterns: `gitops-argocd.md`.

---

## 10. Rollout never finishes / behaves like a plain Deployment on first deploy

**Cause (expected):** On *initial* creation the controller skips the strategy and scales the first ReplicaSet as fast as possible. If it looks "done" instantly, that's correct — strategy only applies from the second revision on. Trigger a real `spec.template` update (e.g. `kubectl argo rollouts set image …`) to exercise the strategy.

**If truly stuck at first deploy:** check pod readiness, image pull, probes, quotas — same as a Deployment.

---

## 11. `undo` / rollback doesn't go fast

**Cause:** Fast rollback only works while the old ReplicaSet is still scaled up (within `scaleDownDelaySeconds` and within `rollbackWindow.revisions` if set). Once scaled down, `undo` re-deploys that revision through the normal strategy from step 0.

**Fix:** Increase `scaleDownDelaySeconds` or set `rollbackWindow.revisions: N` to keep recent ReplicaSets hot for fast reverts. Don't set `revisionHistoryLimit: 0` if you care about undo.

---

## 12. Scaledown of old ReplicaSet happens too fast / too slow / never

- Default `scaleDownDelaySeconds` is 30s (canary traffic-routing and blue-green). Below 30 risks iptables propagation drops.
- `scaleDownDelayRevisionLimit` caps how many old ReplicaSets stay scaled up awaiting the delay.
- Aborted rollouts use `abortScaleDownDelaySeconds` (default 30, `0` = keep canary alive for inspection).
- For router canaries, `scaleDownDelaySeconds` is honored; for basic (no-router) canaries it's ignored (pod count *is* the traffic signal).

---

## Diagnostic one-liners

```bash
# Full rollout state
kubectl argo rollouts get rollout NAME -o yaml

# All ReplicaSets the controller knows about + their hashes/counts
kubectl get rs -n NS -o wide | grep NAME

# Active analysis runs for a rollout
kubectl get analysisrun -n NS -o wide

# Controller logs filtered to your rollout
kubectl logs -n argo-rollouts deploy/argo-rollouts --tail=300 | grep NAME

# Recent events
kubectl get events -n NS --sort-by=.lastTimestamp | tail -50
```
