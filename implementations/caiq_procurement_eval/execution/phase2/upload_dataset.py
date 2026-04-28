"""Phase 2 — Load CAIQ Dataset and Upload to Langfuse.

PURPOSE:
    Reads all vendor CAIQ .xlsx files from the dataset directory,
    parses them into CAIQSample records, and uploads them to Langfuse
    as a dataset for experiment tracking.

    Each Langfuse dataset item contains:
        input          : the CAIQ question text
        expected_output: vendor answer (YES/NO/NA) + comment
        metadata       : vendor, question_id, control_id, domain_id, caiq_version

PASTE TO:
    <repo-root>/implementations/caiq_procurement_eval/execution/phase2/upload_dataset.py

RUN WITH (from repo root):
    uv run --env-file .env --group caiq-procurement-eval \
        python implementations/caiq_procurement_eval/execution/phase2/upload_dataset.py \
        --dataset_dir /path/to/int-dataset \
        --dataset_name CAIQProcurementEval \
        --n 50

WHAT TO CHECK AFTER RUNNING:
    1. Terminal shows "Uploaded N items to dataset 'CAIQProcurementEval'"
    2. Langfuse dashboard > Datasets shows the dataset with correct item count
    3. Each item shows the question text as input and the vendor answer as expected_output
    4. Breakdown by vendor and domain is printed to terminal
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

def main() -> None:
    """Parse arguments and upload CAIQ dataset to Langfuse."""
    parser = argparse.ArgumentParser(description="Phase 2 — Upload CAIQ dataset to Langfuse")
    parser.add_argument("--dataset_dir", required=True, help="Path to directory containing CAIQ .xlsx files")
    parser.add_argument("--dataset_name", default="CAIQProcurementEval", help="Langfuse dataset name")
    parser.add_argument("--n", type=int, default=50, help="Max questions per vendor (default 50)")
    parser.add_argument("--vendors", nargs="*", default=None, help="Vendor name substrings to include (default: all)")
    parser.add_argument("--no_upload", action="store_true", help="Dry run — parse only, skip Langfuse upload")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    print(f"\n=== Phase 2: CAIQ Dataset Load & Langfuse Upload ===\n")
    print(f"  Dataset dir  : {args.dataset_dir}")
    print(f"  Dataset name : {args.dataset_name}")
    print(f"  Max per vendor: {args.n}")
    print(f"  Vendors filter: {args.vendors or 'all'}")
    print()

    # ── 1. Load CAIQ samples ──
    from caiq_procurement_eval.datasets.caiq_loader import load_caiq_directory

    dataset_path = Path(args.dataset_dir)
    if not dataset_path.exists():
        logger.error("Dataset directory not found: %s", dataset_path)
        sys.exit(1)

    logger.info("Loading CAIQ samples from %s ...", dataset_path)
    try:
        samples = load_caiq_directory(str(dataset_path), vendors=args.vendors, n_per_vendor=args.n)
    except Exception as exc:
        logger.error("Failed to load CAIQ dataset: %s", exc)
        sys.exit(1)

    if not samples:
        logger.error("No samples loaded. Check --dataset_dir and file format.")
        sys.exit(1)

    logger.info("Loaded %d samples total.", len(samples))

    # ── 2. Print breakdown ──
    vendor_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    answer_counts: dict[str, int] = {}
    for s in samples:
        vendor_counts[s.vendor] = vendor_counts.get(s.vendor, 0) + 1
        domain_counts[s.domain_id] = domain_counts.get(s.domain_id, 0) + 1
        answer_counts[s.vendor_answer.value] = answer_counts.get(s.vendor_answer.value, 0) + 1

    print("\n  Breakdown by vendor:")
    for v, count in sorted(vendor_counts.items()):
        print(f"    {v:<30} {count:>4} questions")

    print("\n  Breakdown by CCM domain (top 10):")
    for d, count in sorted(domain_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"    {d:<10} {count:>4} questions")

    print("\n  Answer distribution:")
    for a, count in sorted(answer_counts.items()):
        print(f"    {a:<20} {count:>4} questions")

    # ── 3. Build Langfuse records ──
    records = []
    for s in samples:
        records.append({
            "id": s.sample_id,
            "input": s.question_text,
            "expected_output": {
                "vendor_answer": s.vendor_answer.value,
                "vendor_comment": s.vendor_comment or "",
                "control_id": s.control_id,
            },
            "metadata": {
                "vendor": s.vendor,
                "question_id": s.question_id,
                "control_id": s.control_id,
                "domain_id": s.domain_id,
                "caiq_version": s.caiq_version or "",
                "sample_id": s.sample_id,
            },
        })

    if args.no_upload:
        print(f"\n  [DRY RUN] Would upload {len(records)} items to '{args.dataset_name}'")
        print("  -> Re-run without --no_upload to execute the upload.")
        return

    # ── 4. Upload to Langfuse ──
    pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sec = os.environ.get("LANGFUSE_SECRET_KEY", "")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not pub or not sec:
        logger.error("Langfuse keys not configured. Add LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY to .env")
        sys.exit(1)

    try:
        from langfuse import Langfuse
        lf = Langfuse(public_key=pub, secret_key=sec, host=host)
    except Exception as exc:
        logger.error("Failed to instantiate Langfuse client: %s", exc)
        sys.exit(1)

    # Create the dataset first (no-op if it already exists)
    try:
        lf.create_dataset(name=args.dataset_name)
        logger.info("Dataset '%s' created (or already exists).", args.dataset_name)
    except Exception as exc:
        logger.warning("create_dataset warning (may already exist): %s", exc)

    logger.info("Uploading %d items to Langfuse dataset '%s' ...", len(records), args.dataset_name)
    uploaded = 0
    for rec in records:
        try:
            lf.create_dataset_item(
                dataset_name=args.dataset_name,
                input=rec["input"],
                expected_output=json.dumps(rec["expected_output"]),
                id=rec["id"],
                metadata=rec["metadata"],
            )
            uploaded += 1
        except Exception as exc:
            logger.warning("Failed to upload item %s: %s", rec["id"], exc)

    lf.flush()
    logger.info("Upload complete: %d / %d items uploaded.", uploaded, len(records))

    # ── 5. Summary ──
    print("\n" + "=" * 55)
    print(f"  Uploaded {uploaded} items to dataset '{args.dataset_name}'")
    print(f"\n  Vendors: {len(vendor_counts)}")
    for v, count in sorted(vendor_counts.items()):
        print(f"    {v:<30} {count:>4} items")
    print("\n  -> Open Langfuse > Datasets to verify.")
    print("  -> Green light: proceed to Phase 3.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
