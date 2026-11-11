"""Download the lidar surface, one 10 km tile at a time, from USGS 3DEP.

  service   https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer
  call      exportImage, format=tiff, pixelType=F32, nearest-neighbour, EPSG:26917 (UTM 17N)
  pixel     5 m, sampled from the 1 m lidar DEM (nearest neighbour, so a pixel is one
            real 1 m cell and flattened water stays exactly as flat as the contractor left it)
  tile      10 km x 10 km plus a 300 m collar = 2120 x 2120 px, ~17 MB each as float tiff

raw/tiles.json (written by pick_tiles.py) lists the tiles. Each is stored as
raw/dem/<i>_<j>.npz, int16 millimetres clipped to +-32 m, about 3 MB.
Safe to re-run: finished tiles are skipped.
"""
import io, json, os, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import tifffile

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(RAW, "dem")
B = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
T = 10000
PAD = 300
PX = 5
N = (T + 2 * PAD) // PX
WORKERS = 8


def fetch(t):
    i, j = t[0], t[1]
    path = os.path.join(OUT, "%d_%d.npz" % (i, j))
    if os.path.exists(path):
        return "skip"
    e0, n0 = i * T - PAD, j * T - PAD
    p = {
        "bbox": "%d,%d,%d,%d" % (e0, n0, e0 + T + 2 * PAD, n0 + T + 2 * PAD),
        "bboxSR": 26917, "imageSR": 26917, "size": "%d,%d" % (N, N),
        "format": "tiff", "pixelType": "F32", "interpolation": "RSP_NearestNeighbor",
        "noData": -9999, "f": "image",
    }
    url = B + "?" + urllib.parse.urlencode(p)
    for attempt in range(6):
        try:
            raw = urllib.request.urlopen(url, timeout=300).read()
            a = tifffile.imread(io.BytesIO(raw)).astype(np.float32)
            if a.shape != (N, N):
                raise ValueError("shape %s" % (a.shape,))
            bad = ~np.isfinite(a) | (a < -500)
            mm = np.clip(np.round(a * 1000), -32000, 32000).astype(np.int16)
            mm[bad] = -32768
            np.savez_compressed(path, mm=mm)
            return "ok"
        except Exception as e:  # noqa
            err = e
            time.sleep(4 * (attempt + 1))
    return "FAIL %s" % err


def main():
    os.makedirs(OUT, exist_ok=True)
    tiles = json.load(open(os.path.join(RAW, "tiles.json")))
    tiles.sort(key=lambda t: -t[2])           # densest streets first
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for t, r in zip(tiles, ex.map(fetch, tiles)):
            done += 1
            if r != "skip" and (done % 10 == 0 or r != "ok"):
                print(done, len(tiles), t[:2], r, round(time.time() - t0), "s", flush=True)
    print("done", len(tiles), "tiles in", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
