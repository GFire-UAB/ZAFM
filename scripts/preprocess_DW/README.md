# Dynamic World preprocessing for ZAFM

This directory contains the preprocessing code used to obtain a dated
Dynamic World land-cover map before applying ZAFM.

The workflow makes it possible to generate a ZAFM fuel map representative of
a selected year or any user-defined date interval, rather than relying only
on a fixed land-cover reference year.

## Script

- `download_dynamic_world.py`: creates Google Earth Engine batch export tasks
  for the Dynamic World temporal composite.

Supported zones:

| Code | Exported area |
|---|---|
| `ESP` | Iberian Peninsula and Balearic Islands |
| `FRA` | Metropolitan France and Corsica |
| `PRT` | Continental Portugal |
| `ITA` | Italy, including Sicily and Sardinia |
| `GRC` | Greece |

Country boundaries are taken from the geoBoundaries ADM0 collection and
intersected with a geographic window to remove overseas territories that are
outside the target product.

## Temporal mode: not an arithmetic mean

Dynamic World provides a `label` band with integer categorical values from
0 to 8:

| Value | Class |
|---:|---|
| 0 | Water |
| 1 | Trees |
| 2 | Grass |
| 3 | Flooded vegetation |
| 4 | Crops |
| 5 | Shrub and scrub |
| 6 | Built area |
| 7 | Bare ground |
| 8 | Snow and ice |

The script calculates the **pixel-wise temporal mode** of the `label` band:
for every 10 m pixel, the class occurring most frequently among the valid
Dynamic World observations in the selected period is retained. Clouds and
cloud shadows are already masked in the source collection. When several
classes are tied for the mode, Earth Engine returns the smallest tied value.

This temporal mode reduces scene-to-scene noise and produces one categorical
land-cover layer that can be used as the high-resolution land-cover input to
ZAFM.

## Output

Each task exports:

- one `label` band;
- `uint8` values;
- Dynamic World classes `0-8`;
- NoData value `255`;
- 10 m pixel size by default;
- `EPSG:3035` by default;
- tiled Cloud Optimized GeoTIFF parts;
- filenames sharing one common prefix.

Large countries are split into several GeoTIFF files using
`fileDimensions=16384`. The parts can later be mosaicked into a national
raster before FirEUrisk is aligned to the Dynamic World grid and ZAFM is run.

## Installation

Install the Earth Engine Python API:

```bash
python -m pip install earthengine-api
```

Authenticate once:

```bash
earthengine authenticate
```

## Authentication, Cloud project and Google Drive destination

The authenticated Google account and the Google Cloud project have different
roles:

- **Authenticated Google account**: the account selected during
  `earthengine authenticate` or `ee.Authenticate()`. The export files are
  written to this account's personal Google Drive.
- **`--drive-folder`**: the name of the folder in that authenticated user's
  Google Drive. If the folder does not exist, Earth Engine creates it in the
  Drive root. This parameter is a folder name, not a filesystem path and not
  a folder inside the Google Cloud project.
- **`--project`**: the Google Cloud **project ID** used to initialize and run
  Earth Engine requests. The project must have the Earth Engine API enabled,
  be registered for the appropriate use, and the authenticated user must
  have permission to use it.

The Cloud project does not necessarily have to be created by the person
running the script. It may be:

1. a project created and configured by that user; or
2. a shared institutional or research project to which that user has been
   granted the required permissions.

Therefore, each user should replace:

```text
--project YOUR_GOOGLE_CLOUD_PROJECT
```

with a project ID they are authorized to use. For example:

```text
--project my-earth-engine-project
```

The selected project controls Earth Engine access, task execution and
associated quotas or billing configuration. It does **not** determine which
Google Drive receives the files: the destination Drive belongs to the
authenticated Google account.

A typical first-time setup is:

```bash
python -m pip install earthengine-api
earthengine authenticate
```

Then run the script with the appropriate project ID:

```bash
python scripts/preprocess_DW/download_dynamic_world.py \
  --zones ESP \
  --start-date 2026-01-01 \
  --end-date 2026-07-31 \
  --project YOUR_GOOGLE_CLOUD_PROJECT \
  --drive-folder Dynamic_World_2026
```

Alternatively, the script can start the authentication flow itself:

```bash
python scripts/preprocess_DW/download_dynamic_world.py \
  --authenticate \
  --zones ESP \
  --start-date 2026-01-01 \
  --end-date 2026-07-31 \
  --project YOUR_GOOGLE_CLOUD_PROJECT \
  --drive-folder Dynamic_World_2026
```

## Dates

Both command-line dates are **inclusive**. For example:

```text
--start-date 2026-01-01 --end-date 2026-07-31
```

includes observations from 1 January through 31 July 2026. Internally, the
script adds one day to the end date because Earth Engine uses an exclusive
upper date boundary.

## Example: submit Spain, France, Portugal and Italy

```bash
python scripts/preprocess_DW/download_dynamic_world.py \
  --zones ESP FRA PRT ITA \
  --start-date 2026-01-01 \
  --end-date 2026-07-31 \
  --project YOUR_GOOGLE_CLOUD_PROJECT \
  --drive-folder Dynamic_World_2026
```

This creates four tasks with these prefixes:

```text
DW_2026_peninsula_baleares_20260731
DW_2026_francia_metropolitana_corcega_20260731
DW_2026_portugal_continental_20260731
DW_2026_italia_20260731
```

## Example: Greece

```bash
python scripts/preprocess_DW/download_dynamic_world.py \
  --zones GRC \
  --start-date 2026-01-01 \
  --end-date 2026-07-31 \
  --project YOUR_GOOGLE_CLOUD_PROJECT \
  --drive-folder Dynamic_World_2026
```

Expected prefix:

```text
DW_2026_grecia_20260731
```

## Example: a non-annual interval

```bash
python scripts/preprocess_DW/download_dynamic_world.py \
  --zones ESP \
  --start-date 2026-05-01 \
  --end-date 2026-07-31 \
  --project YOUR_GOOGLE_CLOUD_PROJECT
```

Because this interval does not start on 1 January, both dates are included in
the automatic prefix:

```text
DW_peninsula_baleares_20260501_20260731
```

## Useful options

```text
--zones ESP FRA PRT ITA GRC
--start-date YYYY-MM-DD
--end-date YYYY-MM-DD
--project PROJECT_ID
--drive-folder FOLDER_NAME
--scale 10
--crs EPSG:3035
--file-dimensions 16384
--shard-size 256
--priority 100
--dry-run
--authenticate
```

Use `--dry-run` to validate the parameters and source availability without
starting export tasks.

Earth Engine tasks can be monitored at:

```text
https://code.earthengine.google.com/tasks
```

## Subsequent ZAFM workflow

After downloading the exported GeoTIFF parts:

1. mosaic the Dynamic World parts for each zone;
2. align and resample FirEUrisk to the exact Dynamic World grid using nearest
   neighbour;
3. run the Dynamic World-compatible ZAFM mapping;
4. create the final GeoTIFF/COG and internal overviews for distribution and
   fast visualization.

Nearest-neighbour resampling must be used because both Dynamic World and
FirEUrisk contain categorical values.

## Data sources and attribution

Dynamic World V1:

- Earth Engine collection: `GOOGLE/DYNAMICWORLD/V1`
- Spatial resolution: 10 m
- License: CC BY 4.0
- Required attribution: “This dataset is produced for the Dynamic World
  Project by Google in partnership with National Geographic Society and the
  World Resources Institute.”

Country boundaries:

- Earth Engine collection: `WM/geoLab/geoBoundaries/600/ADM0`
- geoBoundaries v6.0.0
- License: CC BY 4.0

Users should cite Dynamic World, the boundary dataset, FirEUrisk and ZAFM in
derived scientific products.
