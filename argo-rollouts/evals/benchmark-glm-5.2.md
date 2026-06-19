# Path B — Skill Eval Benchmark (glm-5.2, opencode run --format json)

| Metric | Result |
|---|---|
| Runs (with + baseline) | 32 |
| Trigger accuracy (with-skill) | 16/16 (100%) |
| Over-trigger on near-misses | 0/6 (0%) |
| Quality pass — with skill | 10/10 (100%) |
| Quality pass — baseline | 9/10 (90%) |
| Quality delta (skill uplift) | +10% |
| Bundled scripts used (trigger prompts) | 5/10 (50%) |
| Near-miss argoproj mentions — with skill | 0/6 (0%) |
| Near-miss argoproj mentions — baseline | 0/6 (0%) |
| Mean tokens — with skill | 80,471 |
| Mean tokens — baseline | 57,001 |
| Token overhead | +23470 (+41%) |

## Per-prompt

| id | category | expect | trig_with | script | qual_with | qual_base | tok_with | tok_base |
|---|---|---|---|---|---|---|---|---|
| p01 | canary-gen | True | Y | Y | PASS | PASS | 73,526 | 46,415 |
| p02 | bluegreen-gen | True | Y | Y | PASS | PASS | 193,084 | 64,882 |
| p03 | traffic-routing | True | Y | Y | PASS | PASS | 224,802 | 112,961 |
| p04 | analysis-gen | True | Y | Y | PASS | PASS | 93,629 | 165,617 |
| p05 | convert | True | Y | Y | PASS | PASS | 72,339 | 44,547 |
| p06 | troubleshoot | True | Y | - | PASS | PASS | 59,200 | 44,624 |
| p07 | troubleshoot | True | Y | - | PASS | PASS | 56,816 | 14,667 |
| p08 | ops | True | Y | - | PASS | PASS | 57,932 | 44,283 |
| p09 | gitops | True | Y | - | PASS | PASS | 55,531 | 47,478 |
| p10 | hpa | True | Y | - | PASS | FAIL | 97,707 | 16,820 |
| p11 | near-miss | False | N | - | PASS | PASS | 44,242 | 29,098 |
| p12 | near-miss | False | N | - | PASS | PASS | 29,412 | 43,674 |
| p13 | near-miss | False | N | - | PASS | PASS | 45,542 | 43,772 |
| p14 | near-miss | False | N | - | PASS | PASS | 44,836 | 44,241 |
| p15 | near-miss | False | N | - | PASS | PASS | 78,637 | 44,248 |
| p16 | near-miss | False | N | - | PASS | PASS | 60,314 | 104,695 |