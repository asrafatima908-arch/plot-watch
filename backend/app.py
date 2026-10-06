"""
Plot Watch web server.
Run:  python app.py   then open the forwarded port 5000.
"""
import math
import uuid
from datetime import date

from flask import Flask, jsonify, request, send_from_directory

from fetch import analyze

MAX_KM, MIN_KM = 6.0, 0.3  # allowed side length of the selected area

app = Flask(__name__, static_folder="../frontend", static_url_path="")


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    d = request.get_json(force=True)
    try:
        west, south, east, north = [float(x) for x in d["bbox"]]
        before = date.fromisoformat(d["before_date"])
        after = date.fromisoformat(d["after_date"])
    except (KeyError, ValueError, TypeError):
        return jsonify(error="Please choose an area on the map and both dates."), 400

    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        return jsonify(error="The selected area is not valid."), 400
    lat = (south + north) / 2
    w_km = (east - west) * 111.32 * math.cos(math.radians(lat))
    h_km = (north - south) * 110.57
    if max(w_km, h_km) > MAX_KM:
        return jsonify(error=f"Area too large. Keep each side under {MAX_KM:g} km."), 400
    if min(w_km, h_km) < MIN_KM:
        return jsonify(error=f"Area too small. Keep each side at least {MIN_KM:g} km."), 400
    if before >= after:
        return jsonify(error="The 'before' date must be earlier than the 'after' date."), 400
    if after > date.today():
        return jsonify(error="The 'after' date cannot be in the future."), 400
    if before < date(2017, 1, 1):
        return jsonify(error="Sentinel-2 images are available from 2017 onward."), 400

    name = "run_" + uuid.uuid4().hex[:8]
    try:
        res = analyze([west, south, east, north], before.isoformat(), after.isoformat(), name)
    except RuntimeError as e:
        return jsonify(error=str(e)), 404
    except Exception as e:  # network or data problems
        return jsonify(error=f"Could not process this request: {e}"), 500

    res["image_urls"] = {k: f"results/{name}/{v}" for k, v in res["images"].items()}
    res["area_km"] = [round(w_km, 1), round(h_km, 1)]
    return jsonify(res)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
