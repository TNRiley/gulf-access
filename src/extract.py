"""Pull what the build needs out of the Geofabrik Florida extract.

Writes raw/osm_extract.pkl with:
  canals    list of (way_id, kind, name, tags_subset, [(lon, lat), ...])   waterway=canal|ditch|drain
  res_pts   float32 (N, 2) lon/lat of every vertex of every highway=residential way
  barriers  list of (lon, lat, kind)   weirs, dams, lock gates (nodes, and way vertices)
  coast     list of [(lon, lat), ...]  natural=coastline ways
  places    list of (lon, lat, name, place, population)
  rivers    list of (way_id, kind, name, [(lon, lat), ...])   waterway=river|stream|tidal_channel
  canal_polys  outer rings of natural=water + water=canal areas (ways only)
"""
import os, pickle, sys
import numpy as np
import osmium

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
PBF = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAW, "florida-261110.osm.pbf")

WATER = {"canal", "ditch", "drain"}
NATURAL = {"river", "stream", "tidal_channel"}
BARRIER = {"weir", "dam", "lock_gate", "sluice_gate", "floodgate"}
KEEP = ("tidal", "boat", "motorboat", "intermittent", "tunnel", "width", "salt", "lock")


def densify(pts, step=0.0003):
    """Add a vertex every ~30 m so a long straight street is not two points."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        d = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        k = int(d / step)
        for i in range(1, k + 1):
            f = i / (k + 1)
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        out.append(b)
    return out


def main():
    canals, res, barriers, coast, places, wpoly, rivers = [], [], [], [], [], [], []
    fp = (
        osmium.FileProcessor(PBF)
        .with_locations()
        .with_filter(osmium.filter.KeyFilter("waterway", "highway", "natural", "place"))
    )
    n = 0
    for o in fp:
        n += 1
        if o.is_node():
            t = o.tags
            w = t.get("waterway")
            if w in BARRIER:
                barriers.append((o.location.lon, o.location.lat, w))
            p = t.get("place")
            if p in ("city", "town", "village", "suburb") and t.get("name"):
                places.append((o.location.lon, o.location.lat, t.get("name"), p, t.get("population", "")))
        elif o.is_way():
            t = o.tags
            w = t.get("waterway")
            h = t.get("highway")
            if t.get("natural") == "water" and t.get("water") == "canal":
                try:
                    wpoly.append([(nd.location.lon, nd.location.lat) for nd in o.nodes if nd.location.valid()])
                except Exception:
                    pass
                continue
            if w in WATER or w in NATURAL or w in BARRIER or h == "residential" or t.get("natural") == "coastline":
                try:
                    pts = [(nd.location.lon, nd.location.lat) for nd in o.nodes if nd.location.valid()]
                except Exception:
                    continue
                if len(pts) < 2:
                    continue
                if w in WATER:
                    canals.append((o.id, w, t.get("name", ""), {k: t.get(k) for k in KEEP if k in t}, pts))
                elif w in NATURAL:
                    rivers.append((o.id, w, t.get("name", ""), pts))
                elif w in BARRIER:
                    for p in pts:
                        barriers.append((p[0], p[1], w))
                elif h == "residential":
                    res.extend(densify(pts))
                else:
                    coast.append(pts)
    out = dict(
        canals=canals,
        res_pts=np.array(res, dtype=np.float32),
        barriers=barriers,
        coast=coast,
        places=places,
        canal_polys=wpoly,
        rivers=rivers,
    )
    with open(os.path.join(RAW, "osm_extract.pkl"), "wb") as f:
        pickle.dump(out, f, protocol=4)
    kinds = {}
    for c in canals:
        kinds[c[1]] = kinds.get(c[1], 0) + 1
    print("objects seen", n)
    print("waterways", kinds)
    print("residential vertices", len(res), "barriers", len(barriers), "coast ways", len(coast), "places", len(places), "canal polygons", len(wpoly), "rivers", len(rivers))


if __name__ == "__main__":
    main()
