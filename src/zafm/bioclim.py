"""Bioclimatic regime utilities.

Current implementation uses a shapefile polygon layer where:
- inside polygon => humid (1)
- outside => arid (0)

The mask is rasterized per tile (window) to keep memory usage low.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import rasterio
from rasterio.features import rasterize


@dataclass
class HumidMaskRasterizer:
    shp_path: str
    _gdf: Optional[object] = None

    def _load_gdf(self):
        import geopandas as gpd

        gdf = gpd.read_file(self.shp_path)
        if gdf.empty:
            self._gdf = gdf
            return

        if gdf.crs is None:
            raise ValueError(f"Shapefile has no CRS: {self.shp_path}")

        self._gdf = gdf

    def rasterize_window(
        self,
        out_shape: tuple[int, int],
        transform,
        crs,
    ) -> np.ndarray:
        """Rasterize humid polygons to a uint8 mask for a given window."""
        if self._gdf is None:
            self._load_gdf()

        gdf = self._gdf
        if gdf is None or gdf.empty:
            return np.zeros(out_shape, dtype=np.uint8)

        if str(gdf.crs) != str(crs):
            gdf = gdf.to_crs(crs)

        shapes = [(geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty]
        if not shapes:
            return np.zeros(out_shape, dtype=np.uint8)

        return rasterize(
            shapes=shapes,
            out_shape=out_shape,
            transform=transform,
            fill=0,
            dtype=np.uint8,
            all_touched=False,
        )
