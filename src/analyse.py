"""Turn the per-tile skeleton pixels into canals, and classify them.

Reads raw/skel/*.npz (process_tiles.py), raw/osm_extract.pkl (extract.py),
raw/wbid.geojson (fetch_wbid.py), raw/fl_counties.geojson, raw/fl_places.geojson.
Writes raw/components.npz (one row per connected piece of narrow water) and
raw/pixels.npz (the kept skeleton pixels with their component id and class).

A "residential canal" here is a connected piece of narrow water that is
  - at least MIN_LEN long and at least MIN_ELONG times longer than it is wide
    (so a retention pond is not a canal),
  - cut at least MIN_FREEBOARD below the ground beside it,
  - for at least half its length within RES_M of a residential street.
Pieces OpenStreetMap calls a river or stream for half their length or more are
kept, labelled, and left out of the canal totals.
"""
import glob, json, os, pickle
import numpy as np
import pyproj
import shapely
from scipy import sparse
from scipy.sparse import csgraph
from scipy.spatial import cKDTree
from shapely.geometry import shape

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
PX = 5.0
K = 1 << 21

MIN_LEN = 150.0
MIN_ELONG = 6.0
MIN_FREEBOARD = 0.3
RES_M = 120.0
OSM_M = 40.0
COAST_PAD = 20.0
RULED = 0.75       # a skeleton pixel is "ruled" if its bank-orientation coherence is at least this
GULF = ["Escambia", "Santa Rosa", "Okaloosa", "Walton", "Bay", "Gulf", "Franklin", "Wakulla",
        "Jefferson", "Taylor", "Dixie", "Levy", "Citrus", "Hernando", "Pasco", "Pinellas",
        "Hillsborough", "Manatee", "Sarasota", "Charlotte", "Lee", "Collier"]


def load_pixels():
    cols = {k: [] for k in ("gx", "gy", "level", "width", "bank", "ruler", "step", "flat")}
    sea = {}
    for f in sorted(glob.glob(os.path.join(RAW, "skel", "*.npz"))):
        z = np.load(f)
        for k in cols:
            cols[k].append(z[k])
        i, j = os.path.basename(f)[:-4].split("_")
        sea[(int(i), int(j))] = (z["sea"], z["frac"])
    return {k: np.concatenate(v) for k, v in cols.items()}, sea


def components(gx, gy):
    """Label skeleton pixels; two pixels join if they are within 2 px (Chebyshev)."""
    key = gy.astype(np.int64) * K + gx.astype(np.int64)
    order = np.argsort(key)
    sk = key[order]
    n = len(key)
    rows, colz = [], []
    for dy in range(0, 3):
        for dx in range(-2, 3):
            if dy == 0 and dx <= 0:
                continue
            tgt = sk + dy * K + dx
            pos = np.searchsorted(sk, tgt)
            pos[pos >= n] = n - 1
            hit = sk[pos] == tgt
            rows.append(order[np.nonzero(hit)[0]])
            colz.append(order[pos[hit]])
    r = np.concatenate(rows)
    c = np.concatenate(colz)
    g = sparse.coo_matrix((np.ones(len(r), np.int8), (r, c)), shape=(n, n))
    ncomp, lab = csgraph.connected_components(g, directed=False)
    return ncomp, lab


def densify_ll(lines, step=0.00015):
    out = []
    for pts in lines:
        a = np.asarray(pts, np.float64)
        d = np.maximum(np.abs(np.diff(a[:, 0])), np.abs(np.diff(a[:, 1])))
        for (p, q, dd) in zip(a[:-1], a[1:], d):
            k = int(dd / step) + 1
            f = np.arange(k)[:, None] / k
            out.append(p + (q - p) * f)
        out.append(a[-1:])
    return np.concatenate(out) if out else np.zeros((0, 2))


def sample_dem(E, N):
    """Lidar elevation at arbitrary UTM points, read back out of the stored tiles."""
    import process_tiles as pt
    out = np.full(len(E), np.nan, np.float32)
    ti = np.floor(E / pt.T).astype(int)
    tj = np.floor(N / pt.T).astype(int)
    for i, j in set(zip(ti.tolist(), tj.tolist())):
        if not os.path.exists(os.path.join(RAW, "dem", "%d_%d.npz" % (i, j))):
            continue
        dem = pt.load(i, j)
        m = (ti == i) & (tj == j)
        col = ((E[m] - (i * pt.T - pt.PAD)) / pt.PX).astype(int)
        row = (((j * pt.T + pt.T + pt.PAD) - N[m]) / pt.PX).astype(int)
        out[m] = dem[row, col]
    return out


def wmedian(v, w):
    o = np.argsort(v)
    cw = np.cumsum(w[o])
    return v[o][np.searchsorted(cw, cw[-1] / 2)]


def main():
    tr = pyproj.Transformer.from_crs(4326, 26917, always_xy=True)
    inv = pyproj.Transformer.from_crs(26917, 4326, always_xy=True)
    P, sea = load_pixels()
    n = len(P["gx"])
    print("skeleton pixels", n, "narrow water km", round(P["step"].sum() / 1000))
    E = (P["gx"] + 0.5) * PX
    Nn = (P["gy"] + 0.5) * PX
    xy = np.column_stack([E, Nn])

    osm = pickle.load(open(os.path.join(RAW, "osm_extract.pkl"), "rb"))
    # --- residential streets
    rp = osm["res_pts"].astype(np.float64)
    rx, ry = tr.transform(rp[:, 0], rp[:, 1])
    box = (rx > E.min() - 500) & (rx < E.max() + 500) & (ry > Nn.min() - 500) & (ry < Nn.max() + 500)
    tree = cKDTree(np.column_stack([rx[box], ry[box]]))
    dres, ires = tree.query(xy, distance_upper_bound=RES_M, workers=-1)
    res = np.isfinite(dres)
    sxy = tree.data
    del tree
    print("residential pixels", res.sum())

    # --- OSM lines: what the map calls natural, what it calls a canal
    def near(lines):
        ll = densify_ll(lines)
        x, y = tr.transform(ll[:, 0], ll[:, 1])
        d, _ = cKDTree(np.column_stack([x, y])).query(xy, distance_upper_bound=OSM_M, workers=-1)
        return np.isfinite(d)
    nat = near([r[3] for r in osm["rivers"]])
    can = near([c[4] for c in osm["canals"] if c[1] == "canal"])
    anyw = can | near([c[4] for c in osm["canals"] if c[1] != "canal"])
    # OSM coastline: mappers run natural=coastline up tidal canals. A canal pixel "touches
    # the coast" if a coastline vertex lies within half the channel width plus COAST_PAD.
    cl = densify_ll(osm["coast"])
    cxx, cyy = tr.transform(cl[:, 0], cl[:, 1])
    dco, _ = cKDTree(np.column_stack([cxx, cyy])).query(xy, distance_upper_bound=100, workers=-1)
    coast = dco <= (P["width"] / 2 + COAST_PAD)
    ruled = P["ruler"] >= RULED

    # --- components
    ncomp, lab = components(P["gx"], P["gy"])
    w = P["step"].astype(np.float64)
    L = np.bincount(lab, w, ncomp)
    wsum = np.bincount(lab, w * P["width"], ncomp)
    wmean = wsum / np.maximum(L, 1e-9)
    fb_ok = np.isfinite(P["bank"])
    bank = np.bincount(lab, w * np.where(fb_ok, P["bank"], 0), ncomp) / np.maximum(np.bincount(lab, w * fb_ok, ncomp), 1e-9)
    f_res = np.bincount(lab, w * res, ncomp) / np.maximum(L, 1e-9)
    f_nat = np.bincount(lab, w * nat, ncomp) / np.maximum(L, 1e-9)
    f_can = np.bincount(lab, w * can, ncomp) / np.maximum(L, 1e-9)
    f_any = np.bincount(lab, w * anyw, ncomp) / np.maximum(L, 1e-9)
    f_flat = np.bincount(lab, w * P["flat"], ncomp) / np.maximum(L, 1e-9)
    f_coast = np.bincount(lab, w * coast, ncomp) / np.maximum(L, 1e-9)
    f_ruled = np.bincount(lab, w * ruled, ncomp) / np.maximum(L, 1e-9)
    rul = np.bincount(lab, w * P["ruler"], ncomp) / np.maximum(L, 1e-9)
    # weighted median level per component
    o = np.lexsort((P["level"], lab))
    ls, lv, lw = lab[o], P["level"][o], w[o]
    start = np.searchsorted(ls, np.arange(ncomp))
    cw = np.cumsum(lw)
    base = np.concatenate([[0], cw])[start]
    half = base + L / 2
    level = lv[np.minimum(np.searchsorted(cw, half), n - 1)]
    # a representative pixel: the one nearest the component's centroid
    cx = np.bincount(lab, w * E, ncomp) / np.maximum(L, 1e-9)
    cy = np.bincount(lab, w * Nn, ncomp) / np.maximum(L, 1e-9)
    d2 = (E - cx[lab]) ** 2 + (Nn - cy[lab]) ** 2
    o2 = np.lexsort((d2, lab))
    rep = o2[np.searchsorted(lab[o2], np.arange(ncomp))]
    px, py = E[rep], Nn[rep]
    lon, lat = inv.transform(px, py)

    elong = L / np.maximum(wmean, 1)
    shape_ok = (L >= MIN_LEN) & (elong >= MIN_ELONG) & ((bank - level) >= MIN_FREEBOARD)
    kept = shape_ok & (f_res >= 0.5)
    print("components", ncomp, "shape ok", shape_ok.sum(), "km", round(L[shape_ok].sum() / 1000),
          "| residential", kept.sum(), "km", round(L[kept].sum() / 1000))

    # --- county, place, DEP class at the representative pixel
    pts = shapely.points(lon, lat)
    def join(path, namef, flt=None):
        fc = json.load(open(os.path.join(RAW, path), encoding="utf-8"))
        feats = [f for f in fc["features"] if f.get("geometry") and (flt is None or flt(f))]
        geoms = [shapely.make_valid(shape(f["geometry"])) for f in feats]
        names = [namef(f) for f in feats]
        st = shapely.STRtree(geoms)
        out = np.full(ncomp, -1, np.int32)
        idx = np.nonzero(shape_ok)[0]
        a, b = st.query(pts[idx], predicate="intersects")
        out[idx[a[::-1]]] = b[::-1]
        return out, names
    county, cnames = join("fl_counties.geojson", lambda f: f["properties"]["NAME"].replace(" County", ""))
    place, pnames = join("fl_places.geojson", lambda f: f["properties"]["BASENAME"])
    wb, wnames = join("wbid.geojson", lambda f: (f["properties"]["WBID"], f["properties"]["WATERBODY_NAME"],
                                                   f["properties"]["WATER_TYPE"], f["properties"]["CLASS"]))
    gulf = np.array([c >= 0 and cnames[c] in GULF for c in county])
    kept &= gulf
    shape_ok &= gulf

    # --- second freeboard measure: the crown of the nearest residential street, not the lot.
    # Different pixels, different feature: the lot measure averages yards and house pads
    # within 45 m of the water, this one reads the road the houses front on.
    sel = np.nonzero(kept[lab] & res)[0]
    sv = np.unique(ires[sel])
    selev = dict(zip(sv.tolist(), sample_dem(sxy[sv, 0], sxy[sv, 1]).tolist()))
    st_e = np.full(n, np.nan, np.float32)
    st_e[sel] = [selev[i] for i in ires[sel].tolist()]
    okst = np.isfinite(st_e) & (st_e < 90)
    street = np.bincount(lab, w * np.where(okst, st_e, 0), ncomp) / np.maximum(np.bincount(lab, w * okst, ncomp), 1e-9)
    street[np.bincount(lab, w * okst, ncomp) == 0] = np.nan
    print("in Gulf counties", kept.sum(), "km", round(L[kept].sum() / 1000))

    np.savez_compressed(
        os.path.join(RAW, "components.npz"),
        L=L, width=wmean, level=level, bank=bank, ruler=rul, f_res=f_res, f_nat=f_nat, f_can=f_can,
        f_any=f_any, f_flat=f_flat, f_coast=f_coast, f_ruled=f_ruled, x=px, y=py, lon=lon, lat=lat, kept=kept, shape_ok=shape_ok,
        county=county, place=place, wb=wb, street=street,
    )
    json.dump(dict(counties=cnames, places=pnames, wbids=wnames),
              open(os.path.join(RAW, "names.json"), "w", encoding="utf-8"))
    keep_px = kept[lab]
    np.savez_compressed(
        os.path.join(RAW, "pixels.npz"),
        gx=P["gx"][keep_px], gy=P["gy"][keep_px], comp=lab[keep_px].astype(np.int32),
        level=P["level"][keep_px], width=P["width"][keep_px], bank=P["bank"][keep_px],
        step=P["step"][keep_px], can=can[keep_px], nat=nat[keep_px], ruler=P["ruler"][keep_px],
    )
    pickle.dump(sea, open(os.path.join(RAW, "sea.pkl"), "wb"))


if __name__ == "__main__":
    main()
