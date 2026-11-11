"""Shape everything the page needs into payload.json.

  comps    one row per connected piece of narrow water (every piece that passes the
           shape test in a Gulf county, residential or not: the page applies the
           residential and canal rules itself, so its controls are live)
  plates   eight map plates: elevation raster + water-class raster
  outline  the 22 Gulf-county outlines, for the coast map
  sea      per-tile level of wide open water, for the "what is sea level here" control
Typed arrays are base64 inside the JSON; inject.py gzips the lot.
"""
import base64, json, os, pickle
import numpy as np
import shapely
from shapely.geometry import shape

import plates as platemod

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
GULF = ["Escambia", "Santa Rosa", "Okaloosa", "Walton", "Bay", "Gulf", "Franklin", "Wakulla",
        "Jefferson", "Taylor", "Dixie", "Levy", "Citrus", "Hernando", "Pasco", "Pinellas",
        "Hillsborough", "Manatee", "Sarasota", "Charlotte", "Lee", "Collier"]
MARINE = {"ESTUARY", "COASTAL", "BEACH"}
FRESH = {"STREAM", "LAKE", "SPRING"}
TIDAL_MAX = 0.6


def b64(a, dt):
    return base64.b64encode(np.ascontiguousarray(a.astype(dt)).tobytes()).decode("ascii")


def pct(a):
    return np.clip(np.round(a * 100), 0, 100)


def main():
    c = np.load(os.path.join(RAW, "components.npz"))
    nm = json.load(open(os.path.join(RAW, "names.json"), encoding="utf-8"))
    ok = c["shape_ok"]
    idx = np.nonzero(ok)[0]
    L = c["L"][idx]

    county = np.array([GULF.index(nm["counties"][i]) for i in c["county"][idx]])
    pl_raw = c["place"][idx]
    used = sorted(set(pl_raw[pl_raw >= 0].tolist()), key=lambda i: nm["places"][i])
    pmap = {i: k for k, i in enumerate(used)}
    place = np.array([pmap.get(int(i), 65535) for i in pl_raw])
    wb_raw = c["wb"][idx]
    wused = sorted(set(wb_raw[wb_raw >= 0].tolist()))
    wmap = {i: k for k, i in enumerate(wused)}
    wb = np.array([wmap.get(int(i), 65535) for i in wb_raw])
    dep = np.array([0 if i < 0 else (1 if nm["wbids"][i][2] in MARINE else 2 if nm["wbids"][i][2] in FRESH else 0)
                    for i in wb_raw])
    street = np.where(np.isfinite(c["street"][idx]), np.round(c["street"][idx] * 100), -32768)

    comps = dict(
        n=int(len(idx)),
        L=b64(L, "<f4"), w=b64(np.clip(np.round(c["width"][idx]), 0, 255), "u1"),
        lv=b64(np.round(c["level"][idx] * 100), "<i2"), bk=b64(np.round(c["bank"][idx] * 100), "<i2"),
        st=b64(street, "<i2"),
        ru=b64(pct(c["f_ruled"][idx]), "u1"), res=b64(pct(c["f_res"][idx]), "u1"),
        nat=b64(pct(c["f_nat"][idx]), "u1"), can=b64(pct(c["f_can"][idx]), "u1"),
        cst=b64(pct(c["f_coast"][idx]), "u1"), flt=b64(pct(c["f_flat"][idx]), "u1"),
        co=b64(county, "u1"), pl=b64(place, "<u2"), wb=b64(wb, "<u2"), dep=b64(dep, "u1"),
        lon=b64(c["lon"][idx], "<f4"), lat=b64(c["lat"][idx], "<f4"),
    )
    names = dict(
        counties=GULF,
        places=[nm["places"][i] for i in used],
        wb=[[nm["wbids"][i][0], nm["wbids"][i][1].title(), nm["wbids"][i][2]] for i in wused],
    )

    # --- plates. Class per component under the page's default canal rule.
    canal = c["kept"] & (c["f_nat"] < 0.5) & ((c["L"] >= 2000) | (c["f_ruled"] >= 0.5))
    other = c["kept"] & ~canal
    cc = np.zeros(len(c["L"]), np.uint8)
    cc[canal & (c["level"] <= TIDAL_MAX)] = 2
    cc[canal & (c["level"] > TIDAL_MAX)] = 3
    fresh = np.array([i >= 0 and nm["wbids"][i][2] in FRESH for i in c["wb"]])
    cc[canal & (c["level"] <= TIDAL_MAX) & fresh] = 5
    cc[other] = 4
    pix = dict(np.load(os.path.join(RAW, "pixels.npz")))
    pl = []
    for p in platemod.build(pix, cc):
        pl.append(dict(name=p["name"], w=p["w"], h=p["h"], px=p["px"], e0=p["e0"], n1=p["n1"],
                       z=b64(p["z"], "u1"), c=b64(p["c"], "u1")))

    # --- outlines
    cs = json.load(open(os.path.join(RAW, "fl_counties.geojson"), encoding="utf-8"))
    rings = []
    for f in cs["features"]:
        g = shape(f["geometry"]).simplify(0.004)
        isg = f["properties"]["NAME"].replace(" County", "") in GULF
        for poly in getattr(g, "geoms", [g]):
            xy = np.asarray(poly.exterior.coords, np.float32)
            if len(xy) >= 4:
                rings.append(dict(g=int(isg), xy=b64(xy.ravel(), "<f4")))

    # --- sea-level control
    sea = pickle.load(open(os.path.join(RAW, "sea.pkl"), "rb"))
    edges = np.arange(-2, 6.0001, 0.02)
    rows = []
    for (i, j), (h, frac) in sorted(sea.items()):
        if h.sum() < 2000:          # under 5 hectares of wide water: no reading
            continue
        m = int(h.argmax())
        rows.append((i, j, int(round(edges[m] * 100)) + 2, int(h[m]), int(h.sum())))
    seaj = dict(n=len(rows), i=[r[0] for r in rows], j=[r[1] for r in rows], cm=[r[2] for r in rows],
                top=[r[3] for r in rows], all=[r[4] for r in rows])

    meta = dict(
        tiles=len(sea), tile_km=10, px=5, tidal_max_cm=int(TIDAL_MAX * 100),
        narrow_km=33834, zmin=platemod.ZMIN, zstep=platemod.ZSTEP,
        osm_date="2026-11-10", built="2026-11-11",
    )
    out = dict(meta=meta, comps=comps, names=names, plates=pl, outline=rings, sea=seaj)
    path = os.path.join(HERE, "payload.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, separators=(",", ":"))
    print("payload %.2f MB, %d components, %d plates" % (os.path.getsize(path) / 1e6, len(idx), len(pl)))


if __name__ == "__main__":
    main()
