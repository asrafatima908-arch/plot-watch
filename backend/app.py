"""
Plot Watch web server.
Run:  python app.py   then open the forwarded port 5000.
"""
import json
import math
import re
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from fetch import analyze, list_scenes

MAX_KM, MIN_KM = 6.0, 0.3
RESULTS = Path("../frontend/results")
NAME_RE = re.compile(r"^run_[0-9a-f]{8}$")

app = Flask(__name__, static_folder="../frontend", static_url_path="")


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


def parse_request(d):
    """Returns (bbox, before, after, w_km, h_km, source, error)."""
    fail = lambda m: (None, None, None, 0, 0, None, m)
    try:
        west, south, east, north = [float(x) for x in d["bbox"]]
        before = date.fromisoformat(d["before_date"])
        after = date.fromisoformat(d["after_date"])
    except (KeyError, ValueError, TypeError):
        return fail("Please choose an area on the map and both dates.")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        return fail("The selected area is not valid.")
    lat = (south + north) / 2
    w_km = (east - west) * 111.32 * math.cos(math.radians(lat))
    h_km = (north - south) * 110.57
    choice = d.get("source", "auto")
    source = choice if choice in ("sentinel", "landsat") else ("landsat" if before < date(2017, 1, 1) else "sentinel")
    err = None
    if max(w_km, h_km) > MAX_KM:
        err = f"Area too large. Keep each side under {MAX_KM:g} km."
    elif min(w_km, h_km) < MIN_KM:
        err = f"Area too small. Keep each side at least {MIN_KM:g} km."
    elif source == "landsat" and min(w_km, h_km) < 1:
        err = "Landsat images are 30 m, so keep each side at least 1 km."
    elif before >= after:
        err = "The 'before' date must be earlier than the 'after' date."
    elif after > date.today():
        err = "The 'after' date cannot be in the future."
    elif before < date(1985, 1, 1):
        err = "Images are available from 1985 onward."
    elif source == "sentinel" and before < date(2017, 1, 1):
        err = "Sentinel-2 starts in 2017. Choose Auto or Landsat for earlier dates."
    return [west, south, east, north], before, after, w_km, h_km, source, err


@app.route("/api/scenes", methods=["POST"])
def api_scenes():
    bbox, before, after, _, _, source, err = parse_request(request.get_json(force=True))
    if err:
        return jsonify(error=err), 400
    win = 20 if source == "sentinel" else 30
    try:
        return jsonify(before=list_scenes(source, bbox, before.isoformat(), win),
                       after=list_scenes(source, bbox, after.isoformat(), win), source=source)
    except Exception as e:
        return jsonify(error=f"Could not check images: {e}"), 500


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    d = request.get_json(force=True)
    bbox, before, after, w_km, h_km, source, err = parse_request(d)
    if err:
        return jsonify(error=err), 400
    try:
        max_cloud = min(80.0, max(1.0, float(d.get("max_cloud", 20))))
    except (ValueError, TypeError):
        max_cloud = 20.0
    name = "run_" + uuid.uuid4().hex[:8]
    try:
        res = analyze(bbox, before.isoformat(), after.isoformat(), name, source=source, max_cloud=max_cloud)
    except RuntimeError as e:
        return jsonify(error=str(e)), 404
    except Exception as e:
        return jsonify(error=f"Could not process this request: {e}"), 500
    res["image_urls"] = {k: f"results/{name}/{v}" for k, v in res["images"].items()}
    res["pdf_url"] = f"results/{name}/report.pdf"
    res["area_km"] = [round(w_km, 1), round(h_km, 1)]
    res["bbox"] = bbox
    res["created"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    (RESULTS / name / "result.json").write_text(json.dumps(res, indent=2))  # saved copy
    return jsonify(res)


@app.route("/api/history")
def api_history():
    items = []
    for f in RESULTS.glob("run_*/result.json"):
        try:
            r = json.loads(f.read_text())
            if "severity" not in r or "image_urls" not in r:
                continue
            b = r["bbox"]
            items.append({"name": r["plot"], "created": r.get("created", ""), "percent": r["change_percent"],
                          "score": r["severity"]["score"], "severity": r["severity"]["level"],
                          "before": r["before_scene"]["date"], "after": r["after_scene"]["date"],
                          "source": r["source"],
                          "centre": [round((b[1] + b[3]) / 2, 4), round((b[0] + b[2]) / 2, 4)]})
        except Exception:
            continue
    items.sort(key=lambda x: x["created"], reverse=True)
    return jsonify(items[:50])


@app.route("/api/history/<name>", methods=["GET", "DELETE"])
def api_history_item(name):
    folder = RESULTS / name
    if not NAME_RE.match(name) or not (folder / "result.json").exists():
        return jsonify(error="Not found."), 404
    if request.method == "DELETE":
        shutil.rmtree(folder, ignore_errors=True)
        return jsonify(ok=True)
    return jsonify(json.loads((folder / "result.json").read_text()))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
