# CAIQ Procurement Eval — Execution Phases

Five sequential phases that take you from environment setup to a full vendor compliance report.
Run each phase from the **repo root** using `uv run --env-file .env`.

---

## Prerequisites

```bash
# Install the caiq-procurement-eval dependency group
uv sync --group caiq-procurement-eval

# Copy the example env file and fill in your keys
cp .env.example .env
```

Required `.env` keys:

| Key | Required | Notes |
|---|---|---|
| `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Yes | For Gemini 2.5 Flash Lite |
| `OPENAI_API_KEY` | No | Only needed for `openai_openai` / `gemini_openai` configs |
| `LANGFUSE_PUBLIC_KEY` | No | Enables trace observability |
| `LANGFUSE_SECRET_KEY` | No | Enables trace observability |
| `LANGFUSE_HOST` | No | Defaults to `https://cloud.langfuse.com` |

---

## Phase Overview

| Phase | Script | Purpose |
|---|---|---|
| **Phase 1** | `phase1/test_connections.py` | Verify API keys, Langfuse, dataset dir |
| **Phase 2** | `phase2/upload_dataset.py` | Parse CAIQ xlsx → upload to Langfuse |
| **Phase 3** | `phase3/run_generate_ceps.py` | Run 3-agent pipeline → write CEP JSONs |
| **Phase 4** | `phase4/run_eval.py` | Score CEPs with verdicts + LLM judge |
| **Phase 5** | `phase5/analyze_results.py` | Aggregate → CSV / Excel / markdown report |

---

## Phase 1 — Environment Check

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase1/test_connections.py \
    --dataset_dir /path/to/int-dataset
```

Checks: `.env` loads, Gemini key present, Langfuse client connects, test trace sent,
dataset directory contains `.xlsx` files, package imports cleanly.

---

## Phase 2 — Dataset Upload

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase2/upload_dataset.py \
    --dataset_dir /path/to/int-dataset \
    --dataset_name CAIQProcurementEval \
    --n 50
```

Parses all vendor CAIQ `.xlsx` files, prints breakdown by vendor/domain/answer,
and uploads items to Langfuse. Use `--no_upload` for a dry run.

---

## Phase 3 — CEP Generation

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase3/run_generate_ceps.py \
    --dataset_dir /path/to/int-dataset \
    --n 50 \
    --config gemini_gemini \
    --workers 4 \
    --out implementations/caiq_procurement_eval/execution/phase3/ceps/
```

Runs `PlannerAgent → EvaluatorAgent → VerifierAgent` on each CAIQ sample.
Each sample writes one CEP JSON to `--out/<config>/`. Langfuse traces are
created per sample if keys are configured.

Config options: `gemini_gemini` | `openai_openai` | `gemini_openai`

---

## Phase 4 — Evaluation

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase4/run_eval.py \
    --cep_dir implementations/caiq_procurement_eval/execution/phase3/ceps/gemini_gemini/ \
    --out implementations/caiq_procurement_eval/execution/phase4/output/metrics.jsonl
```

Reads CEP JSONs, extracts verdicts + evidence quality, runs LLM-as-judge (5 rubrics),
and writes `metrics.jsonl`. Use `--no_judge` to skip the judge for faster iteration.

---

## Phase 5 — Analysis & Reporting

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase5/analyze_results.py \
    --metrics implementations/caiq_procurement_eval/execution/phase4/output/metrics.jsonl \
    --out implementations/caiq_procurement_eval/execution/phase5/output/summary
```

Produces:
- `summary.csv` — compliance rate by vendor × CCM domain
- `summary.xlsx` — Excel workbook (4 sheets: by_vendor, by_vendor_domain, gap_counts, evidence_quality)
- `summary_report.md` — full markdown analysis with gap details and LLM judge scores
