"""CEP writer and reader utilities."""

import json
from pathlib import Path
from typing import Iterator

from .schema import CEP


def write_cep(cep: CEP, out_dir: str) -> str:
    """Serialise a CEP to JSON and write to disk.

    Parameters
    ----------
    cep : CEP
        The compliance evaluation packet to persist.
    out_dir : str
        Directory where the file will be written.

    Returns
    -------
    str
        Absolute path of the written file.
    """
    path = Path(out_dir) / f"{cep.sample.sample_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cep.to_dict(), indent=2, default=str), encoding="utf-8")
    return str(path.resolve())


def iter_ceps(cep_dir: str) -> Iterator[dict]:
    """Yield parsed CEP dicts from all JSON files in a directory.

    Parameters
    ----------
    cep_dir : str
        Directory containing CEP JSON files.
    """
    for p in sorted(Path(cep_dir).glob("*.json")):
        try:
            yield json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[cep_reader] skipping {p.name}: {exc}")
