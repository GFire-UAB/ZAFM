import rasterio
import numpy as np
from preprocessing import remap_values, convert_tif_to_asc, data_homogenization, read_lc_to_fm
from algorithm import generate_fuel_map

# ---------------------------------------------------------------------
# Input data
# ---------------------------------------------------------------------
fireurisk_path = "../data/raw/Fireurisk_raw.tif"
worldcover_path = "../data/raw/Worldcover_raw.tif"
lc_to_fm_path = "../data/raw/LC_to_FM.json"
climate_regime = 'arid'
# ---------------------------------------------------------------------
# Data homogenization
# ---------------------------------------------------------------------
# Fireurisk clases to burgan in arid/semiarid climate (Catalonia) ---
with rasterio.open(fireurisk_path) as src:
    data = src.read(1)
    remapped_data = remap_values(data,climate_regime)

# Convert to asc ---
convert_tif_to_asc(fireurisk_path, data=remapped_data)
convert_tif_to_asc(worldcover_path)

# Data homogenization ---
fireurisk_asc = "../data/processed/Fireurisk_raw.asc"
worldcover_asc = "../data/processed/Worldcover_raw.asc"

fire_20, world_20 = data_homogenization(fireurisk_asc, worldcover_asc)

# ---------------------------------------------------------------------
# Land cover to fuel model table
# ---------------------------------------------------------------------
lc_to_fm = read_lc_to_fm(lc_to_fm_path)
# ---------------------------------------------------------------------
# ZAFM
# ---------------------------------------------------------------------
generate_fuel_map(lc_to_fm, fire_20, world_20)
