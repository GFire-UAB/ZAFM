import numpy as np
import rasterio
import os

def generate_fuel_map(lc_to_fm, fire_map_path, world_map_path, output_dir= '../output'):
    def closest_category_spatial(x, y, candidates, fireurisk_data):
        best_value = None
        min_distance = float('inf')
        for candidate in candidates:
            candidate_indices = np.argwhere(fireurisk_data == candidate)
            if candidate_indices.size > 0:
                distances = np.sqrt((candidate_indices[:, 0] - x) ** 2 +
                                    (candidate_indices[:, 1] - y) ** 2)
                min_candidate_distance = np.min(distances)
                if min_candidate_distance < min_distance:
                    min_distance = min_candidate_distance
                    best_value = candidate
        return best_value

    # Split dictionary into single-value and multi-value entries
    single_value_dict = {k: v for k, v in lc_to_fm.items() if len(v) == 1}
    multi_value_dict = {k: v for k, v in lc_to_fm.items() if len(v) > 1}

    # Load rasters
    with rasterio.open(world_map_path) as world_dataset, rasterio.open(fire_map_path) as fire_dataset:
        world_data = world_dataset.read(1)
        fire_data = fire_dataset.read(1)
        profile = world_dataset.profile

    # Prepare output array
    assigned_values = np.zeros_like(world_data, dtype=np.float32)

    # Assign values
    for i in range(world_data.shape[0]):
        for j in range(world_data.shape[1]):
            world_value = str(int(world_data[i, j]))  # Ensure key is a string
            if world_value in lc_to_fm:
                if world_value in multi_value_dict:
                    assigned_values[i, j] = closest_category_spatial(i, j, multi_value_dict[world_value], fire_data)

                else:
                    assigned_values[i, j] = single_value_dict[world_value][0]

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "ZAFM_fuel_map.asc")
    # Save raster
    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(assigned_values, 1)








