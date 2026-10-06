"""
Plot Watch web server.
Run:  python app.py   then open the forwarded port 5000.
"""
import math
import uuid
from datetime import date

from flask import Flask, jsonify, request, send_from_directory

from fetch import analyze, list_scenes

MAX_KM, MIN_KM = 6.0, 0.3  # allowed side length of the selected area

app = Flask(__name__, static_folder="../frontend", static_url_path="")


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


def parse_request(d):
    """Validate area and dates. Returns (bbox, before, after, w_km, h_km, error_message)."""
    try:
        west, south, east, north = [float(x) for x in d["bbox"]]
        before = date.fromisoformat(d["before_date"])
        after = date.fromisoformat(d["after_date"])
    except (KeyError, ValueError, TypeError):
        return None, None, None, 0, 0, "Please choose an area on the map and both dates."
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        return None, None, None, 0, 0, "The selected area is not valid."
    lat = (south + north) / 2
    w_km = (east - west) * 111.32 * math.cos(math.radians(lat))
    h_km = (north - south) * 110.57
    err = None
    if max(w_km, h_km) > MAX_KM:
        err = f"Area too large. Keep each side under {MAX_KM:g} km."
    elif min(w_km, h_km) < MIN_KM:
        err = f"Area too small. Keep each side at least {MIN_KM:g} km."
    elif before >= after:
        err = "The 'before' date must be earlier than the 'after' date."
    elif after > date.today():
        err = "The 'after' date cannot be in the future."
    elif before < date(2017, 1, 1):
        err = "Sentinel-2 images are available from 2017 onward."
    return [west, south, east, north], before, after, w_km, h_km, err


@app.route("/api/scenes", methods=["POST"])
def api_scenes():
    d = request.get_json(force=True)
    bbox, before, after, _, _, err = parse_request(d)
    if err:
        return jsonify(error=err), 400
    try:
        return jsonify(before=list_scenes(bbox, before.isoformat()),
                       after=list_scenes(bbox, after.isoformat()))
    except Exception as e:
        return jsonify(error=f"Could not check images: {e}"), 500


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    d = request.get_json(force=True)
    bbox, before, after, w_km, h_km, err = parse_request(d)
    if err:
        return jsonify(error=err), 400
    try:
        max_cloud = min(80.0, max(1.0, float(d.get("max_cloud", 20))))
    except (ValueError, TypeError):
        max_cloud = 20.0

    name = "run_" + uuid.uuid4().hex[:8]
    try:
        res = analyze(bbox, before.isoformat(), after.isoformat(), name, max_cloud=max_cloud)
    except RuntimeError as e:
        return jsonify(error=str(e)), 404
    except Exception as e:  # network or data problems
        return jsonify(error=f"Could not process this request: {e}"), 500

    res["image_urls"] = {k: f"results/{name}/{v}" for k, v in res["images"].items()}
    res["area_km"] = [round(w_km, 1), round(h_km, 1)]
    res["bbox"] = bbox
    return jsonify(res)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
