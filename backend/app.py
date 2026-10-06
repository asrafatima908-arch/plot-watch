"""
Plot Watch web server.
Run:  python app.py   then open the forwarded port 5000.
"""
import math
import uuid
from datetime import date

from flask import Flask, jsonify, request, send_from_directory

from fetch import analyze

app = Flask(__name__, static_folder="../frontend", static_url_path="")


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    d = request.get_json(force=True)
    try:
        lat, lon = float(d["lat"]), float(d["lon"])
        size_km = float(d.get("size_km", 2))
        before = date.fromisoformat(d["before_date"])
        after = date.fromisoformat(d["after_date"])
    except (KeyError, ValueError):
        return jsonify(error="Please fill in latitude, longitude and both dates."), 400

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify(error="Latitude or longitude is out of range."), 400
    if not (0.5 <= size_km <= 5):
        return jsonify(error="Area size must be between 0.5 and 5 km."), 400
    if before >= after:
        return jsonify(error="The 'before' date must be earlier than the 'after' date."), 400
    if after > date.today():
        return jsonify(error="The 'after' date cannot be in the future."), 400
    if before < date(2017, 1, 1):
        return jsonify(error="Sentinel-2 images are available from 2017 onward."), 400

    half = size_km / 2
    dlat = half / 111.0
    dlon = half / (111.0 * math.cos(math.radians(lat)))
    bbox = [lon - dlon, lat - dlat, lon + dlon, lat + dlat]
    name = "run_" + uuid.uuid4().hex[:8]

    try:
        res = analyze(bbox, before.isoformat(), after.isoformat(), name)
    except RuntimeError as e:
        return jsonify(error=str(e)), 404
    except Exception as e:  # network or data problems
        return jsonify(error=f"Could not process this request: {e}"), 500

    res["image_urls"] = {k: f"results/{name}/{v}" for k, v in res["images"].items()}
    return jsonify(res)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
