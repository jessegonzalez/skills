"""Tests for ``rollout_lib.validate_rollout`` / ``validate_analysis`` and the
``validate.py`` CLI.

Each test injects one violation into an otherwise-valid manifest and asserts
the validator catches it. The CLI smoke test writes temp YAML files and runs
the script via ``subprocess``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from rollout_lib import (
    build_analysis_template,
    build_rollout,
    emit_yaml,
    validate_analysis,
    validate_rollout,
)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
VALIDATE_PY = SCRIPTS_DIR / "validate.py"


# ---------------------------------------------------------------------------
# A known-good rollout
# ---------------------------------------------------------------------------


def test_known_good_rollout_is_valid():
    doc = build_rollout(name="app", image="img")
    assert validate_rollout(doc) == []


def test_known_good_rollout_with_traffic_routing_is_valid():
    doc = build_rollout(
        name="app",
        image="img",
        traffic_routing="istio",
        stable_service="s",
        canary_service="c",
        virtual_service="vs",
        routes="primary",
    )
    assert validate_rollout(doc) == []


# ---------------------------------------------------------------------------
# Each injected violation
# ---------------------------------------------------------------------------


def _base_rollout():
    return build_rollout(name="app", image="img")


def test_violation_wrong_api_version():
    doc = _base_rollout()
    doc["apiVersion"] = "apps/v1"
    errs = validate_rollout(doc)
    assert any("apiVersion" in e for e in errs), errs


def test_violation_wrong_kind():
    doc = _base_rollout()
    doc["kind"] = "Deployment"
    errs = validate_rollout(doc)
    assert any("kind" in e for e in errs), errs


def test_violation_both_strategies():
    doc = _base_rollout()
    doc["spec"]["strategy"]["blueGreen"] = {"activeService": "x"}
    errs = validate_rollout(doc)
    assert any("strategy" in e for e in errs), errs


def test_violation_no_strategy():
    doc = _base_rollout()
    doc["spec"]["strategy"] = {}
    errs = validate_rollout(doc)
    assert any("strategy" in e for e in errs), errs


def test_violation_bluegreen_lowercase_key():
    doc = _base_rollout()
    doc["spec"]["strategy"] = {"bluegreen": {"activeService": "a"}}
    errs = validate_rollout(doc)
    assert any("blueGreen" in e for e in errs), errs


def test_violation_selector_template_label_mismatch():
    doc = _base_rollout()
    doc["spec"]["template"]["metadata"]["labels"]["app"] = "different"
    errs = validate_rollout(doc)
    assert any("matchLabels" in e for e in errs), errs


def test_violation_traffic_routing_without_canary_service():
    doc = _base_rollout()
    doc["spec"]["strategy"]["canary"]["trafficRouting"] = {"istio": {}}
    doc["spec"]["strategy"]["canary"]["stableService"] = "s"
    # canaryService deliberately absent
    errs = validate_rollout(doc)
    assert any("canaryService" in e for e in errs), errs


def test_violation_traffic_routing_without_stable_service():
    doc = _base_rollout()
    doc["spec"]["strategy"]["canary"]["trafficRouting"] = {"istio": {}}
    doc["spec"]["strategy"]["canary"]["canaryService"] = "c"
    errs = validate_rollout(doc)
    assert any("stableService" in e for e in errs), errs


def test_violation_bluegreen_without_active_service():
    doc = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Rollout",
        "metadata": {"name": "app"},
        "spec": {
            "selector": {"matchLabels": {"app": "app"}},
            "template": {
                "metadata": {"labels": {"app": "app"}},
                "spec": {"containers": []},
            },
            "strategy": {"blueGreen": {}},
        },
    }
    errs = validate_rollout(doc)
    assert any("activeService" in e for e in errs), errs


def test_violation_max_surge_and_unavailable_both_zero_string():
    doc = _base_rollout()
    doc["spec"]["strategy"]["canary"]["maxSurge"] = "0"
    doc["spec"]["strategy"]["canary"]["maxUnavailable"] = "0"
    errs = validate_rollout(doc)
    assert any("maxSurge" in e or "maxUnavailable" in e for e in errs), errs


def test_violation_max_surge_and_unavailable_both_zero_int():
    doc = _base_rollout()
    doc["spec"]["strategy"]["canary"]["maxSurge"] = 0
    doc["spec"]["strategy"]["canary"]["maxUnavailable"] = 0
    errs = validate_rollout(doc)
    assert any("maxSurge" in e or "maxUnavailable" in e for e in errs), errs


def test_violation_analysis_template_without_template_name():
    doc = _base_rollout()
    doc["spec"]["strategy"]["canary"]["analysis"] = {
        "templates": [{"foo": "bar"}],
    }
    errs = validate_rollout(doc)
    assert any("templateName" in e for e in errs), errs


def test_violation_step_with_two_keys():
    doc = _base_rollout()
    doc["spec"]["strategy"]["canary"]["steps"] = [
        {"setWeight": 20, "pause": {"duration": "5m"}},
    ]
    errs = validate_rollout(doc)
    assert any("steps[0]" in e for e in errs), errs


def test_violation_step_with_unknown_key():
    doc = _base_rollout()
    doc["spec"]["strategy"]["canary"]["steps"] = [{"bogusKey": 1}]
    errs = validate_rollout(doc)
    assert any("steps[0]" in e for e in errs), errs


def test_valid_step_keys_pass():
    """Sanity: each known step key alone is accepted."""
    doc = _base_rollout()
    doc["spec"]["strategy"]["canary"]["steps"] = [
        {"setWeight": 20},
        {"pause": {"duration": "5m"}},
        {"pause": {}},
        {"setCanaryScale": {"weight": 10}},
    ]
    errs = validate_rollout(doc)
    # only fail if a step-related error shows up
    assert not any("steps[" in e for e in errs), errs


# ---------------------------------------------------------------------------
# AnalysisTemplate validation
# ---------------------------------------------------------------------------


def test_known_good_analysis_is_valid():
    doc = build_analysis_template(
        name="s",
        provider="prometheus",
        address="http://x",
        query="up",
    )
    assert validate_analysis(doc) == []


def test_analysis_no_metrics():
    doc = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AnalysisTemplate",
        "metadata": {"name": "s"},
        "spec": {},
    }
    errs = validate_analysis(doc)
    assert any("metrics" in e for e in errs), errs


def test_analysis_metric_missing_name():
    doc = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AnalysisTemplate",
        "metadata": {"name": "s"},
        "spec": {"metrics": [{"provider": {"prometheus": {}}}]},
    }
    errs = validate_analysis(doc)
    assert any("name" in e for e in errs), errs


def test_analysis_metric_missing_provider():
    doc = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AnalysisTemplate",
        "metadata": {"name": "s"},
        "spec": {"metrics": [{"name": "m"}]},
    }
    errs = validate_analysis(doc)
    assert any("provider" in e for e in errs), errs


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


def _write(path: Path, doc: dict) -> None:
    path.write_text(emit_yaml(doc))


def test_cli_returns_zero_for_valid_file(tmp_path):
    good = tmp_path / "good.yaml"
    _write(good, build_rollout(name="app", image="img"))
    result = subprocess.run(
        [sys.executable, str(VALIDATE_PY), str(good)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_cli_returns_one_for_invalid_file(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad_doc = build_rollout(name="app", image="img")
    bad_doc["apiVersion"] = "apps/v1"
    _write(bad, bad_doc)
    result = subprocess.run(
        [sys.executable, str(VALIDATE_PY), str(bad)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "apiVersion" in result.stderr


def test_cli_returns_one_for_missing_file(tmp_path):
    missing = tmp_path / "nope.yaml"
    result = subprocess.run(
        [sys.executable, str(VALIDATE_PY), str(missing)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "nope.yaml" in result.stderr


def test_cli_handles_multiple_files_mixed(tmp_path):
    good = tmp_path / "good.yaml"
    bad = tmp_path / "bad.yaml"
    _write(good, build_rollout(name="app", image="img"))
    bad_doc = build_rollout(name="app", image="img")
    del bad_doc["spec"]["strategy"]
    _write(bad, bad_doc)
    result = subprocess.run(
        [sys.executable, str(VALIDATE_PY), str(good), str(bad)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "strategy" in result.stderr
