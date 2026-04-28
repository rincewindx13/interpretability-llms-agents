# Phase 2 — Dataset Load & Langfuse Upload

Parses all vendor CAIQ `.xlsx` files and uploads them to Langfuse as a dataset
for experiment tracking.

## Run

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase2/upload_dataset.py \
    --dataset_dir /path/to/int-dataset \
    --dataset_name CAIQProcurementEval \
    --n 50
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--dataset_dir` | required | Path to directory containing CAIQ `.xlsx` files |
| `--dataset_name` | `CAIQProcurementEval` | Langfuse dataset name to create/update |
| `--n` | `50` | Max questions per vendor |
| `--vendors` | all | Filter to specific vendor name substrings |
| `--no_upload` | off | Dry run — parse only, skip upload |

## Dry run first

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase2/upload_dataset.py \
    --dataset_dir /path/to/int-dataset \
    --no_upload
```

## What to verify after running

1. Terminal shows "Uploaded N items to dataset 'CAIQProcurementEval'"
2. Langfuse > Datasets shows the dataset with correct item count
3. Each item has the question text as `input` and vendor answer as `expected_output`
4. Breakdown by vendor / domain / answer distribution printed to terminal
