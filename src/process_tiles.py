"""Run canalmap over every downloaded tile.

For each raw/dem/<i>_<j>.npz writes raw/skel/<i>_<j>.npz holding, for every
skeleton pixel of narrow water inside the tile's 10 km core (the 300 m collar
is context only):
  gx, gy   global 5 m pixel index in UTM 17N: easting = (gx + 0.5) * 5, northing = (gy + 0.5) * 5
  level, width, bank, ruler, step, flat      see canalmap.py
and two per-tile summaries used by the controls:
  sea      levels (m) of wide flat water (>= 300 m across), a 2 cm histogram from -2 to +6 m
  frac     share of the core that is water / that is nodata
"""
import json, os, sys
from multiprocessing import Pool
import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
T, PAD, PX = 10000, 300, 5
C = PAD // PX
N = (T + 2 * PAD) // PX


def load(i, j):
    mm = np.load(os.path.join(RAW, "dem", "%d_%d.npz" % (i, j)))["mm"]
    dem = mm.astype(np.float32) / 1000.0
    dem[mm == -32768] = 99.0
    return dem


def one(t):
    import canalmap
    i, j = t[0], t[1]
    src = os.path.join(RAW, "dem", "%d_%d.npz" % (i, j))
    dst = os.path.join(RAW, "skel", "%d_%d.npz" % (i, j))
    if not os.path.exists(src):
        return None
    if os.path.exists(dst) and os.path.getmtime(dst) > os.path.getmtime(src) and "--force" not in sys.argv:
        return "skip"
    dem = load(i, j)
    r, m = canalmap.process(dem)
    keep = (r["row"] >= C) & (r["row"] < N - C) & (r["col"] >= C) & (r["col"] < N - C)
    e0 = (i * T - PAD) // PX
    ntop = (j * T + T + PAD) // PX            # global row index just above the top edge
    gx = e0 + r["col"][keep]
    gy = ntop - 1 - r["row"][keep]
    edt = ndi.distance_transform_edt(m)
    wide = m & (edt * PX >= 150) & (dem < 12)
    core = (slice(C, N - C), slice(C, N - C))
    sea, _ = np.histogram(dem[core][wide[core]], bins=np.arange(-2, 6.0001, 0.02))
    np.savez_compressed(
        dst, gx=gx.astype(np.int32), gy=gy.astype(np.int32),
        level=r["level"][keep], width=r["width"][keep], bank=r["bank"][keep],
        ruler=r["ruler"][keep], step=r["step"][keep], flat=r["flat"][keep],
        sea=sea.astype(np.int32),
        frac=np.array([m[core].mean(), (dem[core] > 90).mean()], np.float32),
    )
    return "%d_%d %.1f km" % (i, j, r["step"][keep].sum() / 1000)


def main():
    os.makedirs(os.path.join(RAW, "skel"), exist_ok=True)
    tiles = json.load(open(os.path.join(RAW, "tiles.json")))
    with Pool(6) as p:
        out = [x for x in p.imap_unordered(one, tiles, chunksize=2)]
    print("processed", sum(1 for x in out if x and x != "skip"), "skipped", out.count("skip"),
          "missing", out.count(None))


if __name__ == "__main__":
    main()
