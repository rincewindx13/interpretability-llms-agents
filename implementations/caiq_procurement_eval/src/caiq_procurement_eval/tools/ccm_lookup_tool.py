"""CCMLookupTool — retrieves CCM control context for a given control ID.

Equivalent to the OcrReaderTool in agentic_vqa_eval: it pre-fetches
authoritative CCM control text so the EvaluatorAgent has grounding context,
separating framework knowledge from reasoning.
"""

from pathlib import Path
from typing import Dict, Optional

import pandas as pd


# Lightweight in-memory CCM index populated from xlsx at first use
_CCM_INDEX: Dict[str, dict] = {}
_CCM_LOADED = False


def _load_ccm_index(ccm_file: Optional[str] = None) -> None:
    """Populate the in-memory CCM control index from a CCM xlsx file."""
    global _CCM_INDEX, _CCM_LOADED  # noqa: PLW0603
    if _CCM_LOADED:
        return

    _CCM_LOADED = True

    if not ccm_file:
        return

    path = Path(ccm_file)
    if not path.exists():
        return

    try:
        xl = pd.ExcelFile(path, engine="openpyxl")
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, dtype=str).dropna(how="all")
            id_col = next((c for c in df.columns if "control id" in c.lower()), None)
            title_col = next((c for c in df.columns if "title" in c.lower()), None)
            desc_col = next((c for c in df.columns if "specification" in c.lower() or "description" in c.lower()), None)
            domain_col = next((c for c in df.columns if "domain" in c.lower()), None)
            nist_col = next((c for c in df.columns if "nist" in c.lower()), None)

            if not id_col:
                continue

            for _, row in df.iterrows():
                ctrl_id = str(row.get(id_col, "")).strip()
                if not ctrl_id or ctrl_id.lower() == "nan":
                    continue
                _CCM_INDEX[ctrl_id] = {
                    "control_id": ctrl_id,
                    "title": str(row.get(title_col, "")).strip() if title_col else "",
                    "description": str(row.get(desc_col, "")).strip() if desc_col else "",
                    "domain": str(row.get(domain_col, "")).strip() if domain_col else "",
                    "nist_mapping": str(row.get(nist_col, "")).strip() if nist_col else "",
                }
            if _CCM_INDEX:
                break
    except Exception as exc:
        print(f"[ccm_lookup] failed to load CCM index from {ccm_file}: {exc}")


class CCMLookupTool:
    """Retrieves CCM control description and NIST mapping for a given control ID.

    Used to inject authoritative framework context into the EvaluatorAgent prompt,
    separating *what the control requires* from *whether the vendor meets it*.
    """

    def __init__(self, ccm_file: Optional[str] = None):
        self.ccm_file = ccm_file
        _load_ccm_index(ccm_file)

    def lookup(self, control_id: str) -> Optional[str]:
        """Return a formatted context string for a CCM control ID.

        Parameters
        ----------
        control_id : str
            CCM control identifier, e.g. ``AIS-01``.

        Returns
        -------
        str or None
            Formatted control context, or None if not found.
        """
        entry = _CCM_INDEX.get(control_id)
        if not entry:
            return None

        parts = []
        if entry.get("title"):
            parts.append(f"Control Title: {entry['title']}")
        if entry.get("description"):
            desc = entry["description"]
            parts.append(f"Control Specification: {desc[:500]}{'...' if len(desc) > 500 else ''}")
        if entry.get("nist_mapping"):
            parts.append(f"NIST 800-53 Mapping: {entry['nist_mapping']}")

        return "\n".join(parts) if parts else None

    def is_loaded(self) -> bool:
        """Return True if the CCM index was successfully populated."""
        return bool(_CCM_INDEX)
