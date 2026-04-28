# Phase 1 — Connection & Environment Verification

Verifies all API keys and services before any evaluation work begins.

## Run

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase1/test_connections.py \
    --dataset_dir /path/to/int-dataset
```

## Checks performed

| # | Check | Fatal? |
|---|---|---|
| 1 | `.env` loads without error | Yes |
| 2 | `GOOGLE_API_KEY` or `GEMINI_API_KEY` is set and non-empty | Yes |
| 3 | `OPENAI_API_KEY` present (optional) | No — warns only |
| 4 | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` format correct | No — warns only |
| 5 | Langfuse client instantiates and test trace is sent | No — warns only |
| 6 | Dataset directory exists and contains `.xlsx` files | Yes (if --dataset_dir given) |
| 7 | `caiq_procurement_eval` package imports cleanly | Yes |

## Expected output

```
=== Phase 1: Connection & Environment Checks ===

[1/7] Loading environment variables...
  [OK]   .env loaded
[2/7] Checking Gemini/Google API key...
  [OK]   Google/Gemini API key present  (AIzaSy...)
...
[7/7] Importing caiq_procurement_eval package...
  [OK]   caiq_procurement_eval package importable

===================================================
  Phase 1 checks complete.
  -> Open Langfuse dashboard and confirm the
     'phase1_caiq_connection_test' trace is visible.
  -> Green light: proceed to Phase 2.
===================================================
```

## If a check fails

- **Gemini key missing**: Add `GOOGLE_API_KEY=<your-key>` to `.env`
- **Package import fails**: Run `uv sync --group caiq-procurement-eval`
- **Dataset directory not found**: Check the path to your `int-dataset` folder
