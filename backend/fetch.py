import argparse
import json
import shutil
from datetime import date, timedelta
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
            f"No clear satellite image found for {date_range}. "
            "Try another date, or a wider window."
        )
    return min(items, key=lambda i: i.properties["eo:cloud_cover"])


def download_crop(href, bbox, out_path, offset=0):
    with rasterio.open(href) as src:
        l, b, r, t = transform_bounds("EPSG:4326", src.crs, *bbox)
        w = from_bounds(l, b, r, t, src.transform)
        win = Window(int(round(w.col_off)), int(round(w.row_off)),
                     max(2, int(round(w.width))), max(2, int(round(w.height))))
        data = src.read(1, window=win)
        if offset:
            data = (data.astype("int32") - offset).clip(0).astype(src.dtypes[0])
        profile = src.profile.copy()
        profile.update(driver="GTiff", height=data.shape[0], width=data.shape[1],
                       transform=src.window_transform(win), count=1)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data, 1)


def fetch_scene(bbox, date_range, out_dir, max_cloud=20):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    item = best_scene(bbox, date_range, max_cloud)
    baseline = float(item.properties.get("s2:processing_baseline", "0"))
    offset = 1000 if baseline >= 4.0 else 0
    print(f"Using {item.id} (date {item.datetime.date()}, "
          f"cloud {item.properties['eo:cloud_cover']:.1f}%, offset {offset})")
    for band in BANDS:
        download_crop(item.assets[band].href, bbox,
                      out_dir / f"scene_{band}.tif", offset)
    return {"scene": item.id, "date": str(item.datetime.date()),
            "cloud": round(item.properties["eo:cloud_cover"], 1)}


def window_around(day, days):
    d = date.fromisoformat(day)
    return f"{d - timedelta(days=days)}/{d + timedelta(days=days)}"


def analyze(bbox, before_date, after_date, name, out_dir="../frontend/results",
            window_days=20, max_cloud=20, ndvi_drop=0.15, ndbi_rise=0.05):
    work = Path("data") / name
    try:
        info_b = fetch_scene(bbox, window_around(before_date, window_days),
                             work / "before", max_cloud)
        info_a = fetch_scene(bbox, window_around(after_date, window_days),
                             work / "after", max_cloud)
        res = check_plot(work / "before", work / "after", bbox, name, out_dir,
                         ndvi_drop=ndvi_drop, ndbi_rise=ndbi_rise)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    res["before_scene"], res["after_scene"] = info_b, info_a
    (Path(out_dir) / name / "result.json").write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", nargs=4, type=float, required=True,
                    metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"))
    ap.add_argument("--before-range", required=True)
    ap.add_argument("--after-range", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", default="../frontend/results")
    ap.add_argument("--max-cloud", type=float, default=10)
    ap.add_argument("--ndvi-drop", type=float, default=0.15)
    ap.add_argument("--ndbi-rise", type=float, default=0.05)
    a = ap.parse_args()

    work = Path("data") / a.name
    info_b = fetch_scene(a.bbox, a.before_range, work / "before", a.max_cloud)
    info_a = fetch_scene(a.bbox, a.after_range, work / "after", a.max_cloud)
    res = check_plot(work / "before", work / "after", a.bbox, a.name, a.out,
                     ndvi_drop=a.ndvi_drop, ndbi_rise=a.ndbi_rise)
    res["before_scene"], res["after_scene"] = info_b, info_a
    (Path(a.out) / a.name / "result.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
