"""Plot Watch - cloud and rain warnings for the chosen dates."""
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

CLOUD_WARN_PCT = 20      # warn if the scene's own cloud % is more than this
WX_CLOUD_WARN_PCT = 70   # warn if average weather cloud % is at least this
RAIN_MM = 1.0            # a day with at least this much rain counts as rainy
WINDOW_DAYS = 5          # look at this many days ending on the image date


def _weather(lat, lon, day):
    end = date.fromisoformat(day)
    start = end - timedelta(days=WINDOW_DAYS - 1)
    q = urllib.parse.urlencode({
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "precipitation_sum,cloud_cover_mean", "timezone": "auto",
    })
    url = "https://archive-api.open-meteo.com/v1/archive?" + q
    with urllib.request.urlopen(url, timeout=8) as r:
        d = json.loads(r.read())["daily"]
    rainy = [t for t, p in zip(d["time"], d["precipitation_sum"]) if p is not None and p >= RAIN_MM]
    clouds = [c for c in d["cloud_cover_mean"] if c is not None]
    return rainy, (sum(clouds) / len(clouds) if clouds else None)


def build_warnings(bbox, items):
    """items: list of (label, 'YYYY-MM-DD', scene_cloud_percent_or_None)."""
    lat, lon = (bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2
    out = []
    for label, day, scene_cloud in items:
        if scene_cloud is not None and scene_cloud > CLOUD_WARN_PCT:
            out.append(f"{label} image ({day}): cloud cover is high (about {round(scene_cloud)}%). "
                       "Clouds can hide the ground or look like change.")
        try:
            rainy, avg_cloud = _weather(lat, lon, day)
        except Exception:
            continue          # weather is optional, never break the analysis
        if avg_cloud is not None and avg_cloud >= WX_CLOUD_WARN_PCT and (scene_cloud is None or scene_cloud <= CLOUD_WARN_PCT):
            out.append(f"{label} date ({day}): the area was mostly cloudy around this date (about {round(avg_cloud)}%).")
        if rainy:
            out.append(f"{label} date ({day}): it rained around this date ({', '.join(rainy)}). "
                       "Wet soil and water can look like change.")
    return out
