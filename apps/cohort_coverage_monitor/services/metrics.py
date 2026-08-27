from typing import Dict, Any, List
from collections import Counter
from apps.cohort_coverage_monitor.domain.models import PublicSnapshot

def calculate_summary_metrics(snapshot: PublicSnapshot) -> Dict[str, Any]:
    """Calculates high-level metrics for the summary cards."""
    total_participants = snapshot.total_participants
    priority_participants = snapshot.priority_participants
    
    # Geographic coverage (n >= 25 cities out of total)
    priority_coverage_pct = (priority_participants / total_participants * 100) if total_participants > 0 else 0
    
    # Visible in GEMMA (production or preview)
    visible_participants = sum(
        c.participants for c in snapshot.cities if c.publication_tier in ("production", "preview")
    )
    visible_coverage_pct = (visible_participants / total_participants * 100) if total_participants > 0 else 0
    
    # Status breakdown (number of cities)
    cities_by_status = Counter(c.status for c in snapshot.cities)

    # Number of published cities (status == "published")
    published_cities = cities_by_status.get("published", 0)
    running_cities = cities_by_status.get("running", 0)
    remaining_cities = (
        cities_by_status.get("preparing", 0)
        + cities_by_status.get("pending", 0)
        + cities_by_status.get("blocked", 0)
    )

    # Unique available exposomes across all cities
    unique_exposomes = set()
    for c in snapshot.cities:
        unique_exposomes.update(c.available_exposomes)
        
    return {
        "total_participants": total_participants,
        "priority_participants": priority_participants,
        "priority_coverage_pct": priority_coverage_pct,
        "visible_participants": visible_participants,
        "visible_coverage_pct": visible_coverage_pct,
        "cities_by_status": dict(cities_by_status),
        "published_cities": published_cities,
        "running_cities": running_cities,
        "remaining_cities": remaining_cities,
        "unique_exposomes_count": len(unique_exposomes),
    }

def get_participants_by_status(snapshot: PublicSnapshot) -> Dict[str, int]:
    """Returns total participants per operational status."""
    counts = Counter()
    for c in snapshot.cities:
        counts[c.status] += c.participants
    return dict(counts)

def get_participants_by_tier(snapshot: PublicSnapshot) -> Dict[str, int]:
    """Returns total participants per publication tier."""
    counts = Counter()
    for c in snapshot.cities:
        counts[c.publication_tier] += c.participants
        
    # The remainder of the total cohort is not in these priority cities
    # We should add them to "none" if we want the sum to equal total_participants
    # But for simplicity, we only count the cities in the snapshot.
    # Actually, as per the original cohort_reporting, non-priority cities are "none".
    accounted_participants = sum(counts.values())
    unaccounted = snapshot.total_participants - accounted_participants
    if unaccounted > 0:
        counts["none"] += unaccounted
        
    return dict(counts)
