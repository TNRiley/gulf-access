"""Cut the map plates the page draws.

Each plate is a rectangle of the lidar surface around one canal town, block-averaged
from 5 m to PXOUT, plus a class raster on the same grid:
  0 land   1 other water (sea, bay, lake, pond)   2 tidal canal   3 held canal
  4 residential narrow water that fails the canal rule (subdivision lakes, creeks)
  5 canal at tide height that the state classes as fresh water
Elevation is stored as uint8 in ZSTEP steps from ZMIN (255 = above range).
"""
import json, os
import numpy as np
import pyproj
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

import canalmap
import process_tiles

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
T, PX = 10000, 5
ZMIN, ZSTEP = -1.0, 0.08

# name, centre lat, centre lon, width km, height km, block factor (output pixel = 5 m x factor)
PLATES = [
    ("Cape Coral", 26.640, -81.995, 19.0, 24.0, 3),
    ("Port Charlotte and North Port", 27.020, -82.180, 24.0, 16.0, 3),
    ("Punta Gorda Isles", 26.905, -82.070, 8.0, 7.0, 2),
    ("Rotonda West", 26.888, -82.288, 8.0, 7.0, 2),
    ("Marco Island", 25.940, -81.715, 9.0, 8.0, 2),
    ("Lehigh Acres", 26.600, -81.650, 22.0, 16.0, 3),
    ("Apollo Beach", 27.770, -82.420, 8.0, 7.0, 2),
    ("Hernando Beach", 28.490, -82.655, 7.0, 8.0, 2),
]


def mosaic(e0, n0, e1, n1):
    """5 m DEM for the UTM box, north up. Missing tiles read as nodata (99)."""
    W, H = int((e1 - e0) / PX), int((n1 - n0) / PX)
    out = np.full((H, W), 99.0, np.float32)
    C = process_tiles.C
    for i in range(int(e0 // T), int((e1 - 1) // T) + 1):
        for j in range(int(n0 // T), int((n1 - 1) // T) + 1):
            if not os.path.exists(os.path.join(RAW, "dem", "%d_%d.npz" % (i, j))):
                continue
            d = process_tiles.load(i, j)[C:-C, C:-C]          # 2000 x 2000 core
            # tile core covers E [i*T, (i+1)*T), N [(j+1)*T down to j*T]
            c0 = int((i * T - e0) / PX)
            r0 = int((n1 - (j + 1) * T) / PX)
            rs, cs = max(r0, 0), max(c0, 0)
            re, ce = min(r0 + 2000, H), min(c0 + 2000, W)
            out[rs:re, cs:ce] = d[rs - r0:re - r0, cs - c0:ce - c0]
    return out


def build(pix, comp_class):
    """pix: dict of kept pixel arrays (gx, gy, comp, width). comp_class: class code per component id."""
    tr = pyproj.Transformer.from_crs(4326, 26917, always_xy=True)
    tree = cKDTree(np.column_stack([pix["gx"], pix["gy"]]).astype(np.float64))
    out = []
    for name, lat, lon, wkm, hkm, f in PLATES:
        cx, cy = tr.transform(lon, lat)
        step = PX * f
        e0 = np.floor((cx - wkm * 500) / step) * step
        n0 = np.floor((cy - hkm * 500) / step) * step
        W = int(wkm * 1000 / step)
        H = int(hkm * 1000 / step)
        e1, n1 = e0 + W * step, n0 + H * step
        dem = mosaic(e0, n0, e1, n1)
        m, _ = canalmap.water_mask(dem)
        cls = np.zeros(dem.shape, np.uint8)
        cls[m] = 1
        rr, cc = np.nonzero(m)
        gx = (e0 / PX + cc).astype(np.float64)
        gy = (n1 / PX - 1 - rr).astype(np.float64)
        d, idx = tree.query(np.column_stack([gx, gy]), distance_upper_bound=14, workers=-1)
        ok = np.isfinite(d)
        near = idx[ok]
        ok2 = d[ok] * PX <= pix["width"][near] / 2 + 8
        sel = np.nonzero(ok)[0][ok2]
        cls[rr[sel], cc[sel]] = comp_class[pix["comp"][near[ok2]]]
        # block-reduce: mean elevation of land, majority-ish class (max priority canal > water > land)
        demb = dem.reshape(H, f, W, f)
        land = (cls == 0).reshape(H, f, W, f)
        nland = land.sum(axis=(1, 3))
        zl = np.where(land, demb, 0).sum(axis=(1, 3)) / np.maximum(nland, 1)
        zw = demb.min(axis=(1, 3))
        z = np.where(nland * 2 >= f * f, zl, zw)
        cb = cls.reshape(H, f, W, f).transpose(0, 2, 1, 3).reshape(H, W, f * f)
        cnt = np.stack([(cb == k).sum(axis=2) for k in range(6)], axis=2)
        cnt[:, :, 0] = np.where(cnt[:, :, 0] * 2 >= f * f, 99, 0)       # land wins only with a majority
        cnt[:, :, 2:6] *= 3                                             # a canal is thin: let it show
        cout = cnt.argmax(axis=2).astype(np.uint8)
        q = np.clip(np.round((z - ZMIN) / ZSTEP), 0, 254).astype(np.uint8)
        q[z > 90] = 255
        lon0, lat0 = pyproj.Transformer.from_crs(26917, 4326, always_xy=True).transform(e0, n1)
        out.append(dict(name=name, w=W, h=H, px=step, e0=float(e0), n1=float(n1), z=q, c=cout))
        print("%-32s %4d x %4d  water %.1f%%  tidal px %d  held px %d  low-fresh px %d  other-narrow px %d"
              % (name, W, H, 100 * (cout > 0).mean(), (cout == 2).sum(), (cout == 3).sum(), (cout == 5).sum(), (cout == 4).sum()))
    return out
