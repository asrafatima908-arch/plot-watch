# Plot Watch

**See how land changes, from space.**

Plot Watch compares satellite images of the same place from two dates and shows what changed, such as new construction or cleared land. Pick any location on a map, choose two dates, and get a before/after view, a severity score, and a PDF report.

**Live demo:** https://plot-watch.onrender.com
*(Hosted on a free plan, so the first load after a quiet period can take about a minute.)*

## Why this project

Land encroachment and unauthorised construction cause costly disputes in India, especially for owners who live far from their land and depend on someone else to check it. Satellite data is free but usually needs GIS expertise. Plot Watch turns it into a simple tool: choose a place and two dates, and get an answer.

## Features

- **Map interface:** search a city or landmark, click to place a square, or draw your own area.
- **Two satellite sources:** Sentinel-2 (10 m, 2017 onward) and Landsat (30 m, 1985 onward). *Auto* mode picks Landsat for dates before 2017. Both dates in a comparison always use the same satellite.
- **Cloud check:** lists available images near each date with their cloud cover, sets a maximum cloud limit, and measures cloud over your own area.
- **Six change types:** new construction, road/paving on bare land, vegetation cleared, new water, water shrinkage, vegetation regrowth.
- **Severity score (0-100)** with a plain-language explanation and a recommended action.
- **Four result views:** before/after slider, side by side, change map, and changes drawn on a high-resolution map.
- **Saved analyses:** every run is saved with its PDF report and a downloadable data file.

## How it works

1. The user selects an area and two dates in the browser.
2. The Flask server searches Microsoft Planetary Computer for the clearest image within a window around each date.
3. Only the selected area is downloaded (five bands: blue, green, red, near-infrared, shortwave-infrared).
4. Vegetation (NDVI), built-up (NDBI) and water (NDWI) indices are computed for both dates.
5. Pixels are flagged and classified using fixed thresholds, and small specks are removed.
6. A weighted severity score is calculated from area changed, absolute area, change-type risk, confidence, and persistence (held neutral until history exists).
7. Images, a PDF report, and a JSON result file are saved and shown in the browser.

## Tech stack

- **Backend:** Python, Flask, rasterio, NumPy, SciPy, Matplotlib, pystac-client, ReportLab
- **Frontend:** HTML, CSS, JavaScript, Leaflet
- **Data:** Sentinel-2 L2A and Landsat Collection 2 Level-2 via Microsoft Planetary Computer
- **Hosting:** Render (gunicorn)

## Project structure

```
plot-watch/
  backend/
    app.py            web server and API (analysis, cloud check, saved history)
    fetch.py          satellite search and download (Sentinel-2 and Landsat)
    detect.py         change detection, change types, severity score
    report.py         PDF report
    requirements.txt
  frontend/
    index.html        the website
  render.yaml         deployment settings for Render
```

## Run it yourself

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000` (in GitHub Codespaces, open the forwarded port 5000).

Results are written to `frontend/results/` and temporary downloads to `backend/data/`. Both are ignored by git.

## Limitations

- Detection is **rule-based with fixed thresholds**, not a trained neural network.
- Sentinel-2 has 10 m pixels and Landsat 30 m, so small structures and fine detail cannot be seen.
- Clouds, crop cycles, soil moisture, and seasonal differences can appear as change. Compare images from the same time of year.
- Cloud pixels are measured and reduce the confidence score, but they are not removed from the detection.
- Older Landsat coverage over some regions can be patchy.
- Accuracy has not yet been measured across a set of known sites.
- Results are a screening aid. They do not check permits, land records, or zoning. Verify important findings on the ground.
- There are no user accounts, and saved results on the free host are cleared when it restarts.

## Roadmap

- Accuracy testing on sites with known changes
- Time-series charts to show when a change started
- Cloud and shadow masking in the detection
- Upload a plot boundary (GeoJSON/KML) instead of a rectangle
- User accounts, saved plots, and automatic alerts
- A trained change-detection model compared against the rule-based version

## Credits and data sources

- Builds on our Smart India Hackathon project, **Satellite Change Detection System**, developed as a team.
- Contains modified Copernicus Sentinel data (European Space Agency / European Commission).
- Landsat imagery courtesy of the U.S. Geological Survey and NASA.
- Data access through Microsoft Planetary Computer.
- Map imagery by Esri; street maps and place search by OpenStreetMap contributors; maps powered by Leaflet.

## Author

Asra Fatima