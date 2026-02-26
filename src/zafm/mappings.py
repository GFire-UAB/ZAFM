"""Mapping tables used by ZAFM.

This project uses:
- WorldCover Map (WCM) land-cover classes (e.g., 10, 20, 30...)
- FirEUrisk fuel classes (e.g., 1111, 21, 33...)
- Scott & Burgan (FBFM40-like) fuel model codes as output (e.g., 147, 183...)

The mapping depends on the bioclimatic regime (humid vs arid).

If you need to adapt to a different land-cover product or a different
reference fuel map, edit these dictionaries.
"""

from __future__ import annotations

from typing import Dict, List

# WCM (WorldCover) -> candidate FirEUrisk classes.
# (Kept from your optimized script; feel free to expand.)
WCM_TO_FIRE_CANDIDATES: Dict[int, List[int]] = {
    10:  [1111, 1112, 1121, 1122, 1211, 1212, 1221, 1222, 1301, 1302, 51],
    20:  [21, 22, 23, 52],
    30:  [31, 32, 33, 53],
    40:  [41, 42],
    50:  [61, 62],  # fixed later to 98
    60:  [7],       # fixed later to 93
    70:  [7],       # fixed later to 92
    80:  [7],       # fixed later to 91
    90:  [53],
    95:  [51],
    100: [53],
}

# WCM classes that map to a single fixed Burgan fuel model.
WCM_FIXED_BURGAN: Dict[int, int] = {
    50: 98,
    60: 93,
    70: 92,
    80: 91,
}

# FirEUrisk -> Burgan mapping in arid/semiarid regime.
REMAP_FIRE_TO_BURGAN_ARID: Dict[int, int] = {
    1111: 147, 1112: 161, 1121: 145, 1122: 165,
    1211: 147, 1212: 161, 1221: 145, 1222: 165,
    1301: 147, 1302: 165, 21: 142, 22: 147,
    23: 145, 31: 102, 32: 104, 33: 107,
    41: 104, 42: 102, 51: 147, 52: 145,
    53: 107, 61: 91, 62: 142, 7: 91,
}

# FirEUrisk -> Burgan mapping in humid regime.
REMAP_FIRE_TO_BURGAN_HUMID: Dict[int, int] = {
    1111: 148, 1112: 162, 1121: 149, 1122: 163,
    1211: 148, 1212: 162, 1221: 149, 1222: 183,
    1301: 148, 1302: 183, 21: 143, 22: 148,
    23: 149, 31: 106, 32: 108, 33: 109,
    41: 106, 42: 106, 51: 148, 52: 149,
    53: 109, 61: 91, 62: 143, 7: 91,
}
