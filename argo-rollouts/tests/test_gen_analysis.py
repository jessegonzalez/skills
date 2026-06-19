"""Tests for ``rollout_lib.build_analysis_template``.

Cover the contract from SKILL.md: Prometheus build with defaults,
typed optional fields (consecutiveSuccessLimit/interval/count), arg parsing,
and the Datadog provider shape.
"""

from __future__ import annotations

import pytest

from rollout_lib import build_analysis_template


# ---------------------------------------------------------------------------
# Prometheus provider
# ---------------------------------------------------------------------------


def test_prometheus_minimal():
    doc = build_analysis_template(
        name="success-rate",
        provider="prometheus",
        address="http://prometheus:9090",
        query="up",
        success="result[0] >= 0.95",
    )

    assert doc["apiVersion"] == "argoproj.io/v1alpha1"
    assert doc["kind"] == "AnalysisTemplate"
    assert doc["metadata"]["name"] == "success-rate"

    metric = doc["spec"]["metrics"][0]
    assert metric["name"] == "success-rate"
    assert metric["successCondition"] == "result[0] >= 0.95"
    # default failureLimit / consecutiveSuccessLimit are emitted at 0
    assert metric["failureLimit"] == 0
    assert metric["consecutiveSuccessLimit"] == 0

    prom = metric["provider"]["prometheus"]
    assert prom["address"] == "http://prometheus:9090"
    assert prom["query"] == "up"


def test_prometheus_requires_address():
    with pytest.raises(ValueError, match="address"):
        build_analysis_template(
            name="s", provider="prometheus", query="up"
        )


def test_prometheus_requires_query():
    with pytest.raises(ValueError, match="query"):
        build_analysis_template(
            name="s", provider="prometheus", address="http://x"
        )


# ---------------------------------------------------------------------------
# Optional fields + types
# ---------------------------------------------------------------------------


def test_consecutive_success_limit_interval_count():
    doc = build_analysis_template(
        name="s",
        provider="prometheus",
        address="http://x",
        query="up",
        consecutive_success_limit=3,
        interval="5m",
        count=10,
    )
    m = doc["spec"]["metrics"][0]
    assert m["consecutiveSuccessLimit"] == 3
    assert m["interval"] == "5m"
    assert m["count"] == 10
    # types must be ints where the spec says int
    assert isinstance(m["consecutiveSuccessLimit"], int)
    assert isinstance(m["count"], int)
    assert isinstance(m["interval"], str)


def test_failure_condition_emitted_when_set():
    doc = build_analysis_template(
        name="s",
        provider="prometheus",
        address="http://x",
        query="up",
        failure="result[0] < 0.5",
        failure_limit=5,
    )
    m = doc["spec"]["metrics"][0]
    assert m["failureCondition"] == "result[0] < 0.5"
    assert m["failureLimit"] == 5


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


def test_args_list_of_tuples():
    doc = build_analysis_template(
        name="s",
        provider="prometheus",
        address="http://x",
        query="up",
        args=[("service-name", "guestbook"), ("latency-ms", "100")],
    )
    assert doc["spec"]["args"] == [
        {"name": "service-name", "value": "guestbook"},
        {"name": "latency-ms", "value": "100"},
    ]


def test_args_dict():
    doc = build_analysis_template(
        name="s",
        provider="prometheus",
        address="http://x",
        query="up",
        args={"service-name": "guestbook"},
    )
    assert doc["spec"]["args"] == [
        {"name": "service-name", "value": "guestbook"},
    ]


def test_no_args_omits_field():
    doc = build_analysis_template(
        name="s", provider="prometheus", address="http://x", query="up"
    )
    assert "args" not in doc["spec"]


# ---------------------------------------------------------------------------
# Datadog provider
# ---------------------------------------------------------------------------


def test_datadog_build():
    doc = build_analysis_template(
        name="dd",
        provider="datadog",
        query="avg:system.cpu.user{*}",
    )
    dd = doc["spec"]["metrics"][0]["provider"]["datadog"]
    assert dd["apiVersion"] == "v1"
    assert dd["query"] == "avg:system.cpu.user{*}"


def test_datadog_requires_query():
    with pytest.raises(ValueError, match="query"):
        build_analysis_template(name="dd", provider="datadog")


# ---------------------------------------------------------------------------
# Other providers (best-effort)
# ---------------------------------------------------------------------------


def test_other_provider_best_effort():
    doc = build_analysis_template(
        name="w", provider="wavefront", query="ts(...)"
    )
    assert doc["spec"]["metrics"][0]["provider"] == {
        "wavefront": {"query": "ts(...)"}
    }


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        build_analysis_template(name="x", provider="bogus", query="q")
