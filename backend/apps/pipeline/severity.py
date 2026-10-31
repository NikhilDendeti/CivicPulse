"""Deterministic severity adjustment on top of the model's evidence-only score (FR-6).
Every modifier is recorded in `factors` so the score is explainable and testable."""
from . import clients

MAJOR_ROADS = {"motorway": 10, "trunk": 10, "primary": 8, "secondary": 5, "tertiary": 3}
ROAD_CATEGORIES = {"road_damage", "streetlight", "drainage", "water_leak"}
RAIN_CATEGORIES = {"drainage", "water_leak", "road_damage"}


def level_for(score):
    if score >= 78:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def apply_context(category, base, lat, lng, fetch=True):
    """Returns (score, level, factor_notes). Context lookups are best-effort and noted when unavailable."""
    score = int(base)
    notes = [f"Model severity from evidence: {base}/100"]
    if not fetch:
        return score, level_for(score), notes

    sites = clients.nearby_sensitive_sites(lat, lng)
    if sites is None:
        notes.append("Nearby schools/hospitals: lookup unavailable")
    elif sites:
        kinds = sorted({s["kind"] for s in sites if s.get("kind")})
        score += 10
        notes.append(f"+10 near {', '.join(kinds)} (within 200 m, OpenStreetMap)")

    if category in ROAD_CATEGORIES:
        rc = clients.road_class(lat, lng)
        if rc in MAJOR_ROADS:
            score += MAJOR_ROADS[rc]
            notes.append(f"+{MAJOR_ROADS[rc]} on a {rc} road (OpenStreetMap)")
        elif rc is None:
            notes.append("Road class: lookup unavailable")

    if category in RAIN_CATEGORIES:
        rain = clients.current_precipitation_mm(lat, lng)
        if rain is None:
            notes.append("Weather: lookup unavailable")
        elif rain >= 1.0:
            score += 7
            notes.append(f"+7 active rainfall ({rain:.1f} mm, Open-Meteo)")

    score = max(0, min(100, score))
    return score, level_for(score), notes
