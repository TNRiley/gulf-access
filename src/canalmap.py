"""Find narrow water in a 5 m bare-earth lidar DEM and measure it.

The DEM is the only input. Nothing here knows where any map says a canal is.

Water is whatever is FLAT: a 3x3 window whose range is <= 5 mm, grown out over
neighbours at the same elevation. A USGS lidar DEM is hydro-flattened: the
contractor draws a breakline round each water body and sets every cell inside
it to one elevation. Bare ground, even a Florida car park, is never flat to
5 mm over 15 m, so flatness alone picks out the water.

(A first attempt also looked for trenches cut below the house lots. It found
every street in Cape Coral, because the lots are filled above the roads too.
953 km of "canal" in one 10 km tile. It is not in this file any more.)

Each skeleton pixel of narrow water then gets:
  level   water surface elevation, m NAVD88 (low median of the DEM in the channel)
  width   channel width in m, twice the distance transform at the skeleton
  bank    median land elevation within BANK_M of the channel, m NAVD88
  ruler   0..1 straightness: coherence of the structure tensor of the water mask
          in a 30 m Gaussian window. Two parallel straight banks give ~1, a pond ~0.
"""
import numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

PX = 5.0
FLAT_M = 0.03      # hydro-flattened water is flat to a few cm over 15 m; land is not
TRENCH_M = 1.2     # streets sit 0.3-0.8 m below the house pads; canals sit deeper
CLOSE_M = 95.0
USE_TRENCH = True
RULER_SIGMA_M = 30.0
NEAR_M = 800.0     # a trench must be this close to flattened water...
NEAR_DZ = 0.3      # ...and within this of its level
MAXW_M = 110.0     # wider than this is a lake, a bay or a river, not a canal
BANK_M = 45.0
SEA_MAX = 12.0     # ignore "water" above this; nothing coastal sits that high


def _despeck(m, minpx):
    lab, n = ndi.label(m, np.ones((3, 3), bool))
    if not n:
        return m
    sizes = ndi.sum_labels(m, lab, np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes >= minpx
    return keep[lab]


def water_mask(dem):
    mx = ndi.maximum_filter(dem, 3)
    mn = ndi.minimum_filter(dem, 3)
    core = (mx - mn) <= FLAT_M            # centre of a 3x3 block at one elevation
    # grow each core back out over neighbours at the same elevation
    lvl = ndi.maximum_filter(np.where(core, dem, np.float32(-99)), 3)
    flat = (np.abs(dem - lvl) <= FLAT_M) & (dem < SEA_MAX) & (dem > -5)
    k = int(round(CLOSE_M / PX)) | 1
    trench = (ndi.grey_closing(dem, size=(k, k)) - dem) >= TRENCH_M
    trench &= ~flat
    # a trench only counts if it sits at the level of flattened water nearby:
    # every canal in a system shares one stage, and no street is down there with it
    fl = _despeck(flat, 60)
    if fl.any():
        dist, (ir, ic) = ndi.distance_transform_edt(~fl, return_indices=True)
        near = dem[ir, ic]
        trench &= (dist * PX <= NEAR_M) & (np.abs(dem - near) <= NEAR_DZ)
    else:
        trench[:] = False
    if not USE_TRENCH:
        trench[:] = False
    m = flat | trench
    m = ndi.binary_closing(m, np.ones((3, 3), bool)) | m
    m = _despeck(m, 60)                   # under 60 px is 1,500 m2
    return m, flat & m


def ruler(mask):
    """Orientation coherence of the mask boundary, Gaussian window RULER_SIGMA_M."""
    s = ndi.gaussian_filter(mask.astype(np.float32), 1.2)
    gy, gx = np.gradient(s)
    sig = RULER_SIGMA_M / PX
    jxx = ndi.gaussian_filter(gx * gx, sig)
    jyy = ndi.gaussian_filter(gy * gy, sig)
    jxy = ndi.gaussian_filter(gx * gy, sig)
    tr = jxx + jyy
    disc = np.sqrt((jxx - jyy) ** 2 + 4 * jxy * jxy)
    return np.where(tr > 1e-9, disc / np.maximum(tr, 1e-9), 0).astype(np.float32)


def process(dem):
    """Return a dict of per-skeleton-pixel arrays (row, col, level, width, bank, ruler, step)."""
    dem = np.where(np.isfinite(dem), dem, 0).astype(np.float32)
    m, flat = water_mask(dem)
    edt = ndi.distance_transform_edt(m) * PX
    sk = skeletonize(m)
    width = 2 * edt
    narrow = sk & (width <= MAXW_M) & (width >= 7.5)
    # level: the low side of the DEM inside the channel, robust to bank bleed
    big = np.where(m, dem, np.float32(99))
    low = ndi.minimum_filter(ndi.median_filter(big, 3), 7)
    # bank: mean land elevation near the water, by normalised convolution
    land = ~ndi.binary_dilation(m, np.ones((3, 3), bool))
    r = int(round(BANK_M / PX))
    ker = np.ones((2 * r + 1, 2 * r + 1), np.float32)
    num = ndi.uniform_filter(np.where(land, dem, 0).astype(np.float32), 2 * r + 1)
    den = ndi.uniform_filter(land.astype(np.float32), 2 * r + 1)
    bank = np.where(den > 0.05, num / np.maximum(den, 1e-6), np.nan)
    coh = ruler(m)
    # length carried by each skeleton pixel: half the distance to each skeleton neighbour
    skf = narrow.astype(np.float32)
    orth = ndi.convolve(skf, np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], np.float32), mode="constant")
    diag = ndi.convolve(skf, np.array([[1, 0, 1], [0, 0, 0], [1, 0, 1]], np.float32), mode="constant")
    step = 0.5 * PX * (orth + 1.41421356 * diag)
    step = np.minimum(step, 1.5 * PX)        # a junction pixel is still one pixel of canal
    step = np.where(narrow & (step == 0), PX, step)
    rr, cc = np.nonzero(narrow)
    return dict(
        row=rr.astype(np.int32), col=cc.astype(np.int32),
        level=low[rr, cc], width=width[rr, cc].astype(np.float32),
        bank=bank[rr, cc].astype(np.float32), ruler=coh[rr, cc],
        step=step[rr, cc].astype(np.float32),
        flat=flat[rr, cc],
    ), m
