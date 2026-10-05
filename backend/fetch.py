"""
Plot Watch - automatically fetch Sentinel-2 images for a plot, then run detection.

No account needed. Uses Microsoft Planetary Computer (free Sentinel-2 L2A archive)
and downloads ONLY the plot area (a few MB), not the full 1 GB product.

Usage:
  python fetch.py --bbox 80.30 26.45 80.31 26.46 \
    --before-range 2024-01-01/2024-02-28 \
    --after-range  2026-01-01/2026-02-28 \
    --name plot_changed --out ../frontend/results
"""
import argparse
import json
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds
from pystac_client import Client
import planetary_computer

from detect import check_plot

BANDS = ["B02", "B03", "B04", "B08", "B11"]
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


def best_scene(bbox, date_range, max_cloud):
    """Return the least-cloudy Sentinel-2 L2A scene covering bbox in date_range."""
    catalog = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": max_cloud}},
    )
    items = list(search.items())
    if not items:
        raise RuntimeError(
            f"No scenes under {max_cloud}% cloud for {date_range}. "
            "Try a wider date range or a higher --max-cloud."
        )
    return min(items, key=lambda i: i.properties["eo:cloud_cover"])


def download_crop(href, bbox, out_path):
    """Download only the bbox window of a remote GeoTIFF and save it locally."""
    with rasterio.open(href) as src:
        l, b, r, t = transform_bounds("EPSG:4326", src.crs, *bbox)
        w = from_bounds(l, b, r, t, src.transform)
        win = Window(int(round(w.col_off)), int(round(w.row_off)),
                     max(2, int(round(w.width))), max(2, int(round(w.height))))
        data = src.read(1, window=win)
        profile = src.profile.copy()
        profile.update(driver="GTiff", height=data.shape[0], width=data.shape[1],
                       transform=src.window_transform(win), count=1)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data, 1)


def fetch_scene(bbox, date_range, out_dir, max_cloud=10):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    item = best_scene(bbox, date_range, max_cloud)
    print(f"Using scene {item.id} "
          f"(date {item.datetime.date()}, cloud {item.properties['eo:cloud_cover']:.1f}%)")
    for band in BANDS:
        download_crop(item.assets[band].href, bbox, out_dir / f"scene_{band}.tif")
    return {"scene": item.id, "date": str(item.datetime.date()),
            "cloud": round(item.properties["eo:cloud_cover"], 1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", nargs=4, type=float, required=True,
                    metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"))
    ap.add_argument("--before-range", required=True, help="e.g. 2024-01-01/2024-02-28")
    ap.add_argument("--after-range", required=True, help="e.g. 2026-01-01/2026-02-28")
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", default="../frontend/results")
    ap.add_argument("--max-cloud", type=float, default=10)
    ap.add_argument("--ndvi-drop", type=float, default=0.15)
    ap.add_argument("--ndbi-rise", type=float, default=0.05)
    a = ap.parse_args()

    print("Fetching BEFORE image...")
    info_b = fetch_scene(a.bbox, a.before_range, f"data/{a.name}/before", a.max_cloud)
    print("Fetching AFTER image...")
    info_a = fetch_scene(a.bbox, a.after_range, f"data/{a.name}/after", a.max_cloud)

    print("Running change detection...")
    res = check_plot(f"data/{a.name}/before", f"data/{a.name}/after", a.bbox,
                     a.name, a.out, ndvi_drop=a.ndvi_drop, ndbi_rise=a.ndbi_rise)
    res["before_scene"], res["after_scene"] = info_b, info_a
    (Path(a.out) / a.name / "result.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
