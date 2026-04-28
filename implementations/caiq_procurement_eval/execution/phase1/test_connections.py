"""Phase 1 — Connection & Environment Verification.

PURPOSE:
    Verifies that all required API keys and services are correctly configured
    in the Coder workspace .env file before any evaluation work begins.
    Sends one test trace to Langfuse to confirm write access.
    Confirms the CAIQ dataset directory is readable.

PASTE TO:
    <repo-root>/implementations/caiq_procurement_eval/execution/phase1/test_connections.py

RUN WITH (from repo root):
    uv run --env-file .env --group caiq-procurement-eval \
        python implementations/caiq_procurement_eval/execution/phase1/test_connections.py \
        --dataset_dir /path/to/int-dataset

EXPECTED RESULT:
    All checks print OK. A test trace appears in the Langfuse dashboard.
    If any check fails, fix the .env entry before proceeding to Phase 2.
"""

import argparse
import os
import sys
from pathlib import Path


# ──────────────────────────────────────────────
# HELPER
# ──────────────────────────────────────────────

def ok(label: str, detail: str = "") -> None:
    """Print an OK line."""
    suffix = f"  ({detail})" if detail else ""
    print(f"  [OK]   {label}{suffix}")


def fail(label: str, error: str) -> None:
    """Print a FAIL line and exit."""
    print(f"  [FAIL] {label}")
    print(f"         Error: {error}")
    sys.exit(1)


def warn(label: str, detail: str = "") -> None:
    """Print a WARN line (non-fatal)."""
    suffix = f"  ({detail})" if detail else ""
    print(f"  [WARN] {label}{suffix}")


# ──────────────────────────────────────────────
# ARGS
# ──────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Phase 1 — environment check")
parser.add_argument("--dataset_dir", default=None, help="Path to CAIQ xlsx dataset directory")
args = parser.parse_args()

print("\n=== Phase 1: Connection & Environment Checks ===\n")

# ──────────────────────────────────────────────
# CHECK 1 — Load .env
# ──────────────────────────────────────────────

print("[1/7] Loading environment variables...")
try:
    from dotenv import load_dotenv
    load_dotenv()
    ok(".env loaded")
except Exception as e:
    fail(".env load failed", str(e))


# ──────────────────────────────────────────────
# CHECK 2 — Gemini / Google API key
# ──────────────────────────────────────────────

print("[2/7] Checking Gemini/Google API key...")
try:
    google_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not google_key or google_key in ("...", "your-key-here", ""):
        fail("Google/Gemini API key", "Not set — add GOOGLE_API_KEY or GEMINI_API_KEY to .env")
    ok("Google/Gemini API key present", f"{google_key[:10]}...")
except SystemExit:
    raise
except Exception as e:
    fail("Google/Gemini API key check", str(e))


# ──────────────────────────────────────────────
# CHECK 3 — OpenAI API key (optional)
# ──────────────────────────────────────────────

print("[3/7] Checking OpenAI API key (optional — required for openai configs)...")
try:
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key or openai_key in ("...", ""):
        warn("OpenAI API key not set", "OK if using gemini_gemini config only")
    else:
        ok("OpenAI API key present", f"{openai_key[:10]}...")
except Exception as e:
    warn("OpenAI API key check failed", str(e))


# ──────────────────────────────────────────────
# CHECK 4 — Langfuse keys
# ──────────────────────────────────────────────

print("[4/7] Checking Langfuse keys...")
try:
    pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sec = os.environ.get("LANGFUSE_SECRET_KEY", "")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not pub:
        warn("Langfuse public key not set", "Tracing will be disabled — add LANGFUSE_PUBLIC_KEY to .env")
    elif not pub.startswith("pk-lf-"):
        warn("Langfuse public key format", f"Expected prefix 'pk-lf-', got: {pub[:10]}...")
    else:
        ok("Langfuse public key", pub[:20] + "...")

    if not sec:
        warn("Langfuse secret key not set", "Tracing will be disabled — add LANGFUSE_SECRET_KEY to .env")
    elif not sec.startswith("sk-lf-"):
        warn("Langfuse secret key format", "Expected prefix 'sk-lf-'")
    else:
        ok("Langfuse secret key", "sk-lf-****")

    ok("Langfuse host", host)
except Exception as e:
    warn("Langfuse key check", str(e))


# ──────────────────────────────────────────────
# CHECK 5 — Langfuse client + test trace
# ──────────────────────────────────────────────

print("[5/7] Instantiating Langfuse client and sending test trace...")
lf_ok = False
try:
    pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sec = os.environ.get("LANGFUSE_SECRET_KEY", "")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if pub and sec:
        from langfuse import Langfuse
        lf = Langfuse(public_key=pub, secret_key=sec, host=host)
        trace_id = None
        try:
            # Langfuse v3+ API
            with lf.start_as_current_observation(
                name="phase1_caiq_connection_test",
                as_type="span",
                input={"message": "Phase 1 CAIQ connection test"},
            ) as obs:
                obs.update(output={"status": "ok"}, metadata={"phase": "1", "project": "caiq_procurement_eval"})
                trace_id = lf.get_current_trace_id()
        except AttributeError:
            # Langfuse v2 fallback
            t = lf.trace(name="phase1_caiq_connection_test", input={"message": "Phase 1 CAIQ connection test"})
            t.update(output={"status": "ok"})
            trace_id = t.id
        lf.flush()
        ok("Langfuse test trace sent", f"trace_id={trace_id}")
        lf_ok = True
    else:
        warn("Langfuse client skipped", "Keys not configured — proceeding without tracing")
except Exception as e:
    warn("Langfuse test trace failed", str(e))


# ──────────────────────────────────────────────
# CHECK 6 — CAIQ dataset directory
# ──────────────────────────────────────────────

print("[6/7] Checking CAIQ dataset directory...")
try:
    if args.dataset_dir:
        dataset_path = Path(args.dataset_dir)
        if not dataset_path.exists():
            fail("Dataset directory", f"Not found: {dataset_path}")
        xlsx_files = list(dataset_path.glob("*.xlsx")) + list(dataset_path.glob("*.xls"))
        if not xlsx_files:
            fail("Dataset directory", f"No .xlsx files found in {dataset_path}")
        ok(f"Dataset directory found", f"{len(xlsx_files)} xlsx file(s): {[f.name for f in xlsx_files[:3]]}")
    else:
        warn("Dataset directory not specified", "Pass --dataset_dir /path/to/int-dataset to verify")
except SystemExit:
    raise
except Exception as e:
    fail("Dataset directory check", str(e))


# ──────────────────────────────────────────────
# CHECK 7 — Import caiq_procurement_eval package
# ──────────────────────────────────────────────

print("[7/7] Importing caiq_procurement_eval package...")
try:
    from caiq_procurement_eval.datasets.caiq_loader import load_caiq_directory  # noqa: F401
    from caiq_procurement_eval.agents.planner_agent import PlannerAgent  # noqa: F401
    from caiq_procurement_eval.agents.evaluator_agent import EvaluatorAgent  # noqa: F401
    from caiq_procurement_eval.cep.schema import CEP  # noqa: F401
    ok("caiq_procurement_eval package importable")
except ImportError as e:
    fail("caiq_procurement_eval import failed", f"{e}\n         Run: uv sync --group caiq-procurement-eval")


# ──────────────────────────────────────────────
# SUMMARY
# ──────────────────────────────────────────────

print("\n" + "=" * 55)
print("  Phase 1 checks complete.")
if lf_ok:
    print("  -> Open Langfuse dashboard and confirm the")
    print("     'phase1_caiq_connection_test' trace is visible.")
print("  -> Green light: proceed to Phase 2.")
print("=" * 55 + "\n")
