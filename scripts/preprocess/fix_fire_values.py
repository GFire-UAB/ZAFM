#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix invalid / negative placeholder values in an aligned FirEUrisk raster.

Some FirEUrisk rasters may contain a sentinel value such as -32768. This script
replaces that value with a proper nodata (default -9999) using windowed I/O so
it works on very large rasters.

Typical use:
  python scripts/preprocess/fix_fire_values.py --in aligned.tif --out aligned_fix.tif
"""
import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window


def iter_windows(width: int, height: int, tile: int):
    for r in range(0, height, tile):
        h = min(tile, height - r)
        for c in range(0, width, tile):
            w = min(tile, width - c)
            yield Window(c, r, w, h)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replace bad placeholder values with nodata in a (large) GeoTIFF.")
    p.add_argument("--in", dest="in_path", required=True, help="Input GeoTIFF path.")
    p.add_argument("--out", dest="out_path", required=True, help="Output GeoTIFF path.")
    p.add_argument("--bad", type=int, default=-32768, help="Bad/sentinel value to replace (default: -32768).")
    p.add_argument("--nodata", type=int, default=-9999, help="Output nodata value (default: -9999).")
    p.add_argument("--tile", type=int, default=2048, help="Tile/window size in pixels (default: 2048).")
    p.add_argument("--overwrite", action="store_true", help="Overwrite output if it already exists.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out_path)

    if not in_path.exists():
        raise FileNotFoundError(f"Input not found: {in_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not args.overwrite:
        raise FileExistsError(f"Output exists: {out_path} (use --overwrite to replace)")

    with rasterio.open(in_path) as src:
        profile = src.profile.copy()
        profile.update(
            nodata=args.nodata,
            dtype=rasterio.int16,
            compress="LZW",
            tiled=True,
            BIGTIFF="YES",
        )

        with rasterio.open(out_path, "w", **profile) as dst:
            for win in iter_windows(src.width, src.height, args.tile):
                a = src.read(1, window=win)
                a = np.asarray(a)
                a[a == args.bad] = args.nodata
                dst.write(a.astype(np.int16, copy=False), 1, window=win)

    print("OK ✅")
    print(f"IN : {in_path}")
    print(f"OUT: {out_path}")
    print(f"Replaced {args.bad} -> {args.nodata}")


if __name__ == "__main__":
    main()
