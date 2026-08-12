#!/usr/bin/env python3
"""Ingest Argentina DNEC criminal-statistics downloads reproducibly.

The importer deliberately converts PDF documentation to Markdown as part of
ingest.  Downstream analysis must use those Markdown files rather than reading
the source PDFs directly.  Raw downloads remain local/ignored under data/raw;
the compact provenance manifest and documentation extracts are versionable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import requests
from tqdm import tqdm


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOWNLOADS = Path.home() / "Downloads"
RAW_ROOT = REPO_ROOT / "data/raw/ar/security_dnec/download_2026-07-12"
DOCS_ROOT = REPO_ROOT / "docs/sources/ar/security_dnec"
SOURCE_PAGE = "https://www.argentina.gob.ar/seguridad/estadisticascriminales/bases-de-datos"

FILES: tuple[tuple[str, str, str, str], ...] = (
    ("snic", "csv", "snic_pais_2000_2025.csv", "snic-pais.csv"),
    ("snic", "csv", "snic_provincias_2000_2025.csv", "snic-provincias.csv"),
    ("sat", "csv", "sat_suicidios_2017_2024.csv", "SAT-SS-BU_2017-2024.csv"),
    ("sat", "csv", "sat_muertes_viales_2017_2024.csv", "SAT-MV-BU.csv"),
    ("sat", "csv", "sat_homicidios_dolosos_2017_2024.csv", "SAT-HD-BU.csv"),
    ("sat", "csv", "sat_propiedad_2017_2024.csv", "SAT-Propiedad-BU_2017-2024.csv"),
    ("pufeaf", "csv", "pufeaf_2020_2024.csv", "Base_PUFEAF_2024.csv"),
    ("snic", "pdf", "manual_snic.pdf", "Manual_de_usuario_Base_SNIC.pdf"),
    ("sat", "pdf", "manual_sat_suicidios_2024.pdf", "Manual_de_usuario_Base_SAT-SS_2024.pdf"),
    ("sat", "pdf", "manual_sat_muertes_viales_2024.pdf", "Manual de usuario Base SAT-MV_2024.pdf"),
    ("sat", "pdf", "manual_sat_propiedad_2024.pdf", "Manual de usuario Base SAT Prop_2024.pdf"),
    ("glossary", "pdf", "glosario_conceptual.pdf", "glosario_vf.pdf"),
    ("env", "zip", "env_documentacion.zip", "env_documentacion.zip"),
    ("snic", "csv", "snic_departamentos_anual_2000_2025.csv", "snic-departamentos-anual.csv"),
    ("snic", "zip", "snic_departamentos_mensual_2000_2025.zip", "snic-departamentos-mes-sexo_csv.zip"),
    ("snic", "pdf", "manual_snic_departamentos_2024.pdf", "Manual_de_usuario_Base_SNIC_2024.pdf"),
    ("env", "rar", "env2017_microdatos.rar", "ENV2017_Baseusuario.rar"),
)

REMOTE_URLS = {
    "snic-departamentos-anual.csv": "https://cloud-snic.minseg.gob.ar/Bases/SNIC/snic-departamentos-anual.csv",
    "snic-departamentos-mes-sexo_csv.zip": "https://cloud-snic.minseg.gob.ar/Bases/SNIC/snic-departamentos-mes-sexo_csv.zip",
    "Manual_de_usuario_Base_SNIC_2024.pdf": "https://cloud-snic.minseg.gob.ar/Bases/SNIC/Manual_de_usuario_Base_SNIC_2024.pdf",
    "ENV2017_Baseusuario.rar": "https://cloud-snic.minseg.gob.ar/Bases/OTRAS_BASES/ENV/ENV2017_Baseusuario.rar",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def slug(value: str) -> str:
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def safe_extract(archive: Path, destination: Path) -> list[Path]:
    extracted: list[Path] = []
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zip_file:
        for member in zip_file.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError(f"Unsafe ZIP member: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(target)
    return extracted


def safe_extract_rar(archive: Path, destination: Path) -> list[Path]:
    import rarfile

    extracted: list[Path] = []
    destination.mkdir(parents=True, exist_ok=True)
    with rarfile.RarFile(archive) as rar_file:
        for member in rar_file.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError(f"Unsafe RAR member: {member.filename}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with rar_file.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(target)
    return extracted


def download_with_resume(url: str, destination: Path) -> None:
    """Human-invoked streaming download with progress, checkpoint and resume."""
    if destination.exists():
        return
    partial = destination.with_suffix(destination.suffix + ".partial")
    downloaded = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}
    with requests.get(url, headers=headers, stream=True, timeout=60) as response:
        response.raise_for_status()
        if downloaded and response.status_code != 206:
            downloaded = 0
            partial.unlink(missing_ok=True)
        total = int(response.headers.get("content-length", 0)) + downloaded
        destination.parent.mkdir(parents=True, exist_ok=True)
        with partial.open("ab" if downloaded else "wb") as output, tqdm(
            total=total or None,
            initial=downloaded,
            unit="B",
            unit_scale=True,
            desc=destination.name,
        ) as progress:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                output.write(chunk)
                output.flush()
                progress.update(len(chunk))
    partial.replace(destination)


def pdf_pages(pdf: Path) -> int | None:
    result = subprocess.run(
        ["pdfinfo", str(pdf)], text=True, capture_output=True, check=False
    )
    match = re.search(r"^Pages:\s+(\d+)$", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


def convert_pdf(pdf: Path, markdown: Path, *, raw_relative: str) -> dict[str, object]:
    """Extract text with page breaks, preserving a clear provenance header."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"pdftotext failed for {pdf.name}: {result.stderr.strip()}")
    pages = [part.strip() for part in result.stdout.split("\f")]
    if pages and not pages[-1]:
        pages.pop()
    chunks = [
        f"# {pdf.stem}\n\n"
        f"- Original local: `{raw_relative}`\n"
        f"- Extracted with: `pdftotext -layout`\n"
        f"- PDF pages: {pdf_pages(pdf) or 'unknown'}\n"
        "- Note: this is a text extraction for review; consult the original PDF for layout-specific ambiguity.\n"
    ]
    for number, page in enumerate(pages, start=1):
        chunks.append(f"\n## Página {number}\n\n{page or '[Sin texto extraíble]'}\n")
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text("\n".join(chunks), encoding="utf-8")
    return {
        "pdf_pages": pdf_pages(pdf),
        "markdown_pages": len(pages),
        "extracted_characters": sum(len(page) for page in pages),
        "markdown": markdown.relative_to(REPO_ROOT).as_posix(),
    }


def copy_source(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, default=DEFAULT_DOWNLOADS)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--docs-root", type=Path, default=DOCS_ROOT)
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="Download missing official files with progress/resume (intended for human execution).",
    )
    args = parser.parse_args()

    download_failures: list[dict[str, str]] = []
    if args.download_missing:
        for source_name, url in REMOTE_URLS.items():
            try:
                download_with_resume(url, args.downloads / source_name)
            except requests.RequestException as exc:
                # Each remote artifact is independently resumable. A transient
                # failure in optional documentation or ENV microdata must not
                # discard SNIC CSVs that already finished downloading.
                download_failures.append(
                    {"original_name": source_name, "source_url": url, "error": str(exc)}
                )
                print(f"WARNING: deferred remote source {source_name}: {exc}")

    manifest: dict[str, object] = {
        "provider": "Dirección Nacional de Estadística Criminal (DNEC), Ministerio de Seguridad de la Nación",
        "source_page": SOURCE_PAGE,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "files": [],
        "duplicates": [],
        "missing_remote": download_failures,
    }
    seen: dict[str, str] = {}
    pdf_records: list[tuple[Path, Path]] = []

    for family, kind, canonical_name, source_name in FILES:
        source = args.downloads / source_name
        if not source.exists():
            if source_name in REMOTE_URLS:
                if not any(item["original_name"] == source_name for item in manifest["missing_remote"]):
                    manifest["missing_remote"].append(
                        {
                            "original_name": source_name,
                            "source_url": REMOTE_URLS[source_name],
                            "error": "not present in downloads directory",
                        }
                    )
                continue
            raise FileNotFoundError(source)
        digest = sha256(source)
        destination = args.raw_root / family / kind / canonical_name
        record: dict[str, object] = {
            "family": family,
            "kind": kind,
            "canonical_name": canonical_name,
            "original_name": source.name,
            "sha256": digest,
            "bytes": source.stat().st_size,
            "raw_path": destination.relative_to(REPO_ROOT).as_posix(),
            "source_url": REMOTE_URLS.get(source.name, SOURCE_PAGE),
        }
        if digest in seen:
            record["duplicate_of"] = seen[digest]
            manifest["duplicates"].append(record)
        else:
            copy_source(source, destination)
            seen[digest] = destination.relative_to(REPO_ROOT).as_posix()
            manifest["files"].append(record)
            if kind == "pdf":
                pdf_records.append((destination, args.docs_root / "markdown" / f"{slug(canonical_name)}.md"))
            if kind == "zip":
                for extracted in safe_extract(destination, args.raw_root / family / "extracted"):
                    if extracted.suffix.lower() == ".pdf":
                        pdf_records.append((extracted, args.docs_root / "markdown" / f"env_{slug(extracted.stem)}.md"))
            if kind == "rar":
                safe_extract_rar(destination, args.raw_root / family / "extracted")

    # Explicitly record filenames the user supplied that duplicate canonical data.
    for duplicate_name, canonical_name in (
        ("snic-pais(1).csv", "snic_pais_2000_2025.csv"),
        ("snic-provincias(1).csv", "snic_provincias_2000_2025.csv"),
        ("Manual_de_usuario_Base_SNIC_provincias.pdf", "manual_snic.pdf"),
    ):
        duplicate = args.downloads / duplicate_name
        if duplicate.exists():
            manifest["duplicates"].append(
                {
                    "original_name": duplicate.name,
                    "canonical_name": canonical_name,
                    "sha256": sha256(duplicate),
                    "duplicate_of": canonical_name,
                }
            )

    conversion: list[dict[str, object]] = []
    for pdf, markdown in pdf_records:
        conversion.append(
            {
                "pdf": pdf.relative_to(REPO_ROOT).as_posix(),
                **convert_pdf(pdf, markdown, raw_relative=pdf.relative_to(REPO_ROOT).as_posix()),
            }
        )
    manifest["pdf_conversion"] = conversion
    converted_pdfs = {item["pdf"] for item in conversion}
    recorded_pdfs = {
        item["raw_path"]
        for item in manifest["files"]
        if item.get("kind") == "pdf"
    }
    missing_markdown = sorted(recorded_pdfs - converted_pdfs)
    if missing_markdown:
        raise RuntimeError(f"PDF documentation lacks Markdown conversion: {missing_markdown}")

    args.docs_root.mkdir(parents=True, exist_ok=True)
    (args.docs_root / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Fuentes DNEC de estadísticas criminales argentinas",
        "",
        f"Fuente oficial: {SOURCE_PAGE}",
        "",
        "Los archivos originales se conservan localmente bajo `data/raw/`; el manifiesto registra hashes y nombres canónicos.",
        "",
        "## Documentación convertida",
        "",
    ]
    for item in conversion:
        lines.append(f"- [{item['pdf']}]({item['markdown']}) — {item['extracted_characters']} caracteres extraídos.")
    (args.docs_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
