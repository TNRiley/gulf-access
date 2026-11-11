"""Census place boundaries for Florida (incorporated places and CDPs), from TIGERweb.

Used only to put a town name on each canal. Writes raw/fl_places.geojson.
"""
import json, os, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
B = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/%d/query"


def main():
    feats = []
    for layer, kind in ((4, "place"), (5, "cdp")):
        off = 0
        while True:
            q = {"where": "STATE='12'", "outFields": "NAME,BASENAME,GEOID", "outSR": 4326,
                 "maxAllowableOffset": 0.0003, "geometryPrecision": 5, "orderByFields": "GEOID",
                 "resultOffset": off, "resultRecordCount": 200, "f": "geojson"}
            d = json.loads(urllib.request.urlopen(B % layer + "?" + urllib.parse.urlencode(q), timeout=180).read())
            got = d.get("features", [])
            for f in got:
                f["properties"]["kind"] = kind
            feats += got
            print(kind, off, len(got), flush=True)
            if len(got) < 200:
                break
            off += 200
    json.dump({"type": "FeatureCollection", "features": feats},
              open(os.path.join(RAW, "fl_places.geojson"), "w", encoding="utf-8", newline="\n"))
    print(len(feats), "places")


if __name__ == "__main__":
    main()
