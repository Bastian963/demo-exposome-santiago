#!/usr/bin/env python3
"""Fetch and inventory official INDEC AMBA population denominators."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/ar/security_dnec/download_2026-07-12/population"
DOCS = ROOT / "docs/sources/ar/security_dnec/indec_population_manifest.json"
SOURCES = {
    "indec_population_departments_2022_2035.csv": {
        "url": "https://www.indec.gob.ar/ftp/cuadros/poblacion/base_estimaciones_pob_deptos_2022_2035.csv",
        "coverage": "2022-2035; Censo 2022 base",
    },
    "indec_population_caba_2010_2025.xls": {
        "url": "https://sitioanterior.indec.gob.ar/bajarCuadroEstadistico.asp?idc=4D0F65833B7A52A82B1BFB09955B81C133919F8BABAEB44F87AABC071419733073ED74F0BFE34E2F",
        "coverage": "2010-2025; historical series used for 2017-2021 only",
    },
    "indec_population_buenos_aires_2010_2025.xls": {
        "url": "https://sitioanterior.indec.gob.ar/bajarCuadroEstadistico.asp?idc=42FDBE7BCCCEAA355BF5B1A2C7FFA4113405BA41623EA42A34AD2B22E722504744D35E4FFCB64A37",
        "coverage": "2010-2025; historical series used for 2017-2021 only",
    },
}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-download", action="store_true", help="Only refresh the local manifest")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    if not args.no_download:
        for filename, source in SOURCES.items():
            with urllib.request.urlopen(source["url"]) as response, (RAW / filename).open("wb") as output:
                shutil.copyfileobj(response, output)
    records = []
    for filename, source in SOURCES.items():
        path = RAW / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        records.append(
            {
                "file": path.relative_to(ROOT).as_posix(),
                "sha256": _hash(path),
                "bytes": path.stat().st_size,
                **source,
            }
        )
    DOCS.parent.mkdir(parents=True, exist_ok=True)
    DOCS.write_text(
        json.dumps(
            {
                "provider": "INDEC",
                "retrieved_at": datetime.now(UTC).isoformat(),
                "records": records,
                "method_note": "The 2022-base series supersedes 2010-base estimates from 2022 onward.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
