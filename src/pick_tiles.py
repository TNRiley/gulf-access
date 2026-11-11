"""Choose which 10 km UTM-17N tiles to download.

A tile is kept if it touches one of the 22 Gulf-coast counties and holds at
least 300 vertices of highway=residential (streets densified to ~30 m, so 300
vertices is roughly 9 km of residential street). Writes raw/tiles.json as
[i, j, n_vertices, [county, ...]] where the tile spans easting i*10 km .. (i+1)*10 km.
"""
import collections, json, os, pickle
import numpy as np, pyproj, shapely
from shapely.geometry import shape

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
GULF = ["Escambia", "Santa Rosa", "Okaloosa", "Walton", "Bay", "Gulf", "Franklin", "Wakulla",
        "Jefferson", "Taylor", "Dixie", "Levy", "Citrus", "Hernando", "Pasco", "Pinellas",
        "Hillsborough", "Manatee", "Sarasota", "Charlotte", "Lee", "Collier"]
T = 10000


def main():
    tr = pyproj.Transformer.from_crs(4326, 26917, always_xy=True)
    inv = pyproj.Transformer.from_crs(26917, 4326, always_xy=True)
    d = pickle.load(open(os.path.join(RAW, "osm_extract.pkl"), "rb"))
    P = d["res_pts"].astype(np.float64)
    x, y = tr.transform(P[:, 0], P[:, 1])
    cs = json.load(open(os.path.join(RAW, "fl_counties.geojson"), encoding="utf-8"))
    polys = [(f["properties"]["NAME"].replace(" County", ""), shape(f["geometry"])) for f in cs["features"]]
    polys = [(n, p) for n, p in polys if n in GULF]
    cnt = collections.Counter(zip(np.floor(x / T).astype(int), np.floor(y / T).astype(int)))
    tiles = []
    for (i, j), n in sorted(cnt.items()):
        if n < 300:
            continue
        box = shapely.box(*inv.transform(i * T, j * T), *inv.transform((i + 1) * T, (j + 1) * T))
        hit = [nm for nm, p in polys if p.intersects(box)]
        if hit:
            tiles.append((int(i), int(j), int(n), hit))
    json.dump(tiles, open(os.path.join(RAW, "tiles.json"), "w"))
    print(len(tiles), "tiles")


if __name__ == "__main__":
    main()
