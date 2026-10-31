"""Pure-Python geometry helpers (shapely + haversine); no GDAL needed."""
import math
from functools import lru_cache

from shapely.geometry import Point, shape


def haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=512)
def _shape_from_json(geometry_json: str):
    import json

    return shape(json.loads(geometry_json))


def point_in_geometry(geometry, lat, lng):
    """geometry is a GeoJSON geometry dict. Returns True when (lat, lng) lies inside it."""
    if not geometry:
        return False
    import json

    try:
        geom = _shape_from_json(json.dumps(geometry, sort_keys=True))
    except Exception:
        return False
    return geom.covers(Point(lng, lat))


def find_ward(lat, lng):
    from .models import Ward

    for ward in Ward.objects.all():
        if point_in_geometry(ward.geometry, lat, lng):
            return ward
    return None


def authorities_for(category, lat, lng):
    """Authorities handling `category` whose jurisdiction covers the point (or has none = whole area)."""
    from .models import Authority

    out = []
    for a in Authority.objects.prefetch_related("channels"):
        if category not in (a.categories or []):
            continue
        if a.jurisdiction and not point_in_geometry(a.jurisdiction, lat, lng):
            continue
        out.append(a)
    return out
