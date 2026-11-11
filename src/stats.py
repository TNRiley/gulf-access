"""Recompute the page's headline numbers from payload.json, the same way the page does.

The page computes everything in the browser from the shipped arrays; this script is the
check that the two agree, and the source of the expected-values table in REBUILD.md.
"""
import base64, json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MI = 1.609344


def arr(s, dt):
    return np.frombuffer(base64.b64decode(s), dt)


def wq(v, w, q):
    o = np.argsort(v)
    cw = np.cumsum(w[o])
    return float(v[o][min(np.searchsorted(cw, q * cw[-1]), len(v) - 1)])


def main():
    p = json.load(open(os.path.join(HERE, "payload.json"), encoding="utf-8"))
    c = p["comps"]
    L = arr(c["L"], "<f4").astype(float) / 1000
    lv = arr(c["lv"], "<i2") / 100
    bk = arr(c["bk"], "<i2") / 100
    st = arr(c["st"], "<i2").astype(float)
    st[st == -32768] = np.nan
    st /= 100
    ru, res, nat, can = (arr(c[k], "u1") for k in ("ru", "res", "nat", "can"))
    co, dep = arr(c["co"], "u1"), arr(c["dep"], "u1")
    pl = arr(c["pl"], "<u2")
    names = p["names"]
    resid = (res >= 50)
    base = resid & (nat < 50)
    rules = {
        "network or ruled (default)": base & ((L >= 2) | (ru >= 50)),
        "any residential narrow water": base,
        "networks of 2 km or more": base & (L >= 2),
        "ruled-straight only": base & (ru >= 50),
        "OSM calls it a canal": base & (can >= 50),
    }
    low = lv <= 0.6
    out = {}
    for name, r in rules.items():
        T = L[r].sum()
        out[name] = dict(km=round(T), low_share=round(100 * L[r & low].sum() / T, 1),
                         tidal=round(L[r & low & (dep != 2)].sum()), disputed=round(L[r & low & (dep == 2)].sum()),
                         held=round(L[r & ~low].sum()), osm_cover=round(100 * (L[r] * can[r] / 100).sum() / T, 1))
    r = rules["network or ruled (default)"]
    cc = r & (pl == names["places"].index("Cape Coral"))
    ccall = base & (pl == names["places"].index("Cape Coral"))
    out["cape_coral"] = dict(
        km=round(L[cc].sum(), 1), mi=round(L[cc].sum() / MI, 1), all_res_km=round(L[ccall].sum(), 1),
        held_km=round(L[cc & ~low].sum(), 1), held_mi=round(L[cc & ~low].sum() / MI, 1),
        low_km=round(L[cc & low].sum(), 1), dep_fresh_km=round(L[cc & (dep == 2)].sum(), 1),
        dep_fresh_mi=round(L[cc & (dep == 2)].sum() / MI, 1), dep_marine_km=round(L[cc & (dep == 1)].sum(), 1),
        both_tidal=round(L[cc & low & (dep == 1)].sum(), 1), both_fresh=round(L[cc & ~low & (dep == 2)].sum(), 1),
        low_but_fresh=round(L[cc & low & (dep == 2)].sum(), 1), held_but_marine=round(L[cc & ~low & (dep == 1)].sum(), 1),
        osm_cover=round(100 * (L[cc] * can[cc] / 100).sum() / L[cc].sum(), 1),
    )
    agree = r & (dep > 0)
    out["agreement_pct"] = round(100 * L[agree & (low == (dep == 1))].sum() / L[agree].sum(), 1)
    fb, fs = bk - lv, st - lv
    wild = (res < 10)
    def q(m, v):
        m = m & np.isfinite(v)
        return [round(wq(v[m], L[m], x), 2) for x in (0.1, 0.25, 0.5, 0.75, 0.9)] + [round(L[m].sum())]
    out["freeboard"] = dict(
        tidal_lot=q(r & low, fb), tidal_street=q(r & low, fs), held_lot=q(r & ~low, fb), held_street=q(r & ~low, fs),
        wild_low=q(wild & low, fb), wild_held=q(wild & ~low, fb),
    )
    towns = {}
    for i, nm in enumerate(names["places"]):
        m = r & (pl == i)
        if L[m].sum() >= 30:
            towns[nm] = dict(km=round(L[m].sum()), low=round(L[m & low].sum()), held=round(L[m & ~low].sum()),
                             osm=round(100 * (L[m] * can[m] / 100).sum() / L[m].sum()))
    out["towns"] = dict(sorted(towns.items(), key=lambda kv: -kv[1]["km"]))
    cnt = {}
    for nm_i in range(len(names["counties"])):
        m = r & (co == nm_i)
        if m.any():
            cnt[names["counties"][nm_i]] = dict(km=round(L[m].sum()), low=round(L[m & low].sum()), held=round(L[m & ~low].sum()))
    out["counties"] = cnt
    s = p["sea"]
    cm = np.array(s["cm"])
    out["sea"] = dict(tiles=int(s["n"]), at_zero=int((np.abs(cm) <= 2).sum()),
                      values=sorted({int(x): int((cm == x).sum()) for x in set(cm.tolist())}.items(), key=lambda kv: -kv[1])[:6])
    out["max_held_level"] = float(lv[r].max())
    json.dump(out, open(os.path.join(HERE, "stats.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
