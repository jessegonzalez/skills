# Argo Rollouts skill — evals

Reproducible evaluation harness for the skill, measuring **triggering accuracy**,
**output quality**, and **token cost** vs a no-skill baseline.

## Methodology

Each prompt runs twice via `opencode run --format json`, each in its own isolated
temp directory (so leftover files can't contaminate later runs):

- **with-skill** — an `opencode.json` that registers this skill via `skills.paths`.
- **baseline** — the same prompt with no skill registered.

The JSONL event stream is parsed to grade:

- **Triggering** — a `tool_use` event with `tool == "skill"` and
  `input.name == "argo-rollouts"`. The skill should trigger on the 10
  Argo-Rollouts prompts and stay quiet on the 6 near-misses.
- **Quality** — grep checks over the assistant text + tool outputs
  (`has` / `lacks` / `any`).
- **Fidelity** — whether the agent used the bundled `gen_*.py` / `validate.py`.
- **Cost** — total tokens summed from `step_finish` events.

## Run it

```bash
uv run --with pytest --with pyyaml python -m pytest tests/ -q   # scripts work first
# Then the eval (uses `opencode` on PATH; each run is a real agent call):
python3 evals/run_eval.py                       # run all 16 prompts x 2 configs
python3 evals/run_eval.py p03 p11 p12           # rerun a subset
```

Outputs `out/*.jsonl` (raw transcripts), `benchmark.json`, and `benchmark.md`.

## Latest result — `benchmark-glm-5.2.md`

Headline (glm-5.2, 16 prompts x 2 configs = 32 runs):

| Metric | Result |
|---|---|
| Trigger accuracy | 16/16 (100%) |
| Over-trigger on near-misses | 0/6 (0%) |
| Quality pass — with skill | 10/10 (100%) |
| Quality pass — baseline | 9/10 (90%) |
| Quality delta | +10% |
| Bundled scripts used on generation tasks | 5/5 (100%) |
| Token overhead | +41% |

The skill is well-calibrated: no description changes were needed after this run.
The +41% token overhead is the cost of the script-read → run → validate → explain
loop on generation prompts; p02 (bluegreen) and p03 (ALB ping-pong) are the outliers.

## Notes

- The eval calls the model for real, so it costs tokens and is mildly non-
  deterministic across runs. Treat the benchmark as a snapshot, not a golden file.
- Near-miss prompts must run in isolated dirs — a shared working dir lets earlier
  YAML outputs leak into later transcripts and corrupt the over-trigger metric.
