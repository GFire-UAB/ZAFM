
from rasterio.warp import calculate_default_transform, reproject, Resampling
import rasterio
from rasterio.enums import Resampling
import numpy as np
import os
import json
from scipy import stats


# ---------------------------------------------------------------------
#  fireurisk clases to burgan in arid/semiarid climate (Catalonia)
# ---------------------------------------------------------------------
def remap_values(data, climate_type):
    remap_dict_arid = {
        1111: 147, 1112: 161, 1121: 145, 1122: 165,
        1211: 147, 1212: 161, 1221: 145, 1222: 165,
        1301: 147, 1302: 165, 21: 142, 22: 147,
        23: 145, 31: 102, 32: 104, 33: 107,
        41: 104, 42: 102, 51: 147, 52: 145,
        53: 107, 61: 91, 62: 142, 7: 91
    }

    remap_dict_humid = {
        1111: 148, 1112: 162, 1121: 149, 1122: 163,
        1211: 148, 1212: 162, 1221: 149, 1222: 183,
        1301: 148, 1302: 183, 21: 143, 22: 148,
        23: 149, 31: 106, 32: 108, 33: 109,
        41: 106, 42: 106, 51: 148, 52: 149,
        53: 109, 61: 91, 62: 143, 7: 91
    }

    # The climate regime (arid or humid) depends on the study area
    if climate_type == 'arid':
        remap_dict = remap_dict_arid
    elif climate_type == 'humid':
        remap_dict = remap_dict_humid
    else:
        raise ValueError("climate_type must be 'arid' or 'humid'")

    remapped_data = np.copy(data)
    for old_value, new_value in remap_dict.items():
        remapped_data[data == old_value] = new_value

    return remapped_data

# ---------------------------------------------------------------------
# Reproject raster to 25831 (Catalonia)
# ---------------------------------------------------------------------
def reproject_to_epsg(input_tif, target_epsg=25831, output_dir="../data/processed"):
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Build output path in processed folder
    base_name = os.path.basename(input_tif)
    output_tif = os.path.join(output_dir, base_name)

    with rasterio.open(input_tif) as src:
        transform, width, height = calculate_default_transform(
            src.crs, f"EPSG:{target_epsg}", src.width, src.height, *src.bounds
        )

        kwargs = src.meta.copy()
        kwargs.update({
            "crs": f"EPSG:{target_epsg}",
            "transform": transform,
            "width": width,
            "height": height
        })

        with rasterio.open(output_tif, "w", **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=f"EPSG:{target_epsg}",
                    resampling=Resampling.nearest
                )

    return output_tif

# ---------------------------------------------------------------------
# Convert TIF to ASC
# ---------------------------------------------------------------------
def convert_tif_to_asc(input_tif, data=None, output_dir="../data/processed"):
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Build output filename in processed/
    base = os.path.splitext(os.path.basename(input_tif))[0]
    output_asc = os.path.join(output_dir, base + ".asc")

    with rasterio.open(input_tif) as src:
        # If no data is provided, read directly from the TIF
        if data is None:
            data = src.read(1)

        transform = src.transform
        crs = src.crs

        # Convert only the data array to integers
        data = data.astype(np.int32)

        # Copy metadata and update for ASCII Grid format
        meta = src.meta.copy()
        meta.update({
            'driver': 'AAIGrid',
            'dtype': 'int32',  # matriz en enteros
            'count': 1,
            'crs': crs,
            'transform': transform
        })

        # Write the ASC file
        with rasterio.open(output_asc, 'w', **meta) as dst:
            dst.write(data, 1)

    return output_asc

# ---------------------------------------------------------------------
# Resample two asc raster to same resolution and aligns them
# ---------------------------------------------------------------------

def data_homogenization(fireurisk_asc, worldcover_asc, target_res=20, output_dir="../data/processed"):
    os.makedirs(output_dir, exist_ok=True)

    # Load both rasters
    with rasterio.open(fireurisk_asc) as f_src, rasterio.open(worldcover_asc) as w_src:
        # Determine the transform and shape for target resolution
        x_min = max(f_src.bounds.left, w_src.bounds.left)
        y_max = min(f_src.bounds.top, w_src.bounds.top)
        x_max = min(f_src.bounds.right, w_src.bounds.right)
        y_min = max(f_src.bounds.bottom, w_src.bounds.bottom)

        new_width = int(np.ceil((x_max - x_min) / target_res))
        new_height = int(np.ceil((y_max - y_min) / target_res))

        new_transform = rasterio.transform.from_origin(x_min, y_max, target_res, target_res)

        def resample_raster(src, out_shape, out_transform):
            # Decide resampling method
            scale_x = src.width / out_shape[1]
            scale_y = src.height / out_shape[0]

            if scale_x > 1 or scale_y > 1:
                # reducing resolution → mode of discrete classes
                data = src.read(
                    out_shape=out_shape,
                    resampling=Resampling.mode
                )[0]
            else:
                # increasing resolution → replicate cells
                data = src.read(
                    out_shape=out_shape,
                    resampling=Resampling.nearest
                )[0]
            return data

        f_resampled = resample_raster(f_src, (new_height, new_width), new_transform)
        w_resampled = resample_raster(w_src, (new_height, new_width), new_transform)

        # Update metadata
        meta = f_src.meta.copy()
        meta.update({
            'driver': 'AAIGrid',
            'dtype': 'int32',
            'count': 1,
            'height': new_height,
            'width': new_width,
            'transform': new_transform
        })

        # Save outputs
        f_base = os.path.splitext(os.path.basename(fireurisk_asc))[0] + "_20.asc"
        w_base = os.path.splitext(os.path.basename(worldcover_asc))[0] + "_20.asc"

        f_out = os.path.join(output_dir, f_base)
        w_out = os.path.join(output_dir, w_base)

        with rasterio.open(f_out, 'w', **meta) as dst:
            dst.write(f_resampled.astype(np.int32), 1)

        with rasterio.open(w_out, 'w', **meta) as dst:
            dst.write(w_resampled.astype(np.int32), 1)

    return f_out, w_out


# ---------------------------------------------------------------------
# Read LC to FM table
# ---------------------------------------------------------------------
def read_lc_to_fm(file_path):
    with open(file_path, "r") as f:
        data = json.load(f)
    return data