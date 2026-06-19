#!/usr/bin/env python3
"""Argo Rollouts skill eval runner + grader (JSON, isolated per-run dirs).

Each run executes in its OWN fresh temp dir (with the right opencode.json written
into it) so leftover files from one prompt can't contaminate another. Pass prompt
ids as argv to rerun just those (both configs); otherwise runs all. Always
regrades every JSONL in out/ and rewrites benchmark.{json,md}.
"""
from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVALS = ROOT / "evals.json"
SKILL_PATH = str(Path(__file__).resolve().parent.parent)  # the skill dir
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

OPENCODE = shutil.which("opencode") or "opencode"
PER_RUN_TIMEOUT = 400   # raised so the ALB ping-pong prompt doesn't time out
MAX_WORKERS = 6

WITH_CFG = {"$schema": "https://opencode.ai/config.json",
            "skills": {"paths": [SKILL_PATH]}}
BASE_CFG = {"$schema": "https://opencode.ai/config.json"}


def run_one(pid: str, cfg: str, prompt: str):
    outfile = OUT / f"{pid}-{cfg}.jsonl"
    run_dir = Path(tempfile.mkdtemp(prefix=f"eval-{pid}-{cfg}-"))
    (run_dir / "opencode.json").write_text(json.dumps(WITH_CFG if cfg == "with" else BASE_CFG))
    t0 = time.time()
    try:
        proc = subprocess.run(
            [OPENCODE, "run", "--dir", str(run_dir), "--format", "json",
             "--dangerously-skip-permissions", prompt],
            capture_output=True, text=True, timeout=PER_RUN_TIMEOUT,
        )
        rc, blob = proc.returncode, proc.stdout
        if rc != 0:
            blob += "\n--STDERR--\n" + proc.stderr
    except subprocess.TimeoutExpired:
        rc, blob = -1, ""
    except Exception as exc:  # noqa: BLE001
        rc, blob = -2, f"[ERROR {exc}]"
    dur = time.time() - t0
    outfile.write_text(blob)
    shutil.rmtree(run_dir, ignore_errors=True)
    print(f"  done {pid}-{cfg} rc={rc} {dur:.0f}s", file=sys.stderr)
    return pid, cfg


def parse(jsonl: str) -> dict:
    triggered = used_script = False
    chunks: list[str] = []
    tokens = 0
    for line in jsonl.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        part = ev.get("part") or {}
        if t == "tool_use":
            tool = part.get("tool")
            state = part.get("state") or {}
            inp = state.get("input") or {}
            if tool == "skill" and inp.get("name") == "argo-rollouts":
                triggered = True
            elif tool == "bash":
                cmd = inp.get("command", "") or ""
                if any(s in cmd for s in ("gen_rollout.py", "gen_analysis.py", "validate.py")):
                    used_script = True
            out = state.get("output")
            if isinstance(out, str):
                chunks.append(out)
        elif t == "text":
            chunks.append(part.get("text", "") or "")
        elif t == "step_finish":
            tokens += (part.get("tokens") or {}).get("total", 0)
    return {"triggered": triggered, "used_script": used_script,
            "text": "\n".join(chunks), "tokens": tokens}


def eval_check(text: str, check: dict) -> bool:
    if "has" in check:
        return check["has"] in text
    if "lacks" in check:
        return check["lacks"] not in text
    if "any" in check:
        return any(a in text for a in check["any"])
    return False


def grade_and_write(prompts):
    def read(pid, cfg):
        f = OUT / f"{pid}-{cfg}.jsonl"
        return parse(f.read_text()) if f.exists() else {"triggered": False, "used_script": False, "text": "", "tokens": 0}

    rows, with_toks, base_toks = [], [], []
    n_trig_ok = q_wp = q_wt = q_bp = q_bt = over = wfab = bfab = scripts = 0
    for p in prompts:
        pid = p["id"]
        w, b = read(pid, "with"), read(pid, "base")
        tok_ok = (w["triggered"] == p["trigger"])
        n_trig_ok += tok_ok
        if not p["trigger"] and w["triggered"]:
            over += 1
        wc = all(eval_check(w["text"], c) for c in p["checks"])
        bc = all(eval_check(b["text"], c) for c in p["checks"])
        if p["trigger"]:
            q_wt += 1
            q_wp += wc
            q_bt += 1
            q_bp += bc
            scripts += w["used_script"]
        else:
            wfab += "argoproj.io/v1alpha1" in w["text"]
            bfab += "argoproj.io/v1alpha1" in b["text"]
        with_toks.append(w["tokens"])
        base_toks.append(b["tokens"])
        rows.append({"id": pid, "category": p["category"], "expect": p["trigger"],
                     "trig_with": w["triggered"], "script": w["used_script"],
                     "qual_with": wc, "qual_base": bc,
                     "tok_with": w["tokens"], "tok_base": b["tokens"]})

    n = len(prompts)
    ntr = sum(1 for p in prompts if p["trigger"])
    nnt = n - ntr
    mw = statistics.mean(with_toks) if with_toks else 0
    mb = statistics.mean(base_toks) if base_toks else 0

    def pct(a: int, b: int) -> str:
        return f"{a}/{b} ({a/b:.0%})" if b else "n/a"
    bench = {
        "runs_cached": n * 2, "trigger_accuracy_with": pct(n_trig_ok, n),
        "over_trigger_near_miss": pct(over, nnt),
        "quality_with_skill": pct(q_wp, q_wt), "quality_baseline": pct(q_bp, q_bt),
        "quality_delta": f"+{q_wp/max(q_wt,1)-q_bp/max(q_bt,1):.0%}",
        "script_used_on_trigger_prompts": pct(scripts, ntr),
        "fabrication_with_skill": pct(wfab, nnt), "fabrication_baseline": pct(bfab, nnt),
        "mean_tokens_with_skill": int(mw), "mean_tokens_baseline": int(mb),
        "token_overhead": f"+{int(mw-mb)} ({(mw/max(mb,1))-1:+.0%})", "rows": rows,
    }
    (ROOT / "benchmark.json").write_text(json.dumps(bench, indent=2))
    md = ["# Path B — Skill Eval Benchmark (glm-5.2, opencode run --format json)", "",
          "| Metric | Result |", "|---|---|",
          f"| Runs (with + baseline) | {bench['runs_cached']} |",
          f"| Trigger accuracy (with-skill) | {bench['trigger_accuracy_with']} |",
          f"| Over-trigger on near-misses | {bench['over_trigger_near_miss']} |",
          f"| Quality pass — with skill | {bench['quality_with_skill']} |",
          f"| Quality pass — baseline | {bench['quality_baseline']} |",
          f"| Quality delta (skill uplift) | {bench['quality_delta']} |",
          f"| Bundled scripts used (trigger prompts) | {bench['script_used_on_trigger_prompts']} |",
          f"| Near-miss argoproj mentions — with skill | {bench['fabrication_with_skill']} |",
          f"| Near-miss argoproj mentions — baseline | {bench['fabrication_baseline']} |",
          f"| Mean tokens — with skill | {bench['mean_tokens_with_skill']:,} |",
          f"| Mean tokens — baseline | {bench['mean_tokens_baseline']:,} |",
          f"| Token overhead | {bench['token_overhead']} |",
          "", "## Per-prompt", "",
          "| id | category | expect | trig_with | script | qual_with | qual_base | tok_with | tok_base |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['id']} | {r['category']} | {r['expect']} | {'Y' if r['trig_with'] else 'N'} | "
                  f"{'Y' if r['script'] else '-'} | {'PASS' if r['qual_with'] else 'FAIL'} | "
                  f"{'PASS' if r['qual_base'] else 'FAIL'} | {r['tok_with']:,} | {r['tok_base']:,} |")
    (ROOT / "benchmark.md").write_text("\n".join(md))
    print("Wrote benchmark.json and benchmark.md", file=sys.stderr)


def main() -> int:
    data = json.loads(EVALS.read_text())
    prompts = data["prompts"]
    only = set(sys.argv[1:])
    if only:
        to_run = [p for p in prompts if p["id"] in only]
        print(f"Rerunning {len(to_run)} ids x 2 configs in isolated dirs "
              f"(timeout={PER_RUN_TIMEOUT}s)", file=sys.stderr)
        jobs = [(p["id"], c, p["prompt"]) for p in to_run for c in ("with", "base")]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = [ex.submit(run_one, *j) for j in jobs]
            for fut in as_completed(futs):
                fut.result()
    else:
        print(f"Running ALL {len(prompts)} prompts x 2 configs in isolated dirs", file=sys.stderr)
        jobs = [(p["id"], c, p["prompt"]) for p in prompts for c in ("with", "base")]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = [ex.submit(run_one, *j) for j in jobs]
            for fut in as_completed(futs):
                fut.result()
    grade_and_write(prompts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
