# Security policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for suspected security problems.

Email the maintainer directly at `security@<your-domain>` with:

1. A description of the issue and its impact.
2. Reproduction steps (or a proof-of-concept).
3. Any known mitigations.

You should receive an acknowledgement within **5 business days**. If a
vulnerability is confirmed we will open a GitHub Security Advisory, coordinate
a fix on a private branch, and credit the reporter in the release notes unless
they prefer to remain anonymous.

## Scope

This repository distributes an *agent Skill* — Python helper scripts that
**generate and validate Kubernetes YAML** for Argo Rollouts. The scripts:

- run locally on the user's machine (or in CI) under the user's credentials,
- do **not** talk to the network (no telemetry, no upstream calls),
- do **not** execute the manifests they produce (applying them is the user's
  responsibility, typically via `kubectl` or Argo CD).

A "vulnerability" therefore means something like: a script that produces
manifests which are unsafe by construction (e.g. always sets
`privileged: true`, or mangles a Secret in a way that leaks it), or a way to
make `validate.py` report "valid" for a manifest that is structurally broken.

Issues in the upstream **Argo Rollouts controller** itself should be reported
to the upstream project — see
<https://github.com/argoproj/argo-rollouts/security/policy>.

## Supported versions

Only the latest release line receives security fixes.

| Version | Supported |
|---------|-----------|
| 1.x     | ✅        |
| < 1.0   | ❌        |
