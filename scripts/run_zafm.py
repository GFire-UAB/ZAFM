#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Command-line interface for ZAFM v2.

Examples
--------
Single region (explicit paths):

  python scripts/run_zafm.py \
    --wcm data/input/ESP__WCM_4326_clip.tif \
    --fire data/input/ESP__FIREURISK_4326_clip_aligned_to_WCM_MASKED.tif \
    --humid-shp data/bioclim/humid.shp \
    --out output/ESP_4326_ZAFM.tif

Batch mode (input directory + region codes):

  python scripts/run_zafm.py \
    --input-dir data/input \
    --regions ESP,FRA,GRC,ITA,PRT \
    --humid-shp data/bioclim/humid.shp \
    --out-dir output

In batch mode, the script expects these filenames per region prefix:
  <REG>__WCM_4326_clip.tif
  <REG>__FIREURISK_4326_clip_aligned_to_WCM_MASKED.tif

"""

from __future__ import annotations

import argparse
import os
from typing import List

from zafm import ZAFMConfig, run_zafm


def _parse_regions(s: str) -> List[str]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    # normalize common variants
    norm = []
    for p in parts:
        p = p.upper()
        if p in {"SPN", "ESP"}:
            norm.append("ESP")
        elif p in {"GRE", "GRC"}:
            norm.append("GRC")
        else:
            norm.append(p)
    # unique, keep order
    seen = set()
    out = []
    for p in norm:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description="Run ZAFM v2 (windowed, bioclim-aware).")

    # Single-run inputs
    ap.add_argument("--wcm", help="Path to WCM raster (GeoTIFF).")
    ap.add_argument("--fire", help="Path to FirEUrisk raster aligned to WCM (GeoTIFF).")
    ap.add_argument("--out", help="Output ZAFM raster path (GeoTIFF).")

    # Batch inputs
    ap.add_argument("--input-dir", help="Directory containing region input rasters.")
    ap.add_argument("--regions", help="Comma-separated region codes: ESP,FRA,GRC,ITA,PRT")
    ap.add_argument("--out-dir", default="output", help="Output directory for batch mode.")

    # Shared
    ap.add_argument("--humid-shp", required=True, help="Humid regime shapefile (.shp).")
    ap.add_argument("--tile", default="2048,2048", help="Tile size 'W,H' (default 2048,2048).")
    ap.add_argument("--halo", type=int, default=256, help="Halo padding (pixels) around each tile.")
    ap.add_argument("--out-nodata", type=int, default=0, help="Output nodata value (default 0).")
    ap.add_argument("--outside-mask", type=int, default=0, help="WCM value meaning 'outside' (default 0).")

    args = ap.parse_args()

    tile_w, tile_h = [int(x) for x in args.tile.split(",")]

    # Decide mode
    if args.wcm and args.fire and args.out:
        cfg = ZAFMConfig(
            wcm_path=args.wcm,
            fire_path=args.fire,
            humid_shp=args.humid_shp,
            out_path=args.out,
            tile_w=tile_w,
            tile_h=tile_h,
            halo=args.halo,
            out_nodata=args.out_nodata,
            outside_mask_value=args.outside_mask,
        )
        out = run_zafm(cfg)
        print(f"\nOK -> {out}")
        return

    if args.input_dir and args.regions:
        regions = _parse_regions(args.regions)
        os.makedirs(args.out_dir, exist_ok=True)

        for reg in regions:
            wcm = os.path.join(args.input_dir, f"{reg}__WCM_4326_clip.tif")
            fire = os.path.join(args.input_dir, f"{reg}__FIREURISK_4326_clip_aligned_to_WCM_MASKED.tif")
            out = os.path.join(args.out_dir, f"{reg}_4326_ZAFM.tif")

            cfg = ZAFMConfig(
                wcm_path=wcm,
                fire_path=fire,
                humid_shp=args.humid_shp,
                out_path=out,
                tile_w=tile_w,
                tile_h=tile_h,
                halo=args.halo,
                out_nodata=args.out_nodata,
                outside_mask_value=args.outside_mask,
            )

            print(f"\n=== Running {reg} ===")
            outp = run_zafm(cfg)
            print(f"OK -> {outp}")
        return

    ap.error("Provide either (--wcm --fire --out) for single mode, or (--input-dir --regions) for batch mode.")


if __name__ == "__main__":
    main()
