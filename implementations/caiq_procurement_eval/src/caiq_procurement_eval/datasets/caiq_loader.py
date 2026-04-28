"""CAIQ dataset loader — parses vendor-completed CAIQ xlsx files.

Handles CAIQ versions 4.0.x and 4.1.x with flexible column name resolution.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .caiq_sample import CAIQSample, ComplianceCategory, VendorAnswer


# ---------------------------------------------------------------------------
# Column name aliases across CAIQ versions
# ---------------------------------------------------------------------------

_QUESTION_ID_COLS = [
    "Question ID", "question_id", "QuestionID", "CAIQ ID",
    "Question #", "ID", "Ref #",
]
_QUESTION_TEXT_COLS = [
    "Question", "question", "Question Text", "Description",
    "Control Specification", "CAIQ Question",
]
_ANSWER_COLS = [
    "Answer", "answer", "Response", "Yes/No/NA", "CSP Answer",
    "Consensus Assessment", "Yes / No / NA", "CSP CAIQ Answer",
]
_COMMENT_COLS = [
    "Comment", "comment", "Comments", "Explanation", "Evidence",
    "CSP Comments", "Implementation Description", "Answer Description",
    "CSP Implementation Description (Optional/Recommended)",
    "CSP Implementation Description",
]
_CONTROL_ID_COLS = [
    "Control ID", "control_id", "CCM Control ID", "Control",
    "CCM ID", "Control Reference",
]
_DOMAIN_COLS = [
    "Control Domain", "control_domain", "Domain", "Security Domain",
    "CCM Domain", "Domain ID", "CCM Domain Title",
]


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Return the first matching column name from candidates, or None."""
    for c in candidates:
        if c in df.columns:
            return c
    # Case-insensitive fallback
    lower = {col.lower(): col for col in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _extract_version(filename: str) -> str:
    """Infer CAIQ version from filename (e.g. 'CAIQv4.0.2' → '4.0.2')."""
    match = re.search(r"v(\d+\.\d+[\.\d]*)", filename, re.IGNORECASE)
    return match.group(1) if match else "unknown"


def _extract_vendor(filename: str) -> str:
    """Derive a clean vendor name from the filename."""
    name = Path(filename).stem
    # Strip common suffixes
    name = re.sub(r"[-_]?(CAIQ|STAR|Security.Questionnaire|v\d[\d.]*|Final|final)", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[-_]+", " ", name).strip()
    return name or Path(filename).stem


def _infer_control_id(question_id: str) -> str:
    """Derive the parent CCM control ID from a question ID (AIS-01.1 → AIS-01)."""
    parts = str(question_id).rsplit(".", 1)
    return parts[0] if len(parts) == 2 else str(question_id)


def _infer_domain_id(control_id: str) -> str:
    """Extract the domain prefix from a CCM control ID (AIS-01 → AIS)."""
    return str(control_id).split("-")[0].upper()


def _read_caiq_sheet(filepath: Path) -> Optional[pd.DataFrame]:
    """Try to find and return the most relevant sheet in a CAIQ xlsx file."""
    xl = pd.ExcelFile(filepath)
    sheet_names = xl.sheet_names

    # Prefer sheets with 'CAIQ' or 'Assessment' in their name
    preferred = [s for s in sheet_names if re.search(r"caiq|assessment|response", s, re.IGNORECASE)]
    ordered = preferred + [s for s in sheet_names if s not in preferred]

    for sheet in ordered:
        for header_row in [0, 1, 2]:
            try:
                df = xl.parse(sheet, dtype=str, header=header_row)
                df = df.dropna(how="all")
                if len(df) > 5 and _find_col(df, _QUESTION_ID_COLS):
                    return df
            except Exception:
                continue
    return None


def load_caiq_file(filepath: str, vendor_override: Optional[str] = None, n: Optional[int] = None) -> List[CAIQSample]:
    """Load a single vendor CAIQ xlsx file into a list of CAIQSample objects.

    Parameters
    ----------
    filepath : str
        Path to the vendor-completed CAIQ xlsx file.
    vendor_override : str, optional
        Explicit vendor name; inferred from filename if not provided.
    n : int, optional
        Maximum number of samples to return.

    Returns
    -------
    list of CAIQSample
        One sample per CAIQ question row.
    """
    path = Path(filepath)
    vendor = vendor_override or _extract_vendor(path.name)
    version = _extract_version(path.name)

    df = _read_caiq_sheet(path)
    if df is None:
        raise ValueError(f"Could not find a valid CAIQ sheet in {filepath}")

    q_col = _find_col(df, _QUESTION_ID_COLS)
    text_col = _find_col(df, _QUESTION_TEXT_COLS)
    ans_col = _find_col(df, _ANSWER_COLS)
    comment_col = _find_col(df, _COMMENT_COLS)
    ctrl_col = _find_col(df, _CONTROL_ID_COLS)
    domain_col = _find_col(df, _DOMAIN_COLS)

    if not q_col:
        raise ValueError(f"Cannot locate Question ID column in {filepath}. Columns: {list(df.columns)}")

    samples: List[CAIQSample] = []
    for _, row in df.iterrows():
        question_id = str(row.get(q_col, "")).strip()
        if not question_id or question_id.lower() in {"nan", "question id", "id"}:
            continue

        control_id = str(row.get(ctrl_col, "")).strip() if ctrl_col else _infer_control_id(question_id)
        if not control_id or control_id.lower() == "nan":
            control_id = _infer_control_id(question_id)

        domain_id = str(row.get(domain_col, "")).strip() if domain_col else _infer_domain_id(control_id)
        if not domain_id or domain_id.lower() == "nan":
            domain_id = _infer_domain_id(control_id)

        raw_answer = str(row.get(ans_col, "")).strip() if ans_col else ""
        comment = str(row.get(comment_col, "")).strip() if comment_col else ""
        question_text = str(row.get(text_col, "")).strip() if text_col else ""

        if comment.lower() == "nan":
            comment = ""
        if question_text.lower() == "nan":
            question_text = ""

        answer = VendorAnswer.normalise(raw_answer)
        category = ComplianceCategory.from_domain_id(domain_id)

        sample_id = f"{vendor.replace(' ', '_')}_{question_id}"

        metadata: Dict[str, str] = {}
        for col in df.columns:
            if col not in {q_col, text_col, ans_col, comment_col, ctrl_col, domain_col}:
                val = str(row.get(col, "")).strip()
                if val and val.lower() != "nan":
                    metadata[col] = val

        samples.append(
            CAIQSample(
                sample_id=sample_id,
                vendor=vendor,
                question_id=question_id,
                control_id=control_id,
                domain_id=domain_id.split("-")[0].upper(),
                question_text=question_text,
                vendor_answer=answer,
                vendor_comment=comment,
                caiq_version=version,
                category=category,
                metadata=metadata,
            )
        )

    if n is not None:
        samples = samples[:n]

    return samples


def load_caiq_directory(
    directory: str,
    vendors: Optional[List[str]] = None,
    n_per_vendor: Optional[int] = None,
) -> List[CAIQSample]:
    """Load all CAIQ xlsx files from a directory.

    Parameters
    ----------
    directory : str
        Path to folder containing vendor CAIQ xlsx files.
    vendors : list of str, optional
        Whitelist of vendor name substrings to include (case-insensitive).
    n_per_vendor : int, optional
        Maximum samples to load per vendor file.

    Returns
    -------
    list of CAIQSample
        Combined samples from all matched vendor files.
    """
    dirpath = Path(directory)
    files = sorted(dirpath.glob("*.xlsx"))

    if vendors:
        lowered = [v.lower() for v in vendors]
        files = [f for f in files if any(v in f.name.lower() for v in lowered)]

    all_samples: List[CAIQSample] = []
    for f in files:
        try:
            samples = load_caiq_file(str(f), n=n_per_vendor)
            all_samples.extend(samples)
            print(f"  Loaded {len(samples):>4} questions from {f.name}")
        except Exception as exc:
            print(f"  SKIP {f.name}: {exc}")

    return all_samples
