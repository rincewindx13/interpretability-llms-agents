# Phase 3 — CEP Generation (3-Agent Pipeline)

Runs the full Planner → Evaluator → Verifier pipeline on every CAIQ sample
and writes one CEP JSON per sample to the output directory.

## Run

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase3/run_generate_ceps.py \
    --dataset_dir /path/to/int-dataset \
    --n 50 \
    --config gemini_gemini \
    --workers 4 \
    --out implementations/caiq_procurement_eval/execution/phase3/ceps/
```

## With CCM context (recommended)

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase3/run_generate_ceps.py \
    --dataset_dir /path/to/int-dataset \
    --ccm_file /path/to/CCM.xlsx \
    --n 50 \
    --config gemini_gemini \
    --workers 4 \
    --out implementations/caiq_procurement_eval/execution/phase3/ceps/
```

## Agent pipeline

```
PlannerAgent  (text-only, no vendor data)
    ↓ plan: steps, risk_level, nist_mapping_hint
EvaluatorAgent  (reads vendor answer + CCM context)
    ↓ evaluation: verdict, confidence, evidence_quality, gap_description
VerifierAgent  (cross-check pass 2.5)
    ↓ verifier: confirmed | revised | skipped
```

## Config options

| Config | Planner | Evaluator | Cost |
|---|---|---|---|
| `gemini_gemini` | Gemini 2.5 Flash Lite | Gemini 2.5 Flash Lite | Cheapest |
| `openai_openai` | GPT-4o | GPT-4o | Most expensive |
| `gemini_openai` | Gemini 2.5 Flash Lite | GPT-4o | Balanced |

## Options

| Flag | Default | Description |
|---|---|---|
| `--dataset_dir` | required | CAIQ xlsx directory |
| `--ccm_file` | none | CCM xlsx for control context lookup |
| `--n` | `50` | Max questions per vendor |
| `--config` | `gemini_gemini` | Backend config |
| `--workers` | `2` | Parallel threads (keep ≤ 5 for rate limits) |
| `--out` | `phase3/ceps/` | Output directory |
| `--no_verifier` | off | Skip VerifierAgent |

## Output

CEP JSON files are written to `--out/<config>/`, one per sample:

```
phase3/ceps/
  gemini_gemini/
    vendor_a__AIS-01.1__abc123.json
    vendor_a__IAM-02.1__def456.json
    ...
```

Each JSON contains: `run_id`, `config`, `sample`, `plan`, `evaluation`, `verifier`, `timestamps`, `errors`.
