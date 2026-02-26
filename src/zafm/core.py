"""ZAFM v2 (windowed / multi-region) implementation.

Key ideas:
- Convert FirEUrisk classes -> Burgan classes using bioclimatic regime (humid vs arid).
- For WCM classes that map to multiple candidate fuel models, pick the candidate that
  is spatially closest in the reference fuel map.

Optimization:
- Process the raster in tiles (windows) + halo.
- Use scipy.ndimage.distance_transform_edt to compute distance maps efficiently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import os
import numpy as np
import rasterio
from rasterio.windows import Window

from .tiling import iter_windows, clamp_window, expand_window, window_slices
from .bioclim import HumidMaskRasterizer
from .mappings import (
    WCM_TO_FIRE_CANDIDATES,
    WCM_FIXED_BURGAN,
    REMAP_FIRE_TO_BURGAN_ARID,
    REMAP_FIRE_TO_BURGAN_HUMID,
)

try:
    from scipy.ndimage import distance_transform_edt
except Exception as e:  # pragma: no cover
    raise ImportError(
        "SciPy is required (scipy.ndimage.distance_transform_edt). Install with: pip install scipy"
    ) from e


def _build_lut_from_dict(mapping: Dict[int, int], max_code: int, default: int = 0) -> np.ndarray:
    lut = np.full(max_code + 1, default, dtype=np.uint16)
    for k, v in mapping.items():
        kk = int(k)
        if 0 <= kk <= max_code:
            lut[kk] = np.uint16(v)
    return lut


def fire_to_burgan_tile(fire_tile: np.ndarray, humid_tile: np.ndarray, nodata_fire: Optional[float]) -> np.ndarray:
    """Convert FirEUrisk -> Burgan for a tile, using humid_tile (1 humid / 0 arid)."""
    out = np.zeros_like(fire_tile, dtype=np.uint16)

    if nodata_fire is not None:
        valid = (fire_tile != nodata_fire)
    else:
        valid = np.ones(fire_tile.shape, dtype=bool)

    if not np.any(valid):
        return out

    max_code = int(fire_tile[valid].max())
    lut_h = _build_lut_from_dict(REMAP_FIRE_TO_BURGAN_HUMID, max_code=max_code, default=0)
    lut_a = _build_lut_from_dict(REMAP_FIRE_TO_BURGAN_ARID,  max_code=max_code, default=0)

    m_h = valid & (humid_tile == 1)
    m_a = valid & (humid_tile == 0)

    if np.any(m_h):
        out[m_h] = lut_h[fire_tile[m_h]]
    if np.any(m_a):
        out[m_a] = lut_a[fire_tile[m_a]]

    return out


def wcm_to_burgan_candidates(wcm_val: int, regime: str) -> List[int]:
    """Return candidate Burgan codes for a WCM class under a regime (humid|arid)."""
    if wcm_val in WCM_FIXED_BURGAN:
        return [WCM_FIXED_BURGAN[wcm_val]]

    fire_cand = WCM_TO_FIRE_CANDIDATES.get(wcm_val)
    if not fire_cand:
        return []

    mapping = REMAP_FIRE_TO_BURGAN_HUMID if regime == "humid" else REMAP_FIRE_TO_BURGAN_ARID
    burg = [mapping.get(fc, 0) for fc in fire_cand]
    burg = [int(b) for b in burg if int(b) != 0]

    # unique preserving order
    seen = set()
    uniq: List[int] = []
    for b in burg:
        if b not in seen:
            seen.add(b)
            uniq.append(b)
    return uniq


def compute_nearest_distance_maps(burgan_halo: np.ndarray, needed_burgans: Iterable[int]) -> Dict[int, Optional[np.ndarray]]:
    """Compute EDT distance map for each needed burgan code, within a halo tile."""
    dist_maps: Dict[int, Optional[np.ndarray]] = {}
    for b in needed_burgans:
        feature = (burgan_halo != b).astype(np.uint8)  # 0 where b occurs
        if np.all(feature == 1):
            dist_maps[b] = None
            continue
        dist_maps[b] = distance_transform_edt(feature).astype(np.float32)
    return dist_maps


def apply_zafm_burgan_tile(
    wcm_core: np.ndarray,
    burgan_core: np.ndarray,
    burgan_halo: np.ndarray,
    humid_core: np.ndarray,
    core_sl_r: slice,
    core_sl_c: slice,
    out_nodata: int = 0,
    outside_mask_value: int = 0,
) -> np.ndarray:
    """Apply ZAFM in Burgan space for a tile.

    Parameters
    ----------
    outside_mask_value:
        If WCM equals this value, output is set to out_nodata (i.e., outside study area).
    """
    out = np.full_like(wcm_core, out_nodata, dtype=np.uint16)

    # valid study area pixels
    m_valid = (wcm_core != outside_mask_value)
    if not np.any(m_valid):
        return out

    # fixed classes
    for wcm_val, burg in WCM_FIXED_BURGAN.items():
        m = m_valid & (wcm_core == wcm_val)
        out[m] = np.uint16(burg)

    unresolved = m_valid & ~np.isin(wcm_core, list(WCM_FIXED_BURGAN.keys()))
    if not np.any(unresolved):
        return out

    present_wcm = np.unique(wcm_core[unresolved])
    present_wcm = [int(v) for v in present_wcm.tolist() if int(v) in WCM_TO_FIRE_CANDIDATES or int(v) in WCM_FIXED_BURGAN]

    # If nothing matches, fallback to reference
    if not present_wcm:
        out[unresolved] = burgan_core[unresolved].astype(np.uint16)
        return out

    cand_by_wcm_h: Dict[int, List[int]] = {}
    cand_by_wcm_a: Dict[int, List[int]] = {}
    needed_burgans = set()

    for w in present_wcm:
        ch = wcm_to_burgan_candidates(w, "humid")
        ca = wcm_to_burgan_candidates(w, "arid")
        cand_by_wcm_h[w] = ch
        cand_by_wcm_a[w] = ca
        needed_burgans.update(ch)
        needed_burgans.update(ca)

    needed = sorted([int(b) for b in needed_burgans if int(b) != 0])
    dist_maps_halo = compute_nearest_distance_maps(burgan_halo, needed)

    # Crop distance maps to core
    dist_maps_core: Dict[int, Optional[np.ndarray]] = {}
    for b, dist_h in dist_maps_halo.items():
        dist_maps_core[b] = None if dist_h is None else dist_h[core_sl_r, core_sl_c]

    chosen_b = np.full(wcm_core.shape, -1, dtype=np.int32)

    for w in present_wcm:
        m_w = unresolved & (wcm_core == w)
        if not np.any(m_w):
            continue

        # Humid
        m_wh = m_w & (humid_core == 1)
        cand_h = cand_by_wcm_h.get(w, [])
        if np.any(m_wh):
            if len(cand_h) == 1:
                chosen_b[m_wh] = cand_h[0]
            elif len(cand_h) > 1:
                best_dist = np.full(wcm_core.shape, np.inf, dtype=np.float32)
                best_code = np.full(wcm_core.shape, -1, dtype=np.int32)
                for b in cand_h:
                    d = dist_maps_core.get(b)
                    if d is None:
                        continue
                    improve = m_wh & (d < best_dist)
                    best_dist[improve] = d[improve]
                    best_code[improve] = b
                chosen_b[m_wh] = best_code[m_wh]

        # Arid
        m_wa = m_w & (humid_core == 0)
        cand_a = cand_by_wcm_a.get(w, [])
        if np.any(m_wa):
            if len(cand_a) == 1:
                chosen_b[m_wa] = cand_a[0]
            elif len(cand_a) > 1:
                best_dist = np.full(wcm_core.shape, np.inf, dtype=np.float32)
                best_code = np.full(wcm_core.shape, -1, dtype=np.int32)
                for b in cand_a:
                    d = dist_maps_core.get(b)
                    if d is None:
                        continue
                    improve = m_wa & (d < best_dist)
                    best_dist[improve] = d[improve]
                    best_code[improve] = b
                chosen_b[m_wa] = best_code[m_wa]

    m_chosen = (chosen_b >= 0) & unresolved
    out[m_chosen] = chosen_b[m_chosen].astype(np.uint16)

    # fallback
    m_unresolved = unresolved & (chosen_b < 0)
    if np.any(m_unresolved):
        out[m_unresolved] = burgan_core[m_unresolved].astype(np.uint16)

    return out


@dataclass
class ZAFMConfig:
    wcm_path: str
    fire_path: str
    humid_shp: str
    out_path: str
    tile_w: int = 2048
    tile_h: int = 2048
    halo: int = 256
    out_nodata: int = 0
    outside_mask_value: int = 0  # if WCM==0 => outside


def run_zafm(cfg: ZAFMConfig) -> str:
    """Run ZAFM v2 for one region. Returns output path."""
    for p in [cfg.wcm_path, cfg.fire_path, cfg.humid_shp]:
        if not os.path.exists(p):
            raise FileNotFoundError(p)

    humid_rast = HumidMaskRasterizer(cfg.humid_shp)

    with rasterio.open(cfg.wcm_path) as wcm_src, rasterio.open(cfg.fire_path) as fire_src:
        if (wcm_src.width != fire_src.width) or (wcm_src.height != fire_src.height):
            raise ValueError("WCM and FIRE rasters have different dimensions.")
        if wcm_src.transform != fire_src.transform:
            raise ValueError("WCM and FIRE rasters are not perfectly aligned (different transform).")
        if str(wcm_src.crs) != str(fire_src.crs):
            raise ValueError("WCM and FIRE rasters have different CRS.")

        width, height = wcm_src.width, wcm_src.height
        crs = wcm_src.crs
        nodata_fire = fire_src.nodata

        profile = wcm_src.profile.copy()
        profile.update(
            driver="GTiff",
            dtype=rasterio.uint16,
            count=1,
            nodata=cfg.out_nodata,
            compress="LZW",
            tiled=True,
            BIGTIFF="YES",
        )
        profile.pop("photometric", None)

        os.makedirs(os.path.dirname(cfg.out_path) or ".", exist_ok=True)

        n_tiles_x = (width + cfg.tile_w - 1) // cfg.tile_w
        n_tiles_y = (height + cfg.tile_h - 1) // cfg.tile_h
        total_tiles = int(n_tiles_x * n_tiles_y)
        processed = 0
        next_pct = 10

        with rasterio.open(cfg.out_path, "w", **profile) as dst:
            for win_core in iter_windows(width, height, tile_w=cfg.tile_w, tile_h=cfg.tile_h):
                win_halo = clamp_window(expand_window(win_core, cfg.halo), width, height)

                # Read WCM band 1 (WCM might have more than 1 band)
                wcm_core = wcm_src.read(1, window=win_core)

                fire_core = fire_src.read(1, window=win_core)
                fire_halo = fire_src.read(1, window=win_halo)

                win_halo_transform = rasterio.windows.transform(win_halo, wcm_src.transform)
                humid_halo = humid_rast.rasterize_window(
                    out_shape=(int(win_halo.height), int(win_halo.width)),
                    transform=win_halo_transform,
                    crs=crs,
                )
                core_sl_r, core_sl_c = window_slices(win_core, win_halo)
                humid_core = humid_halo[core_sl_r, core_sl_c]

                burgan_core = fire_to_burgan_tile(fire_core, humid_core, nodata_fire=nodata_fire)
                burgan_halo = fire_to_burgan_tile(fire_halo, humid_halo, nodata_fire=nodata_fire)

                out_core = apply_zafm_burgan_tile(
                    wcm_core=wcm_core,
                    burgan_core=burgan_core,
                    burgan_halo=burgan_halo,
                    humid_core=humid_core,
                    core_sl_r=core_sl_r,
                    core_sl_c=core_sl_c,
                    out_nodata=cfg.out_nodata,
                    outside_mask_value=cfg.outside_mask_value,
                )

                dst.write(out_core.astype(np.uint16), 1, window=win_core)

                processed += 1
                pct = int((processed * 100) // total_tiles)
                if pct >= next_pct:
                    print(f"Progress: {pct}% ({processed}/{total_tiles} tiles)", flush=True)
                    next_pct = ((pct // 10) + 1) * 10

    return cfg.out_path
