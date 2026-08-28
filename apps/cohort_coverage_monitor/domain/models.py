from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json

@dataclass
class CitySnapshot:
    id: str
    metro: str
    country: str
    lat: float
    lon: float
    participants: int
    pct_total: float
    status: str
    publication_tier: str
    available_exposomes_count: int
    expected_exposomes_count: int
    available_exposomes: List[str]
    rank: int
    next_action: Optional[str] = None

@dataclass
class PublicSnapshot:
    total_participants: int
    priority_participants: int
    minimum_participants: int
    updated_at: str
    snapshot_generated_at: str
    cities: List[CitySnapshot]
    catalog_created_utc: Optional[str] = None

    def to_json(self, indent=2):
        return json.dumps(asdict(self), indent=indent)
    
    @classmethod
    def from_dict(cls, data):
        cities_data = data.pop("cities", [])
        cities = [CitySnapshot(**c) for c in cities_data]
        return cls(cities=cities, **data)
