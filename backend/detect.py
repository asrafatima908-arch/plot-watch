"""
Plot Watch - change detection, change categories and risk scoring for one area.
Works on any pair of scenes saved as B02/B03/B04/B08/B11 files (Sentinel-2 or converted Landsat).
"""
import json
import math
from datetime import date
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

# key: (label, colour, risk weight 0-100)
CATS = {
    "construction": ("New construction / built-up expansion", (0.85, 0.10, 0.10), 90),
    "paving": ("Road / paving on bare land", (0.55, 0.20, 0.75), 70),
    "clearing": ("Vegetation cleared / bare soil", (0.95, 0.55, 0.10), 60),
    "water_gain": ("New water / waterlogging", (0.10, 0.45, 0.95), 40),
    "water_loss": ("Water body shrinkage", (0.10, 0.75, 0.80), 40),
    "regrowth": ("Vegetation regrowth", (0.20, 0.70, 0.30), 10),
}


def find_band(folder, band):
    exts = {".jp2", ".tif", ".tiff"}
    hits = [p for p in Path(folder).rglob("*")
            if p.suffix.lower() in exts and f"_{band}" in p.name]
    if not hits:
        raise FileNotFoundError(f"No file for {band} found in {folder}")
    want = "20m" if band in NATIVE_20M else "10m"
    hits.sort(key=lambda p: want not in str(p))
    return hits[0]


def read_band(path, bbox, shape=None):
    with rasterio.open(path) as src:
        l, b, r, t = transform_bounds("EPSG:4326", src.crs, *bbox)
        win = from_bounds(l, b, r, t, src.transform)
        if shape is None:
            shape = (max(2, round(win.height)), max(2, round(win.width)))
        arr = src.read(1, window=win, out_shape=shape, resampling=Resampling.bilinear,
                       boundless=True, fill_value=0).astype("float32")
    return arr, shape


def load_scene(folder, bbox, shape=None):
    bands = {}
    for b in BANDS:
        bands[b], shape = read_band(find_band(folder, b), bbox, shape)
    return bands, shape


def indices(b):
    e = 1e-6
    ndvi = (b["B08"] - b["B04"]) / (b["B08"] + b["B04"] + e)   # vegetation
    ndbi = (b["B11"] - b["B08"]) / (b["B11"] + b["B08"] + e)   # built-up
    ndwi = (b["B03"] - b["B08"]) / (b["B03"] + b["B08"] + e)   # water
    return ndvi, ndbi, ndwi


def rgb(b, scale=3000.0):
    return np.clip(np.dstack([b["B04"], b["B03"], b["B02"]]) / scale, 0, 1) ** 0.8


def upscale(img, target=1000):
    k = max(1, round(target / img.shape[1]))
    return np.clip(zoom(img, (k, k, 1), order=3), 0, 1)


def clean(mask, min_pixels):
    labels, n = label(mask)
    if n:
        sizes = np.bincount(labels.ravel())
        mask = mask & ~np.isin(labels, np.where(sizes < min_pixels)[0])
    return mask


def classify(before, after, ndvi_drop, ndbi_rise, min_pixels):
    nv_b, nb_b, nw_b = indices(before)
    nv_a, nb_a, nw_a = indices(after)
    valid = (before["B04"] > 0) & (after["B04"] > 0)
    dv, db = nv_a - nv_b, nb_a - nb_b
    wet_b, wet_a = nw_b > 0.1, nw_a > 0.1
    veg_loss, veg_gain, built = dv < -ndvi_drop, dv > ndvi_drop, db > ndbi_rise
    m = {"water_gain": valid & ~wet_b & wet_a, "water_loss": valid & wet_b & ~wet_a}
    rest = valid & ~m["water_gain"] & ~m["water_loss"]
    m["construction"] = rest & veg_loss & built
    m["clearing"] = rest & veg_loss & ~built
    m["paving"] = rest & ~veg_loss & built & (nv_b < 0.2)
    m["regrowth"] = rest & veg_gain
    return {k: clean(v, min_pixels) for k, v in m.items()}, valid


def check_plot(before_dir, after_dir, bbox, name, out_dir,
               ndvi_drop=0.15, ndbi_rise=0.05, min_pixels=2, alert_pct=5.0):
    before, shape = load_scene(before_dir, bbox)
    after, _ = load_scene(after_dir, bbox, shape)
    masks, valid = classify(before, after, ndvi_drop, ndbi_rise, min_pixels)
    nvalid = max(int(valid.sum()), 1)

    pct_of = {k: float(m.sum() / nvalid * 100) for k, m in masks.items()}
    pct = pct_of["construction"] + pct_of["paving"]   # headline: built-up change

    if pct >= alert_pct:
        alert, level = f"Possible construction or land clearing detected on {pct:.0f}% of your plot.", "alert"
    elif pct >= 1:
        alert, level = f"Minor built-up change detected on {pct:.1f}% of your plot. We are monitoring it.", "watch"
    else:
        alert, level = "No significant built-up change detected on your plot.", "clear"

    # images: every category drawn in its own colour
    after_img = rgb(after)
    big = upscale(after_img)
    k = big.shape[1] // after_img.shape[1]
    overlay, rgba = big.copy(), np.zeros(big.shape[:2] + (4,), np.float32)
    for key, (_, col, _) in CATS.items():
        m = np.repeat(np.repeat(masks[key], k, axis=0), k, axis=1)
        overlay[m] = 0.4 * overlay[m] + 0.6 * np.array(col)
        rgba[m] = [*col, 0.65]
    out = Path(out_dir) / name
    out.mkdir(parents=True, exist_ok=True)
    plt.imsave(out / "before.png", upscale(rgb(before)))
    plt.imsave(out / "after.png", big)
    plt.imsave(out / "change.png", overlay)
    plt.imsave(out / "change_overlay.png", rgba)

    w_km = (bbox[2] - bbox[0]) * 111.32 * math.cos(math.radians((bbox[1] + bbox[3]) / 2))
    h_km = (bbox[3] - bbox[1]) * 110.57
    result = {
        "plot": name, "change_percent": round(pct, 1), "level": level, "alert": alert,
        "area_km2": round(w_km * h_km, 2), "changed_km2": round(pct / 100 * w_km * h_km, 3),
        "breakdown": [{"key": k, "label": CATS[k][0], "percent": round(pct_of[k], 1),
                       "color": "#%02x%02x%02x" % tuple(int(c * 255) for c in CATS[k][1])}
                      for k in CATS],
        "images": {"before": "before.png", "after": "after.png", "change": "change.png",
                   "overlay": "change_overlay.png"},
    }
    (out / "result.json").write_text(json.dumps(result, indent=2))
    return result


def _season_gap_days(d1, d2):
    a = date.fromisoformat(d1).timetuple().tm_yday
    b = date.fromisoformat(d2).timetuple().tm_yday
    g = abs(a - b)
    return min(g, 365 - g)


def severity(res, info_b, info_a, source):
    """Weighted 0-100 risk score (transparent rules, not a trained model)."""
    shares = {b["key"]: b["percent"] for b in res["breakdown"]}
    total = sum(shares.values())
    area_s = min(100.0, res["change_percent"] * 4)
    abs_s = min(100.0, res["changed_km2"] * 50)
    risk_s = sum(shares[k] * CATS[k][2] for k in shares) / total if total > 0 else 0.0
    cloud = max((info_b.get("local_cloud") or info_b["cloud"]), (info_a.get("local_cloud") or info_a["cloud"]))
    gap = _season_gap_days(info_b["date"], info_a["date"])
    conf = 85 - 1.5 * cloud - (10 if source == "landsat" else 0) - (10 if gap > 45 else 0)
    conf = max(20.0, min(95.0, conf))
    score = 0.30 * area_s + 0.15 * abs_s + 0.30 * risk_s + 0.15 * conf + 0.10 * 50  # persistence neutral
    score = round(score)
    level = "Low" if score < 25 else "Moderate" if score < 50 else "High" if score < 75 else "Critical"
    actions = {
        "Low": "No action needed. Keep monitoring.",
        "Moderate": "Review the change map. Compare with other dates before drawing conclusions.",
        "High": "Plan a field check and compare with recent high-resolution imagery.",
        "Critical": "Priority field verification recommended.",
    }
    top = sorted(((v, k) for k, v in shares.items() if v >= 0.5), reverse=True)[:3]
    parts = ", ".join(f"{CATS[k][0].lower()} ({v:.1f}%)" for v, k in top) or "no significant change types"
    why = (f"{res['changed_km2']} km2 of the {res['area_km2']} km2 area shows built-up change "
           f"({res['change_percent']}%). Main change types: {parts}. Rules compare vegetation (NDVI), "
           f"built-up (NDBI) and water (NDWI) indices between the two dates. Confidence {round(conf)}% "
           f"(cloud over area up to {cloud}%, season gap {gap} days).")
    return {"score": score, "level": level, "action": actions[level], "explanation": why,
            "confidence": round(conf),
            "components": {"area": round(area_s), "absolute_area": round(abs_s),
                           "category_risk": round(risk_s), "confidence": round(conf), "persistence": 50}}
