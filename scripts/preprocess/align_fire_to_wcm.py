#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Align FirEUrisk (reference fuel map) to a WCM (WorldCover) template grid.

Typical use:
- You already clipped WCM to your region of interest (ROI) at 10 m.
- You have FirEUrisk (typically 1 km) covering Europe (or a larger area).
- This script resamples/reprojects FirEUrisk onto the *exact* grid of the WCM ROI
  (same CRS, transform, width/height). Nearest-neighbour is used (categorical data).

This produces an intermediate aligned GeoTIFF that can be used as input to ZAFM v2.

Notes:
- Inputs are NOT shipped with the repository (size/licensing). See README.
- The script writes directly to disk (no full destination array in RAM).
"""
import argparse
from pathlib import Path

import rasterio
from rasterio.warp import reproject, Resampling


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Align FirEUrisk to the exact grid of a WCM template GeoTIFF.")
    p.add_argument("--wcm", required=True, help="Path to the WCM ROI GeoTIFF (template grid).")
    p.add_argument("--fire", required=True, help="Path to the FirEUrisk GeoTIFF (can be large; Europe-wide).")
    p.add_argument("--out", required=True, help="Output path for the aligned FirEUrisk GeoTIFF.")
    p.add_argument("--src-nodata", type=float, default=None, help="Override FirEUrisk nodata value (optional).")
    p.add_argument("--dst-nodata", type=float, default=None, help="Set output nodata (default: FirEUrisk nodata or 0).")
    p.add_argument("--overwrite", action="store_true", help="Overwrite output if it already exists.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    wcm_path = Path(args.wcm)
    fire_path = Path(args.fire)
    out_path = Path(args.out)

    if not wcm_path.exists():
        raise FileNotFoundError(f"WCM template not found: {wcm_path}")
    if not fire_path.exists():
        raise FileNotFoundError(f"FirEUrisk not found: {fire_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not args.overwrite:
        raise FileExistsError(f"Output exists: {out_path} (use --overwrite to replace)")

    with rasterio.open(wcm_path) as wcm, rasterio.open(fire_path) as fire:
        dst_crs = wcm.crs
        dst_transform = wcm.transform
        dst_width, dst_height = wcm.width, wcm.height

        src_nodata = args.src_nodata if args.src_nodata is not None else fire.nodata
        if src_nodata is None:
            src_nodata = 0

        dst_nodata = args.dst_nodata if args.dst_nodata is not None else src_nodata

        # Use WCM as template for output metadata
        profile = wcm.profile.copy()
        profile.update(
            driver="GTiff",
            count=1,
            dtype=fire.dtypes[0],
            nodata=dst_nodata,
            compress="LZW",
            tiled=True,
            BIGTIFF="YES",
        )

        with rasterio.open(out_path, "w", **profile) as out_ds:
            reproject(
                source=rasterio.band(fire, 1),
                destination=rasterio.band(out_ds, 1),
                src_transform=fire.transform,
                src_crs=fire.crs,
                src_nodata=src_nodata,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                dst_nodata=dst_nodata,
                resampling=Resampling.nearest,
            )

    print("OK ✅")
    print(f"WCM template: {wcm_path}")
    print(f"FirEUrisk:    {fire_path}")
    print(f"Aligned out:  {out_path}")
    print("Output matches WCM grid exactly (CRS/transform/width/height).")


if __name__ == "__main__":
    main()
