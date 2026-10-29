# Detector evaluation (rules + Presidio)

These scripts score the service's own detectors on Karina's baseline v1.1 (`data/baseline/`) with her `score.py`, so every change can be compared with the same numbers. The results behind `docs/research/yudi/2026-10-29/rules-presidio-dev-evaluation-en.md` come from them.

Run them from the repo root with the service virtualenv. Presidio and `en_core_web_lg` must be installed. Output goes to `service/scripts/eval/out/`, which git ignores.

| Script | What it gives |
|---|---|
| `eval_detectors.py` | Recall, leak rate and extra masks for rules, Presidio and their union; recall by type; example misses |
| `strategy_table.py` | The strategy table in the report: main's baseline, then each strategy added alone and cumulatively |
| `show_misses.py` | Each missed or under-tiered span with the text around it, from a prediction file |

```bash
service/.venv/bin/python service/scripts/eval/eval_detectors.py
```

```bash
service/.venv/bin/python service/scripts/eval/show_misses.py service/scripts/eval/out/pred_union_dev.jsonl ID_NUMBER,CODENAME
```

## Rules for using the data

- **Tune on the 60 development emails only** (`baseline_v1.1_dev.jsonl`). The 40 test emails are scored once, after the whole pipeline (rules, Presidio, model, thresholds) is frozen. `eval_detectors.py` refuses `--part test` and `--part all` without `--final`, and never prints test-set text.
- **Run the same script before and after a detection change**, and put both sets of numbers in the PR, so the gain of every change stays on record.
- **Adding the model's detections:** merge them with the other candidate lists in `eval_detectors.py` (`merge(r, p, m)`) and add a `model` column. The scoring needs no other change.
