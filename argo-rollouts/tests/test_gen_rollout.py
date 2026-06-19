"""Tests for ``rollout_lib.build_rollout`` and ``parse_steps``.

These cover the contract from SKILL.md: minimal canary, step parsing, traffic
routing, background analysis, blue-green (with and without manual gate), the
documented error cases, and YAML idempotency.
"""

from __future__ import annotations

import yaml

import pytest

from rollout_lib import build_rollout, emit_yaml, parse_steps


# ---------------------------------------------------------------------------
# Canary minimal
# ---------------------------------------------------------------------------


def test_canary_minimal():
    """A bare canary rollout has the required shape and matching labels."""
    doc = build_rollout(name="app", image="img", strategy="canary")

    assert doc["apiVersion"] == "argoproj.io/v1alpha1"
    assert doc["kind"] == "Rollout"

    # selector labels MUST equal template labels (hard k8s rule)
    selector_labels = doc["spec"]["selector"]["matchLabels"]
    template_labels = doc["spec"]["template"]["metadata"]["labels"]
    assert selector_labels == template_labels == {"app": "app"}

    # exactly one strategy, only canary, no traffic routing
    strategy = doc["spec"]["strategy"]
    assert "canary" in strategy
    assert "blueGreen" not in strategy
    assert "trafficRouting" not in strategy["canary"]

    # container shape
    container = doc["spec"]["template"]["spec"]["containers"][0]
    assert container["name"] == "app"
    assert container["image"] == "img"
    assert container["ports"] == [{"containerPort": 8080}]

    # replicas + metadata labels defaults
    assert doc["spec"]["replicas"] == 1
    assert doc["metadata"]["labels"] == {"app": "app"}


# ---------------------------------------------------------------------------
# Step parsing
# ---------------------------------------------------------------------------


def test_parse_steps_alternating():
    """'20 5m,40 5m' expands to four alternating setWeight/pause items."""
    steps = parse_steps("20 5m,40 5m")
    assert steps == [
        {"setWeight": 20},
        {"pause": {"duration": "5m"}},
        {"setWeight": 40},
        {"pause": {"duration": "5m"}},
    ]
    # types must be int weight + str duration
    assert isinstance(steps[0]["setWeight"], int)
    assert isinstance(steps[1]["pause"]["duration"], str)


def test_parse_steps_weight_only_and_duration_only():
    """Weight-only and duration-only chunks are supported."""
    assert parse_steps("20") == [{"setWeight": 20}]
    assert parse_steps("5m") == [{"pause": {"duration": "5m"}}]


def test_parse_steps_rejects_bad_chunk():
    with pytest.raises(ValueError):
        parse_steps("20 5m extra")


# ---------------------------------------------------------------------------
# Canary + Istio traffic routing
# ---------------------------------------------------------------------------


def test_canary_with_istio_traffic_routing():
    doc = build_rollout(
        name="guestbook",
        image="guestbook:v2",
        strategy="canary",
        traffic_routing="istio",
        stable_service="guestbook-stable",
        canary_service="guestbook-canary",
        virtual_service="guestbook-vsvc",
        routes="primary",
    )
    canary = doc["spec"]["strategy"]["canary"]
    assert canary["canaryService"] == "guestbook-canary"
    assert canary["stableService"] == "guestbook-stable"
    istio = canary["trafficRouting"]["istio"]
    assert istio["virtualService"]["name"] == "guestbook-vsvc"
    assert istio["virtualService"]["routes"] == ["primary"]


def test_canary_routes_parses_comma_list():
    doc = build_rollout(
        name="app",
        image="img",
        traffic_routing="istio",
        stable_service="s",
        canary_service="c",
        virtual_service="vs",
        routes="r1, r2 ,r3",
    )
    routes = doc["spec"]["strategy"]["canary"]["trafficRouting"]["istio"][
        "virtualService"
    ]["routes"]
    assert routes == ["r1", "r2", "r3"]


# ---------------------------------------------------------------------------
# Background analysis
# ---------------------------------------------------------------------------


def test_canary_with_background_analysis():
    doc = build_rollout(
        name="app",
        image="img",
        strategy="canary",
        analysis_template="success-rate",
        starting_step=2,
    )
    analysis = doc["spec"]["strategy"]["canary"]["analysis"]
    assert analysis["templates"][0]["templateName"] == "success-rate"
    assert isinstance(analysis["startingStep"], int)
    assert analysis["startingStep"] == 2
    assert analysis["args"] == []


def test_canary_analysis_without_starting_step_omits_field():
    doc = build_rollout(
        name="app", image="img", analysis_template="success-rate"
    )
    analysis = doc["spec"]["strategy"]["canary"]["analysis"]
    assert "startingStep" not in analysis


# ---------------------------------------------------------------------------
# Blue-green
# ---------------------------------------------------------------------------


def test_bluegreen_minimal():
    doc = build_rollout(
        name="my-app",
        image="my-app:v1",
        strategy="bluegreen",
        active_service="my-app-active",
    )
    bg = doc["spec"]["strategy"]["blueGreen"]
    assert bg["activeService"] == "my-app-active"
    assert bg["scaleDownDelaySeconds"] == 30
    # autoPromotionEnabled defaults to controller default (true) - omitted
    assert "autoPromotionEnabled" not in bg


def test_bluegreen_manual_gate_and_preview():
    doc = build_rollout(
        name="my-app",
        image="my-app:v1",
        strategy="bluegreen",
        active_service="my-app-active",
        preview_service="my-app-preview",
        manual_gate=True,
    )
    bg = doc["spec"]["strategy"]["blueGreen"]
    assert bg["previewService"] == "my-app-preview"
    assert bg["autoPromotionEnabled"] is False


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_error_istio_without_stable_service():
    with pytest.raises(ValueError, match="stable-service"):
        build_rollout(
            name="app",
            image="img",
            traffic_routing="istio",
            canary_service="c",
            virtual_service="vs",
        )


def test_error_istio_without_canary_service():
    with pytest.raises(ValueError, match="canary-service"):
        build_rollout(
            name="app",
            image="img",
            traffic_routing="istio",
            stable_service="s",
            virtual_service="vs",
        )


def test_error_bluegreen_without_active_service():
    with pytest.raises(ValueError, match="active-service"):
        build_rollout(name="app", image="img", strategy="bluegreen")


def test_error_both_max_zero():
    with pytest.raises(ValueError, match="0"):
        build_rollout(
            name="app",
            image="img",
            max_surge="0",
            max_unavailable="0",
        )


def test_error_invalid_strategy():
    with pytest.raises(ValueError):
        build_rollout(name="app", image="img", strategy="rolling")


def test_error_traffic_routing_on_bluegreen():
    with pytest.raises(ValueError):
        build_rollout(
            name="app",
            image="img",
            strategy="bluegreen",
            active_service="a",
            traffic_routing="istio",
            stable_service="s",
            canary_service="c",
            virtual_service="vs",
        )


# ---------------------------------------------------------------------------
# Idempotent YAML
# ---------------------------------------------------------------------------


def test_emit_yaml_roundtrip():
    """emit_yaml(build_rollout(...)) parses back to the same dict."""
    doc = build_rollout(
        name="app",
        image="img",
        strategy="canary",
        steps="20 5m,40 5m",
    )
    parsed = yaml.safe_load(emit_yaml(doc))
    assert parsed == doc


def test_emit_yaml_roundtrip_bluegreen():
    doc = build_rollout(
        name="app",
        image="img",
        strategy="bluegreen",
        active_service="a",
        preview_service="p",
        manual_gate=True,
    )
    parsed = yaml.safe_load(emit_yaml(doc))
    assert parsed == doc
