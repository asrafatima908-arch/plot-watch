"""
Plot Watch - fetch satellite crops (no account needed) and run detection.
Sentinel-2 (10 m, 2017+) and Landsat (30 m, 1985+) via Microsoft Planetary Computer.
Only the chosen area is downloaded.
"""
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds
from pystac_client import Client
import planetary_computer

from detect import check_plot, severity
from report import make_report

BANDS = ["B02", "B03", "B04", "B08", "B11"]
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = {"sentinel": "sentinel-2-l2a", "landsat": "landsat-c2-l2"}
RES_M = {"sentinel": 10, "landsat": 30}
LANDSAT_ASSET = {"B02": "blue", "B03": "green", "B04": "red", "B08": "nir08", "B11": "swir16"}


def window_around(day, days):
    d = date.fromisoformat(day)
    return f"{d - timedelta(days=days)}/{d + timedelta(days=days)}"


def _rank(item, source):
    cloud = item.properties.get("eo:cloud_cover", 100)
    if source == "sentinel":
        return cloud
    pen = 0 if item.properties.get("landsat:collection_category", "T1") == "T1" else 50
    if item.properties.get("platform") == "landsat-7" and item.datetime.date() >= date(2003, 6, 1):
        pen += 30  # scan-line gaps after mid 2003
    return cloud + pen


def best_scene(source, bbox, date_range, max_cloud):
    catalog = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    search = catalog.search(collections=[COLLECTION[source]], bbox=bbox, datetime=date_range,
                            query={"eo:cloud_cover": {"lt": max_cloud}})
    items = list(search.items())
    if not items:
        raise RuntimeError(f"No clear satellite image found for {date_range}. "
                           "Try another date, a higher max cloud, or a different image source.")
    return min(items, key=lambda i: _rank(i, source))


def _window(src, bbox):
    l, b, r, t = transform_bounds("EPSG:4326", src.crs, *bbox)
    w = from_bounds(l, b, r, t, src.transform)
    return Window(int(round(w.col_off)), int(round(w.row_off)),
                  max(2, int(round(w.width))), max(2, int(round(w.height))))


def download_crop(href, bbox, out_path, offset=0, landsat=False):
    with rasterio.open(href) as src:
        win = _window(src, bbox)
        data = src.read(1, window=win)
        profile = src.profile.copy()
        profile.update(driver="GTiff", height=data.shape[0], width=data.shape[1],
                       transform=src.window_transform(win), count=1)
    if landsat:  # convert to reflectance x 10000 so it matches Sentinel-2 scale
        refl = data.astype("float32") * 0.0000275 - 0.2
        data = np.where(data == 0, 0, np.clip(refl * 10000, 1, 20000)).astype("uint16")
        profile.update(dtype="uint16", nodata=None)
    elif offset:  # processing baseline >= 4.0 adds +1000
        data = (data.astype("int32") - offset).clip(0).astype(profile["dtype"])
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data, 1)


def local_cloud_pct(item, bbox, source):
    """Percent of cloud/shadow pixels inside the chosen area."""
    try:
        key = "qa_pixel" if source == "landsat" else "SCL"
        with rasterio.open(item.assets[key].href) as src:
            q = src.read(1, window=_window(src, bbox)).astype("int32")
        if source == "landsat":
            valid, cloudy = (q & 1) == 0, (q & 0b11110) > 0
        else:
            valid, cloudy = q != 0, np.isin(q, [3, 8, 9, 10])
        return round(float(cloudy.sum() / max(valid.sum(), 1) * 100), 1)
    except Exception:
        return None


def fetch_scene(source, bbox, date_range, out_dir, max_cloud=20):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    item = best_scene(source, bbox, date_range, max_cloud)
    landsat = source == "landsat"
    offset = 0
    if not landsat:
        offset = 1000 if float(item.properties.get("s2:processing_baseline", "0")) >= 4.0 else 0
    print(f"Using {item.id} ({item.datetime.date()}, cloud {item.properties['eo:cloud_cover']:.1f}%)")
    for band in BANDS:
        key = LANDSAT_ASSET[band] if landsat else band
        download_crop(item.assets[key].href, bbox, out_dir / f"scene_{band}.tif", offset, landsat)
    return {"scene": item.id, "date": str(item.datetime.date()),
            "cloud": round(item.properties["eo:cloud_cover"], 1),
            "local_cloud": local_cloud_pct(item, bbox, source)}


def list_scenes(source, bbox, center_date, window_days=20):
    catalog = Client.open(STAC_URL)
    search = catalog.search(collections=[COLLECTION[source]], bbox=bbox,
                            datetime=window_around(center_date, window_days))
    by_date = {}
    for it in search.items():
        d, c = str(it.datetime.date()), round(it.properties.get("eo:cloud_cover", 100), 1)
        if d not in by_date or c < by_date[d]:
            by_date[d] = c
    return [{"date": d, "cloud": c} for d, c in sorted(by_date.items())]


def analyze(bbox, before_date, after_date, name, source="sentinel", out_dir="../frontend/results",
            max_cloud=20, ndvi_drop=0.15, ndbi_rise=0.05):
    window_days = 20 if source == "sentinel" else 30
    work = Path("data") / name
    try:
        info_b = fetch_scene(source, bbox, window_around(before_date, window_days), work / "before", max_cloud)
        info_a = fetch_scene(source, bbox, window_around(after_date, window_days), work / "after", max_cloud)
        res = check_plot(work / "before", work / "after", bbox, name, out_dir,
                         ndvi_drop=ndvi_drop, ndbi_rise=ndbi_rise)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    res.update(before_scene=info_b, after_scene=info_a, source=source, resolution_m=RES_M[source])
    res["severity"] = severity(res, info_b, info_a, source)
    folder = Path(out_dir) / name
    make_report(res, folder, bbox)
    (folder / "result.json").write_text(json.dumps(res, indent=2))
    return res