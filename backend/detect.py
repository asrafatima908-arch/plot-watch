"""
Plot Watch - change detection for a single plot using two Sentinel-2 images.

Usage example:
  python detect.py \
    --before data/before --after data/after \
    --bbox 80.30 26.45 80.31 26.46 \
    --name plot_changed --out ../frontend/results

--bbox is the plot boundary as: min_lon min_lat max_lon max_lat (WGS84, from Google Maps).
--before / --after are folders holding the downloaded Sentinel-2 band files
(B02, B03, B04, B08, B11 as .jp2 or .tif/.tiff, inside any sub-folders).
"""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from scipy.ndimage import label, zoom

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BANDS = ["B02", "B03", "B04", "B08", "B11"]
NATIVE_20M = {"B11"}


def find_band(folder, band):
    """Find the file for a band anywhere inside folder."""
    exts = {".jp2", ".tif", ".tiff"}
    hits = [p for p in Path(folder).rglob("*")
            if p.suffix.lower() in exts and f"_{band}" in p.name]
    if not hits:
        raise FileNotFoundError(f"No file for {band} found in {folder}")
    want = "20m" if band in NATIVE_20M else "10m"
    hits.sort(key=lambda p: want not in str(p))  # prefer the right resolution
    return hits[0]


def read_band(path, bbox, shape=None):
    """Read one band cropped to bbox (lon/lat), resampled to `shape`."""
    with rasterio.open(path) as src:
        l, b, r, t = transform_bounds("EPSG:4326", src.crs, *bbox)
        win = from_bounds(l, b, r, t, src.transform)
        if shape is None:
            shape = (max(2, round(win.height)), max(2, round(win.width)))
        arr = src.read(1, window=win, out_shape=shape,
                       resampling=Resampling.bilinear,
                       boundless=True, fill_value=0).astype("float32")
    return arr, shape


def load_scene(folder, bbox, shape=None):
    bands = {}
    for b in BANDS:
        bands[b], shape = read_band(find_band(folder, b), bbox, shape)
    return bands, shape


def indices(b):
    ndvi = (b["B08"] - b["B04"]) / (b["B08"] + b["B04"] + 1e-6)
    ndbi = (b["B11"] - b["B08"]) / (b["B11"] + b["B08"] + 1e-6)
    return ndvi, ndbi


def rgb(b, scale=3000.0):
    img = np.dstack([b["B04"], b["B03"], b["B02"]]) / scale
    return np.clip(img, 0, 1) ** 0.8


def upscale(img, target=1000):
    """Smooth (bicubic) upscaling so 10 m pixels don't show up as big blocks."""
    k = max(1, round(target / img.shape[1]))
    return np.clip(zoom(img, (k, k, 1), order=3), 0, 1)


def check_plot(before_dir, after_dir, bbox, name, out_dir,
               ndvi_drop=0.15, ndbi_rise=0.05, min_pixels=2, alert_pct=5.0):
    """Returns dict with change percentage, image paths and alert text."""
    before, shape = load_scene(before_dir, bbox)
    after, _ = load_scene(after_dir, bbox, shape)

    ndvi_b, ndbi_b = indices(before)
    ndvi_a, ndbi_a = indices(after)

    valid = (before["B04"] > 0) & (after["B04"] > 0)
    change = ((ndvi_a - ndvi_b) < -ndvi_drop) & ((ndbi_a - ndbi_b) > ndbi_rise) & valid

    # remove isolated speckle (components smaller than min_pixels)
    labels, n = label(change)
    if n:
        sizes = np.bincount(labels.ravel())
        small = np.isin(labels, np.where(sizes < min_pixels)[0])
        change &= ~small

    pct = float(change.sum() / max(valid.sum(), 1) * 100)

    if pct >= alert_pct:
        alert = f"Possible construction or land clearing detected on {pct:.0f}% of your plot."
        level = "alert"
    elif pct >= 1:
        alert = f"Minor change detected on {pct:.1f}% of your plot. We are monitoring it."
        level = "watch"
    else:
        alert = "No significant change detected on your plot."
        level = "clear"

    out = Path(out_dir) / name
    out.mkdir(parents=True, exist_ok=True)

    img_after = rgb(after)
    big_after = upscale(img_after)
    k = big_after.shape[0] // change.shape[0]
    big_mask = np.repeat(np.repeat(change, k, axis=0), k, axis=1)
    overlay = big_after.copy()
    overlay[big_mask] = 0.4 * overlay[big_mask] + 0.6 * np.array([1.0, 0.1, 0.1])
    plt.imsave(out / "before.png", upscale(rgb(before)))
    plt.imsave(out / "after.png", big_after)
    plt.imsave(out / "change.png", overlay)

    result = {
        "plot": name,
        "change_percent": round(pct, 1),
        "level": level,
        "alert": alert,
        "images": {"before": "before.png", "after": "after.png", "change": "change.png"},
    }
    (out / "result.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True,
                    metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"))
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", default="../frontend/results")
    ap.add_argument("--ndvi-drop", type=float, default=0.15)
    ap.add_argument("--ndbi-rise", type=float, default=0.05)
    a = ap.parse_args()
    res = check_plot(a.before, a.after, a.bbox, a.name, a.out,
                     ndvi_drop=a.ndvi_drop, ndbi_rise=a.ndbi_rise)
    print(json.dumps(res, indent=2))
