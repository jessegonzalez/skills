# Notifications (Slack / Teams / Webhook / Email)

Argo Rollouts notifications (v1.1+) are powered by the argoproj notifications-engine. Administrators configure triggers + templates + a notification service in a ConfigMap; **end users just annotate their Rollout** to subscribe.

For related patterns, see `gitops-argocd.md` (notifications are the supported integration point for triggering CI on lifecycle events). For command-line control, see `kubectl-plugin.md`.

## Two layers

1. **Controller-side config** (admin): `argo-rollouts-notification-configmap` + `argo-rollouts-notification-secret` in the controller's namespace define the services (Slack/Teams/email/webhook), templates, and triggers.
2. **Per-Rollout subscription** (user): an annotation on the Rollout picks a trigger + service + recipient.

Quickstart — apply `notifications-install.yaml` for built-in templates/triggers, then add your service creds:

```bash
kubectl apply -n argo-rollouts -f https://github.com/argoproj/argo-rollouts/releases/latest/download/notifications-install.yaml
```

## Configure a service (Slack example)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argo-rollouts-notification-configmap
  namespace: argo-rollouts
data:
  service.slack: |
    token: $slack-token
---
apiVersion: v1
kind: Secret
metadata:
  name: argo-rollouts-notification-secret
  namespace: argo-rollouts
stringData:
  slack-token: <xoxb-...>          # bot OAuth token
```

For MS Teams, email, generic webhook, etc. use the corresponding `service.<name>:` block. See the official notification-services docs.

## Built-in triggers

Ship with `notifications-install.yaml`:

- `on-rollout-completed` — all steps done, fully promoted.
- `on-rollout-aborted` — aborted before completion (often your on-call trigger).
- `on-rollout-paused` — paused (manual gate hit).
- `on-rollout-step-completed` — each step finished.
- `on-rollout-updated` — manifest changed.
- `on-analysis-run-error` / `on-analysis-run-failed` / `on-analysis-run-running`.
- `on-scaling-replica-set` — replica count changed.

## Subscribe a Rollout (the user step)

Annotate the Rollout:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: my-app
  annotations:
    notifications.argoproj.io/subscribe.on-rollout-completed.slack: releases;ops-team
    notifications.argoproj.io/subscribe.on-rollout-aborted.slack: ops-team;oncall
```

Annotation key format:

```
notifications.argoproj.io/subscribe.<TRIGGER>.<SERVICE>: <recipients>
```

- `<TRIGGER>` — e.g. `on-rollout-aborted`.
- `<SERVICE>` — e.g. `slack`.
- `<recipients>` — semicolon-separated list (Slack channels, email addresses, etc., depending on the service).

Multiple triggers → multiple annotations.

## Self-service (per-namespace) notifications (v1.6+)

By default only the controller-namespace config is used. To let end-users configure their own notifications in their own Rollout namespace:

1. Run the controller with `--self-service-notification-enabled`.
2. Users create their own `argo-rollouts-notification-configmap` (+ optional secret) in their Rollout's namespace.
3. The controller merges controller-level + namespace-level config.

## Custom templates & triggers (admin)

Templates use Go `html/template` with `.rollout` and `.recipient` in scope:

```yaml
data:
  template.my-purple-template: |
    message: |
      Rollout {{.rollout.metadata.name}} changed
    slack:
      attachments: |
        [{"title": "{{.rollout.metadata.name}}", "color": "#800080"}]
```

Custom triggers use [expr-lang](https://github.com/expr-lang/expr) predicates:

```yaml
data:
  trigger.on-purple: |
    - send: [my-purple-template]
      when: rollout.spec.template.spec.containers[0].image == 'my-app:purple'
```

## Validate / test notifications from the CLI

```bash
# List configured triggers/templates
kubectl argo rollouts notifications trigger get
kubectl argo rollouts notifications template get

# Manually fire a trigger against a Rollout (great for testing)
kubectl argo rollouts notifications trigger run my-app on-rollout-completed

# Send a test render of a template to a service/recipient
kubectl argo rollouts notifications template notify slack my-channel my-purple-template
```

## Notification metrics (Prometheus, controller)

- `notification_send_success` (counter)
- `notification_send_error` (counter)
- `notification_send` (histogram, latency)

Useful SLOs: alert if `notification_send_error` rate climbs (broken token, rate limits, wrong channel).

## Troubleshooting

- **No notifications fire:** check the annotation key spelling — trigger name must exactly match a configured trigger; service name must match the `service.<name>:` key. Verify the secret token is valid.
- **Wrong/old data in the message:** the template renders from the Rollout object at fire time; make sure your template references current fields.
- **Controller doesn't see your ConfigMap:** for self-service mode confirm `--self-service-notification-enabled` is set and the ConfigMap name is exactly `argo-rollouts-notification-configmap` in the Rollout's namespace.
