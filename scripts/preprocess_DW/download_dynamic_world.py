#!/usr/bin/env python3
"""Export a temporal Dynamic World composite from Google Earth Engine.

The output is the pixel-wise temporal MODE of the Dynamic World ``label``
band for an inclusive date interval. Exports are submitted asynchronously to
Google Drive as tiled Cloud Optimized GeoTIFFs.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Sequence, Tuple

import ee


DYNAMIC_WORLD_COLLECTION = "GOOGLE/DYNAMICWORLD/V1"
BOUNDARIES_COLLECTION = "WM/geoLab/geoBoundaries/600/ADM0"
NODATA_VALUE = 255


@dataclass(frozen=True)
class ZoneConfig:
    code: str
    slug: str
    description: str
    bbox: Tuple[float, float, float, float]


ZONE_CONFIGS: Dict[str, ZoneConfig] = {
    "ESP": ZoneConfig(
        "ESP",
        "peninsula_baleares",
        "Spain: Iberian Peninsula and Balearic Islands",
        (-9.60, 35.95, 4.50, 44.20),
    ),
    "FRA": ZoneConfig(
        "FRA",
        "francia_metropolitana_corcega",
        "Metropolitan France and Corsica",
        (-5.60, 41.00, 10.00, 51.60),
    ),
    "PRT": ZoneConfig(
        "PRT",
        "portugal_continental",
        "Continental Portugal",
        (-9.70, 36.80, -6.00, 42.30),
    ),
    "ITA": ZoneConfig(
        "ITA",
        "italia",
        "Italy, including Sicily and Sardinia",
        (6.30, 35.30, 18.80, 47.20),
    ),
    "GRC": ZoneConfig(
        "GRC",
        "grecia",
        "Greece",
        (19.00, 34.50, 30.00, 42.10),
    ),
}


def parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}. Use YYYY-MM-DD."
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export the temporal mode of the Dynamic World label band "
            "for one or more Southern European zones."
        )
    )
    parser.add_argument(
        "--zones",
        nargs="+",
        required=True,
        choices=sorted(ZONE_CONFIGS),
        metavar="ZONE",
        help="One or more zones: ESP FRA PRT ITA GRC.",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        type=parse_iso_date,
        help="First included date, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        type=parse_iso_date,
        help="Last included date, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--project",
        required=True,
        help=(
            "Google Cloud project ID configured for Earth Engine. The "
            "authenticated user must own it or have permission to use it."
        ),
    )
    parser.add_argument(
        "--drive-folder",
        default="Dynamic_World_exports",
        help="Google Drive folder name. Default: Dynamic_World_exports.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=10.0,
        help="Export pixel size in metres. Default: 10.",
    )
    parser.add_argument(
        "--crs",
        default="EPSG:3035",
        help="Output CRS. Default: EPSG:3035.",
    )
    parser.add_argument(
        "--file-dimensions",
        type=int,
        default=16384,
        help=(
            "Maximum width and height of each GeoTIFF part in pixels. "
            "Default: 16384."
        ),
    )
    parser.add_argument(
        "--shard-size",
        type=int,
        default=256,
        help="Earth Engine computation shard size. Default: 256.",
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=100,
        help="Batch task priority from 0 to 9999. Default: 100.",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="Custom prefix; valid only when one zone is requested.",
    )
    parser.add_argument(
        "--authenticate",
        action="store_true",
        help="Run ee.Authenticate() before initialization.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without starting export tasks.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.end_date < args.start_date:
        raise ValueError("--end-date must be on or after --start-date.")
    if args.scale <= 0:
        raise ValueError("--scale must be greater than zero.")
    if args.shard_size <= 0 or args.file_dimensions <= 0:
        raise ValueError("Shard and file dimensions must be greater than zero.")
    if args.file_dimensions % args.shard_size != 0:
        raise ValueError(
            "--file-dimensions must be a multiple of --shard-size."
        )
    if not 0 <= args.priority <= 9999:
        raise ValueError("--priority must be between 0 and 9999.")
    if args.prefix and len(args.zones) != 1:
        raise ValueError("--prefix can only be used with a single zone.")


def initialize_earth_engine(project: str, authenticate: bool) -> None:
    if authenticate:
        ee.Authenticate()
    try:
        ee.Initialize(project=project)
    except Exception as exc:
        raise RuntimeError(
            "Earth Engine initialization failed. Run `earthengine authenticate` "
            "or use --authenticate, and check --project."
        ) from exc


def get_zone_geometry(zone: ZoneConfig) -> ee.Geometry:
    countries = ee.FeatureCollection(BOUNDARIES_COLLECTION)
    selected = countries.filter(ee.Filter.eq("shapeGroup", zone.code))

    feature_count = int(selected.size().getInfo())
    if feature_count == 0:
        raise RuntimeError(
            f"No boundary found for {zone.code} in {BOUNDARIES_COLLECTION}."
        )

    country_geometry = ee.Feature(selected.first()).geometry()
    window = ee.Geometry.Rectangle(
        coords=list(zone.bbox),
        proj="EPSG:4326",
        geodesic=False,
    )
    return country_geometry.intersection(window, maxError=100)


def make_output_prefix(zone: ZoneConfig, start_date: date, end_date: date) -> str:
    if (
        start_date.month == 1
        and start_date.day == 1
        and start_date.year == end_date.year
    ):
        return (
            f"DW_{start_date.year}_{zone.slug}_"
            f"{end_date.strftime('%Y%m%d')}"
        )

    return (
        f"DW_{zone.slug}_{start_date.strftime('%Y%m%d')}_"
        f"{end_date.strftime('%Y%m%d')}"
    )


def create_mode_image(
    aoi: ee.Geometry,
    start_date: date,
    end_date: date,
    zone: ZoneConfig,
):
    # The CLI end date is inclusive; Earth Engine filterDate end is exclusive.
    end_exclusive = end_date + timedelta(days=1)

    collection = (
        ee.ImageCollection(DYNAMIC_WORLD_COLLECTION)
        .filterBounds(aoi)
        .filterDate(start_date.isoformat(), end_exclusive.isoformat())
        .select("label")
    )

    image_count = int(collection.size().getInfo())
    if image_count == 0:
        raise RuntimeError(
            f"No Dynamic World images found for {zone.code} between "
            f"{start_date} and {end_date}."
        )

    mode = collection.mode().rename("label").toUint8()

    # Dynamic World class 0 is water, so NoData is encoded as 255.
    export_image = (
        mode.unmask(value=NODATA_VALUE, sameFootprint=False)
        .clip(aoi)
        .set(
            {
                "source_collection": DYNAMIC_WORLD_COLLECTION,
                "composite_method": "pixel-wise temporal mode",
                "start_date_inclusive": start_date.isoformat(),
                "end_date_inclusive": end_date.isoformat(),
                "zone_code": zone.code,
                "zone_description": zone.description,
                "nodata_value": NODATA_VALUE,
            }
        )
    )
    return export_image, image_count


def submit_export(
    *,
    image,
    aoi,
    prefix: str,
    drive_folder: str,
    scale: float,
    crs: str,
    file_dimensions: int,
    shard_size: int,
    priority: int,
    dry_run: bool,
):
    if dry_run:
        return None

    task = ee.batch.Export.image.toDrive(
        image=image,
        description=prefix,
        folder=drive_folder,
        fileNamePrefix=prefix,
        region=aoi,
        scale=scale,
        crs=crs,
        maxPixels=10_000_000_000_000,
        shardSize=shard_size,
        fileDimensions=file_dimensions,
        skipEmptyTiles=True,
        fileFormat="GeoTIFF",
        formatOptions={
            "cloudOptimized": True,
            "noData": NODATA_VALUE,
        },
        priority=priority,
    )
    task.start()
    return task.id


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        validate_args(args)
        initialize_earth_engine(args.project, args.authenticate)

        print("Dynamic World temporal-mode exports")
        print(f"Inclusive dates: {args.start_date} to {args.end_date}")
        print(f"Output grid: {args.crs}, {args.scale:g} m")
        print(f"Google Drive folder: {args.drive_folder}")
        print(f"NoData: {NODATA_VALUE}\n")

        started = 0
        for zone_code in args.zones:
            zone = ZONE_CONFIGS[zone_code]
            prefix = args.prefix or make_output_prefix(
                zone, args.start_date, args.end_date
            )

            print(f"[{zone.code}] {zone.description}")
            print(f"  Prefix: {prefix}")

            aoi = get_zone_geometry(zone)
            image, image_count = create_mode_image(
                aoi, args.start_date, args.end_date, zone
            )
            print(f"  Source images intersecting AOI: {image_count}")

            task_id = submit_export(
                image=image,
                aoi=aoi,
                prefix=prefix,
                drive_folder=args.drive_folder,
                scale=args.scale,
                crs=args.crs,
                file_dimensions=args.file_dimensions,
                shard_size=args.shard_size,
                priority=args.priority,
                dry_run=args.dry_run,
            )

            if args.dry_run:
                print("  DRY RUN: task not started.\n")
            else:
                started += 1
                print(f"  Task started: {task_id}\n")

        if args.dry_run:
            print("Validation completed. No tasks were submitted.")
        else:
            print(f"{started} task(s) submitted.")
            print("Task monitor: https://code.earthengine.google.com/tasks")
        return 0

    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
