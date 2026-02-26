"""Tiling helpers for windowed raster processing."""

from __future__ import annotations

from rasterio.windows import Window


def iter_windows(width: int, height: int, tile_w: int = 2048, tile_h: int = 2048):
    """Yield core windows that tile the full raster."""
    for row_off in range(0, height, tile_h):
        h = min(tile_h, height - row_off)
        for col_off in range(0, width, tile_w):
            w = min(tile_w, width - col_off)
            yield Window(col_off=col_off, row_off=row_off, width=w, height=h)


def clamp_window(win: Window, width: int, height: int) -> Window:
    col_off = int(max(0, win.col_off))
    row_off = int(max(0, win.row_off))
    col_end = int(min(width, win.col_off + win.width))
    row_end = int(min(height, win.row_off + win.height))
    return Window(col_off=col_off, row_off=row_off, width=col_end - col_off, height=row_end - row_off)


def expand_window(win: Window, pad: int) -> Window:
    return Window(
        col_off=int(win.col_off) - pad,
        row_off=int(win.row_off) - pad,
        width=int(win.width) + 2 * pad,
        height=int(win.height) + 2 * pad,
    )


def window_slices(core: Window, halo: Window):
    """Return (row_slice, col_slice) to index the core region inside a halo window."""
    r0 = int(core.row_off - halo.row_off)
    c0 = int(core.col_off - halo.col_off)
    r1 = r0 + int(core.height)
    c1 = c0 + int(core.width)
    return slice(r0, r1), slice(c0, c1)
