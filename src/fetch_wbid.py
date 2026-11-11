"""Download every Florida DEP Waterbody ID (WBID) polygon with its class.

The WBID layer is the state's own water-quality bookkeeping: each polygon is a
waterbody assessment unit, and WATER_TYPE says whether DEP treats it as
ESTUARY / COASTAL / BEACH (marine) or STREAM / LAKE / SPRING (fresh).
6,894 polygons, 1,000 per page. Geometry is generalised to ~11 m on the way out.
"""
import json, os, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
U = "https://ca.dep.state.fl.us/arcgis/rest/services/OpenData/WBIDS/MapServer/0/query"


def page(offset):
    q = {
        "where": "1=1",
        "outFields": "WBID,WATERBODY_NAME,WATER_TYPE,CLASS",
        "outSR": 4326,
        "orderByFields": "OBJECTID",
        "resultOffset": offset,
        "resultRecordCount": 1000,
        "maxAllowableOffset": 0.0001,
        "geometryPrecision": 5,
        "f": "geojson",
    }
    url = U + "?" + urllib.parse.urlencode(q)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa
            print("retry", offset, e)
            time.sleep(5 * (attempt + 1))
    raise SystemExit("WBID page failed at offset %d" % offset)


def main():
    feats = []
    off = 0
    while True:
        d = page(off)
        got = d.get("features", [])
        feats += got
        print(off, len(got), flush=True)
        if len(got) < 1000:
            break
        off += 1000
    out = os.path.join(RAW, "wbid.geojson")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    print("wrote", len(feats), "polygons,", os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
