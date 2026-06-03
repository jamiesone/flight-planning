"""Geometry helpers — WGS84 in, no external GIS dependency.

Simple version, just enough to answer "is this airspace within the reachability disk?" 
Three shape-matched tests:

  * polygon zones  -> exact disk/polygon intersection (`geom_within_disk`)
  * circle NOTAMs  -> exact circle/circle intersection (`circle_within_disk`)
  * named-area NOTAMs have no geometry of their own; the caller inherits their
    reach from the airspace they activate.

A circle overlaps a filled polygon iff the shortest distance from the circle
centre to the polygon is <= the radius. That distance is 0 when the centre is
inside the polygon, otherwise the minimum point-to-edge distance. We project
lon/lat into a local planar frame (km, centred on the query point) for the
segment math; over a ~50 km disk at Swiss latitudes the equirectangular
distortion is well under 0.1%.
"""
from __future__ import annotations
import math
from typing import Iterable

EARTH_R_KM = 6371.0088
KM_PER_DEG_LAT = 110.574


def iter_coords(geom: dict) -> Iterable[tuple[float, float]]:
    """Yield every (lon, lat) vertex of a GeoJSON geometry, any nesting depth."""
    def walk(c):
        if c and isinstance(c[0], (int, float)):
            yield c[0], c[1]
        else:
            for x in c:
                yield from walk(x)
    yield from walk(geom["coordinates"])


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def _to_local_km(lon: float, lat: float, c_lon: float, c_lat: float) -> tuple[float, float]:
    """Equirectangular projection to km, relative to (c_lon, c_lat) as origin."""
    kx = KM_PER_DEG_LAT * math.cos(math.radians(c_lat))
    return (lon - c_lon) * kx, (lat - c_lat) * KM_PER_DEG_LAT


def _rings(geom: dict):
    """Yield exterior rings (coord lists) of a Polygon/MultiPolygon."""
    t = geom["type"]
    if t == "Polygon":
        yield geom["coordinates"][0]
    elif t == "MultiPolygon":
        for poly in geom["coordinates"]:
            yield poly[0]


def point_in_polygon(lon: float, lat: float, geom: dict) -> bool:
    """Ray-casting point-in-polygon over a GeoJSON Polygon/MultiPolygon."""
    inside = False
    for ring in _rings(geom):
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if (yi > lat) != (yj > lat):
                x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
                if lon < x_cross:
                    inside = not inside
            j = i
    return inside


def _pt_seg_dist(px: float, py: float, ax: float, ay: float,
                 bx: float, by: float) -> float:
    """Distance from point (px,py) to segment (ax,ay)-(bx,by), planar.

    t locates the perpendicular foot on the infinite line; clamping it to [0,1]
    keeps the nearest point on the segment (t<=0 -> A, t>=1 -> B, else interior)."""
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _min_edge_dist_km(geom: dict, c_lon: float, c_lat: float) -> float:
    """Min distance (km) from (c_lon,c_lat) to any polygon edge. The query point
    is the origin after projection; edge i->(i+1)%n so the ring always closes."""
    best = math.inf
    for ring in _rings(geom):
        pts = [_to_local_km(lon, lat, c_lon, c_lat) for lon, lat in ring]
        n = len(pts)
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            best = min(best, _pt_seg_dist(0.0, 0.0, ax, ay, bx, by))
    return best


def geom_within_disk(geom: dict, c_lon: float, c_lat: float, radius_km: float) -> bool:
    """Exact disk/geometry intersection.

    Polygon: true iff the query point is inside it (distance 0) OR the nearest
    edge passes within `radius_km` — full segment-circle test, no vertex blind
    spot. Point/LineString fall back to nearest-vertex distance.
    """
    if geom["type"] in ("Polygon", "MultiPolygon"):
        if point_in_polygon(c_lon, c_lat, geom):
            return True
        return _min_edge_dist_km(geom, c_lon, c_lat) <= radius_km
    return any(haversine_km(c_lon, c_lat, lon, lat) <= radius_km
               for lon, lat in iter_coords(geom))


def min_distance_km(geom: dict, c_lon: float, c_lat: float) -> float:
    """Nearest distance (km) from (c_lon,c_lat) to the geometry; 0 if inside a
    polygon. True edge distance for polygons, vertex distance otherwise."""
    if geom["type"] in ("Polygon", "MultiPolygon"):
        if point_in_polygon(c_lon, c_lat, geom):
            return 0.0
        return _min_edge_dist_km(geom, c_lon, c_lat)
    return min(haversine_km(c_lon, c_lat, lon, lat) for lon, lat in iter_coords(geom))


def circles_intersect(lon1: float, lat1: float, r1_km: float,
                      lon2: float, lat2: float, r2_km: float) -> bool:
    """Two circles overlap iff centre distance <= sum of radii (exact)."""
    return haversine_km(lon1, lat1, lon2, lat2) <= r1_km + r2_km


def circle_within_disk(n_lon: float, n_lat: float, n_radius_km: float,
                       c_lon: float, c_lat: float, reach_km: float) -> bool:
    """Reachability test for a circle NOTAM against the reachability disk."""
    return circles_intersect(n_lon, n_lat, n_radius_km, c_lon, c_lat, reach_km)
