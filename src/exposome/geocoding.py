"""Resolve user input to coordinates, outside the exposure sampler.

Kept deliberately separate from :mod:`exposome.point_query` and
:mod:`exposome.point_extraction`: a postal area is not a unique point, and the
sampler must stay a pure ``coordinate -> value`` function (ADR 0012 §7).

Three input forms are supported.  ``lat/lon`` is first class and transmits
nothing.  An address is sent to a provider only behind an explicit opt-in.  A
postal code resolves to an administrative unit from a **local, reproducible
reference file** -- never to an invented centroid -- which today means it
reports ``unsupported_country`` for every country in the repo.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

USER_AGENT = "BrainLat-Exposome/1.0 (https://github.com/brainlat; exposome pipeline)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

#: Nominatim's usage policy allows at most one request per second.
MIN_REQUEST_INTERVAL_S = 1.0

KIND_LATLON = "latlon"
KIND_ADDRESS = "address"
KIND_POSTAL = "postal"
KIND_EMPTY = "empty"

PRECISION_EXACT = "latlon_exact"
PRECISION_ROOFTOP = "rooftop"
PRECISION_STREET = "street"
PRECISION_LOCALITY = "locality_centroid"
PRECISION_UNKNOWN = "unknown"

# Postal-code shapes per country.  They are only used to *classify* a line the
# user already told us the country for; nothing here implies we can resolve it.
POSTAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "CL": re.compile(r"^\d{7}$"),
    "MX": re.compile(r"^\d{5}$"),
    "ES": re.compile(r"^\d{5}$"),
    "PE": re.compile(r"^\d{5}$"),
    "CO": re.compile(r"^\d{6}$"),
    "BR": re.compile(r"^\d{5}-?\d{3}$"),
    # Argentina's CPA is a letter, four digits and three letters; the legacy
    # four-digit form is still written by hand.
    "AR": re.compile(r"^([A-Z]\d{4}[A-Z]{3}|\d{4})$", re.IGNORECASE),
}

_LATLON = re.compile(
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$"
)
_COUNTRY_PREFIX = re.compile(r"^\s*([A-Z]{2})[\s:]+(.+)$", re.IGNORECASE)


class GeocodingError(RuntimeError):
    """The provider could not be reached or returned something unusable."""


@dataclass(frozen=True)
class ClassifiedInput:
    raw: str
    kind: str
    lon: float | None = None
    lat: float | None = None
    postal_code: str | None = None
    country: str | None = None
    note: str | None = None


@dataclass
class GeocodeResult:
    query: str
    lon: float | None
    lat: float | None
    precision: str
    accuracy_m: float | None
    provider: str
    matched_address: str | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_input(line: str, postal_country: str | None = None) -> ClassifiedInput:
    """Decide whether a pasted line is coordinates, a postal code or an address.

    A bare five-digit number is ambiguous between MX, ES and PE, so the country
    for postal lines is **declared**, never inferred -- either as a two-letter
    prefix (``MX 06700``) or via ``postal_country``.  Coordinates must use a dot
    decimal separator: with a comma the string is ambiguous against the
    separator itself.
    """
    raw = (line or "").strip()
    if not raw:
        return ClassifiedInput(raw=raw, kind=KIND_EMPTY)

    match = _LATLON.match(raw)
    if match:
        first, second = float(match.group(1)), float(match.group(2))
        # "lat, lon" is the convention people paste from map apps.
        lat, lon = first, second
        if abs(lat) > 90 and abs(lon) <= 90:
            lat, lon = lon, lat  # tolerate the reversed order when unambiguous
        if abs(lat) > 90 or abs(lon) > 180:
            return ClassifiedInput(raw=raw, kind=KIND_ADDRESS,
                                   note="looks like coordinates but is out of range")
        return ClassifiedInput(raw=raw, kind=KIND_LATLON, lon=lon, lat=lat)

    candidate, country = raw, (postal_country or "").upper() or None
    prefixed = _COUNTRY_PREFIX.match(raw)
    if prefixed and prefixed.group(1).upper() in POSTAL_PATTERNS:
        country = prefixed.group(1).upper()
        candidate = prefixed.group(2).strip()

    if country and country in POSTAL_PATTERNS:
        if POSTAL_PATTERNS[country].match(candidate.replace(" ", "")):
            return ClassifiedInput(
                raw=raw, kind=KIND_POSTAL,
                postal_code=candidate.replace(" ", "").upper(), country=country,
            )
    return ClassifiedInput(raw=raw, kind=KIND_ADDRESS, country=country)


def _precision_from_nominatim(payload: Mapping[str, Any]) -> str:
    address_type = str(payload.get("addresstype") or payload.get("type") or "").lower()
    category = str(payload.get("class") or "").lower()
    if address_type in {"house", "building", "residential"} or category == "building":
        return PRECISION_ROOFTOP
    if address_type in {"road", "street", "footway", "residential_road"}:
        return PRECISION_STREET
    if address_type in {"suburb", "neighbourhood", "city", "town", "village",
                        "municipality", "state", "county", "administrative"}:
        return PRECISION_LOCALITY
    return PRECISION_UNKNOWN


def _accuracy_from_bbox(payload: Mapping[str, Any]) -> float | None:
    """Half the diagonal of the provider's own bounding box, in metres.

    Using the provider's uncertainty rather than a guess keeps
    ``geocode_accuracy_m`` comparable to ``support_m`` downstream.
    """
    box = payload.get("boundingbox")
    if not box or len(box) != 4:
        return None
    try:
        south, north, west, east = (float(value) for value in box)
    except (TypeError, ValueError):
        return None
    mid_lat = (south + north) / 2
    metres_per_degree = 111_320.0
    height = abs(north - south) * metres_per_degree
    width = abs(east - west) * metres_per_degree * max(_cos(mid_lat), 1e-6)
    return float(((height**2 + width**2) ** 0.5) / 2)


def _cos(degrees: float) -> float:
    import math

    return math.cos(math.radians(degrees))


class NominatimGeocoder:
    """OpenStreetMap's geocoder: no key, but a strict usage policy.

    ``viewbox`` + ``bounded`` + ``countrycodes`` are set from the study's own
    bounding box whenever one is known.  Without them Latin American street
    matches drift badly and a mistyped city can land on another continent.
    """

    name = "nominatim"

    def __init__(
        self,
        *,
        transport: Callable[[str, dict[str, str], dict[str, str]], Any] | None = None,
        cache_dir: Path | None = None,
        min_interval_s: float = MIN_REQUEST_INTERVAL_S,
        user_agent: str = USER_AGENT,
    ) -> None:
        self._transport = transport or _requests_transport
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._min_interval_s = float(min_interval_s)
        self._user_agent = user_agent
        self._last_request_at = 0.0
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path | None:
        if not self._cache_dir:
            return None
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.json"

    def _throttle(self) -> None:
        if self._min_interval_s <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval_s:
            time.sleep(self._min_interval_s - elapsed)
        self._last_request_at = time.monotonic()

    def geocode(
        self,
        query: str,
        *,
        country_code: str | None = None,
        viewbox: tuple[float, float, float, float] | None = None,
    ) -> GeocodeResult:
        params: dict[str, str] = {"q": query, "format": "jsonv2", "limit": "1",
                                  "addressdetails": "1"}
        if country_code:
            params["countrycodes"] = country_code.lower()
        if viewbox:
            west, south, east, north = viewbox
            params["viewbox"] = f"{west},{north},{east},{south}"
            params["bounded"] = "1"

        cache_key = json.dumps(params, sort_keys=True)
        cache_path = self._cache_path(cache_key)
        if cache_path and cache_path.exists():
            return GeocodeResult(**json.loads(cache_path.read_text()))

        self._throttle()
        try:
            payloads = self._transport(
                NOMINATIM_URL, params, {"User-Agent": self._user_agent}
            )
        except Exception as error:  # noqa: BLE001 - provider failures are data
            return GeocodeResult(query=query, lon=None, lat=None,
                                 precision=PRECISION_UNKNOWN, accuracy_m=None,
                                 provider=self.name, error=str(error))

        result = self._to_result(query, payloads)
        if cache_path and result.error is None:
            cache_path.write_text(json.dumps(result.as_dict(), ensure_ascii=False))
        return result

    def _to_result(self, query: str, payloads: Any) -> GeocodeResult:
        if not payloads:
            return GeocodeResult(query=query, lon=None, lat=None,
                                 precision=PRECISION_UNKNOWN, accuracy_m=None,
                                 provider=self.name, error="no_match")
        best = payloads[0] if isinstance(payloads, list) else payloads
        try:
            lon = float(best["lon"])
            lat = float(best["lat"])
        except (KeyError, TypeError, ValueError):
            return GeocodeResult(query=query, lon=None, lat=None,
                                 precision=PRECISION_UNKNOWN, accuracy_m=None,
                                 provider=self.name, error="malformed_response")
        return GeocodeResult(
            query=query,
            lon=lon,
            lat=lat,
            precision=_precision_from_nominatim(best),
            accuracy_m=_accuracy_from_bbox(best),
            provider=self.name,
            matched_address=best.get("display_name"),
            raw={key: best.get(key) for key in ("class", "type", "addresstype")},
        )


def _requests_transport(url: str, params: dict[str, str], headers: dict[str, str]):
    import requests

    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def resolve_postal_code(
    postal_code: str,
    country: str,
    reference_dir: Path | None = None,
) -> dict[str, Any]:
    """Resolve a postal code from a local reference file, or say why we cannot.

    A postal code is an **area**, not a coordinate.  Resolving one to a centroid
    would carry every bias of the modifiable areal unit problem without
    declaring it, so this returns a unit reference or an explicit refusal.

    No reference exists for any country in the repo today, so in practice this
    reports ``unsupported_country`` everywhere.  That is the honest answer, and
    it is why the tab offers address and lat/lon first.
    """
    country = (country or "").upper()
    if country not in POSTAL_PATTERNS:
        return {"status": "unsupported_country", "country": country,
                "postal_code": postal_code, "reason": "no postal pattern configured"}
    if reference_dir is None:
        return {"status": "unsupported_country", "country": country,
                "postal_code": postal_code,
                "reason": "no local postal reference is vendored for this country"}
    reference = Path(reference_dir) / country.lower() / "postal_units.json"
    if not reference.exists():
        return {"status": "unsupported_country", "country": country,
                "postal_code": postal_code, "reason": f"missing reference {reference}"}
    records = json.loads(reference.read_text()).get("records", {})
    entry = records.get(postal_code)
    if not entry:
        return {"status": "not_found", "country": country, "postal_code": postal_code,
                "reason": "code absent from the local reference"}
    return {"status": "resolved", "country": country, "postal_code": postal_code,
            "spatial_id": entry.get("spatial_id"), "spatial_name": entry.get("spatial_name"),
            "support": "administrative_unit"}


def geocode_lines(
    lines: list[str],
    *,
    geocoder: NominatimGeocoder | None = None,
    postal_country: str | None = None,
    country_code: str | None = None,
    viewbox: tuple[float, float, float, float] | None = None,
    allow_network: bool = False,
) -> list[dict[str, Any]]:
    """Turn pasted lines into coordinate rows, geocoding only when allowed.

    ``allow_network`` defaults to False so nothing leaves the machine unless a
    caller opts in.  Coordinate lines never need it.
    """
    resolved: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        classified = classify_input(line, postal_country)
        row: dict[str, Any] = {
            "query_id": f"point_{index + 1:04d}",
            "input_raw": classified.raw,
            "input_kind": classified.kind,
            "lon": classified.lon,
            "lat": classified.lat,
            "geocode_precision": None,
            "geocode_accuracy_m": None,
            "geocode_provider": None,
            "matched_address": None,
            "status": None,
        }
        if classified.kind == KIND_LATLON:
            row.update(geocode_precision=PRECISION_EXACT, geocode_accuracy_m=0.0,
                       geocode_provider="input", status="ok")
        elif classified.kind == KIND_POSTAL:
            outcome = resolve_postal_code(classified.postal_code, classified.country)
            row.update(status=outcome["status"], matched_address=outcome.get("reason"))
        elif classified.kind == KIND_ADDRESS:
            if not allow_network or geocoder is None:
                row["status"] = "geocoding_not_enabled"
            else:
                result = geocoder.geocode(
                    classified.raw, country_code=country_code, viewbox=viewbox
                )
                row.update(
                    lon=result.lon, lat=result.lat,
                    geocode_precision=result.precision,
                    geocode_accuracy_m=result.accuracy_m,
                    geocode_provider=result.provider,
                    matched_address=result.matched_address,
                    status="ok" if result.lon is not None else (result.error or "no_match"),
                )
        else:
            row["status"] = "empty"
        resolved.append(row)
    return resolved
