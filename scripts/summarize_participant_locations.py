"""Resumen reproducible de la residencia de participantes de la cohorte.

Lee el raw inmutable ``data/raw/zipcodes/<version>/participant_locations.csv``
(una fila por participante, columnas ``City,State,Country``; sin códigos
postales pese al nombre del archivo original), normaliza los strings sucios y
agrupa a área metropolitana. Es la fuente de los números citados en
``docs/multicity_status.md``.

Uso:

    python3 scripts/summarize_participant_locations.py [--version 2026-07] [--write]

``--write`` materializa ``data/interim/cohort/participant_city_counts.csv``
(conteos por país/metro/ciudad normalizada; interim, no versionado).

La agrupación metropolitana es deliberadamente aproximada (nivel checklist,
no crosswalk oficial): las reglas están en ``METRO_RULES`` y las decisiones en
``data/raw/zipcodes/README.md``.
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "zipcodes"
INTERIM_CSV = ROOT / "data" / "interim" / "cohort" / "participant_city_counts.csv"
DEFAULT_VERSION = "2026-07"

COUNTRY_LABELS = {
    "COLOMBIA": "CO",
    "PERU": "PE",
    "CHILE": "CL",
    "MEXICO": "MX",
    "ARGENTINA": "AR",
    "BRASIL": "BR",
    "ESTADOS UNIDOS": "US",
    "EEUU": "US",
    "ESPANA": "ES",
    "ITALIA": "IT",
    "PANAMA": "PA",
    "GUATEMALA": "GT",
    "ARUBA": "AW",
    "CANADA": "CA",
}

# Typos evidentes en el raw; se corrigen solo en memoria, nunca en el archivo.
CITY_TYPOS = {
    "PERALLILLO": "PERALILLO",
    "FERRENATE": "FERRENAFE",
    "MAGDALENA CONTRERAS": "LA MAGDALENA CONTRERAS",
}

# Reglas de agrupación metropolitana, evaluadas en orden por país.
# Cada regla: (etiqueta_metro, ciudades exactas normalizadas | None, predicado state).
# Aproximaciones asumidas (ver README del raw): state SP -> RMSP, state MG ->
# RMBH, provincia San Juan completa -> "San Juan", Bs.As. provincia -> AMBA.
METRO_RULES: dict[str, list[tuple[str, set[str] | None, set[str] | None]]] = {
    "CL": [
        ("Santiago (RM)", None, {"METROPOLITANA", "REGION METROPOLITANA"}),
        ("Talca", {"TALCA"}, None),
    ],
    "AR": [
        ("San Juan (Gran San Juan + provincia)", None, {"SAN JUAN"}),
        (
            "Buenos Aires (CABA+AMBA)",
            None,
            {
                "CIUDAD AUTONOMA DE BUENOS AIRES",
                "CABA",
                "PROVINCIA DE BUENOS AIRES",
                "BUENOS AIRES",
                "BS.AS",
                "BS.AS.",
                "BSAS.",
            },
        ),
    ],
    "PE": [
        ("Lima Metropolitana", {"LIMA", "CALLAO"}, None),
        ("Arequipa", {"AREQUIPA"}, None),
        ("Chiclayo", {"CHICLAYO"}, None),
    ],
    "CO": [
        ("Bogotá D.C.", {"BOGOTA", "BOGOTA D.C", "BOGOTA D.C."}, None),
        (
            "Valle de Aburrá (Medellín)",
            {
                "MEDELLIN",
                "ENVIGADO",
                "SABANETA",
                "ITAGUI",
                "BELLO",
                "LA ESTRELLA",
                "COPACABANA",
                "GIRARDOTA",
            },
            None,
        ),
        ("Santa Marta", {"SANTA MARTA"}, None),
        ("Cartagena", {"CARTAGENA"}, None),
        ("Barranquilla", {"BARRANQUILLA"}, None),
        ("Cali", {"CALI", "SANTIAGO DE CALI"}, None),
        ("Pasto", {"SAN JUAN DE PASTO", "PASTO"}, None),
    ],
    "MX": [
        # Alcaldías CDMX + conurbación EdoMex. Incluye los "Azcapotzalco,
        # Estado de México" mal etiquetados (es alcaldía CDMX: mismo metro).
        ("Valle de México (ZMVM)", None, {"CDMX"}),
        (
            "Valle de México (ZMVM)",
            {
                "TLALNEPANTLA DE BAZ",
                "ECATEPEC DE MORELOS",
                "MUNICIPIO DE NAUCALPAN DE JUAREZ",
                "MUNICIPIO DE HUIXQUILUCAN",
                "MUNICIPIO DE ATIZAPAN DE ZARAGOZA",
                "CIUDAD NEZAHUALCOYOTL",
                "MUNICIPIO DE CHIMALHUACAN",
                "TEXCOCO DE MORA",
                "AZCAPOTZALCO",
            },
            None,
        ),
        # Tepoztlán aparece bajo EdoMex por error (es Morelos, ZM Cuernavaca).
        ("Cuernavaca (ZM)", {"CUERNAVACA", "JIUTEPEC", "TEPOZTLAN"}, None),
    ],
    "BR": [
        ("São Paulo (RMSP aprox.)", None, {"SP", "SAO PAULO"}),
        ("Belo Horizonte (RMBH aprox.)", None, {"MINAS GERAIS", "MG"}),
    ],
}


def normalize(value: str | None) -> str:
    text = " ".join((value or "").split()).upper()
    stripped = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in stripped if not unicodedata.combining(ch))


def classify(country: str, city: str, state: str) -> str:
    city = CITY_TYPOS.get(city, city)
    for label, cities, states in METRO_RULES.get(country, []):
        if cities is not None and city in cities:
            return label
        if states is not None and state in states:
            return label
    if not country:
        return "(sin país)"
    return f"{country} – otras"


def load_rows(version: str) -> list[dict[str, str]]:
    path = RAW_DIR / version / "participant_locations.csv"
    if not path.exists():
        sys.exit(f"No existe {path}. ¿Versión correcta? (--version)")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--write", action="store_true", help="escribe el CSV interim")
    args = parser.parse_args()

    rows = load_rows(args.version)
    total = len(rows)

    metro_counts: Counter[tuple[str, str]] = Counter()
    city_counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        country = COUNTRY_LABELS.get(normalize(row.get("Country")), normalize(row.get("Country")))
        city = normalize(row.get("City"))
        state = normalize(row.get("State"))
        metro = classify(country, city, state)
        metro_counts[(country, metro)] += 1
        city_counts[(country, metro, CITY_TYPOS.get(city, city))] += 1

    print(f"Total participantes: {total}\n")
    print(f"{'País':<12}{'Metro':<40}{'n':>6}{'%':>8}")
    print("-" * 66)
    for (country, metro), n in metro_counts.most_common():
        print(f"{country or '—':<12}{metro:<40}{n:>6}{100 * n / total:>7.1f}%")

    if args.write:
        INTERIM_CSV.parent.mkdir(parents=True, exist_ok=True)
        with INTERIM_CSV.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["country", "metro", "city_normalized", "n"])
            for (country, metro, city), n in sorted(
                city_counts.items(), key=lambda item: (-item[1], item[0])
            ):
                writer.writerow([country, metro, city, n])
        print(f"\nEscrito {INTERIM_CSV.relative_to(ROOT)} ({len(city_counts)} filas)")


if __name__ == "__main__":
    main()
