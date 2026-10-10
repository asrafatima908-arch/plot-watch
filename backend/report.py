"""Plot Watch - PDF report for one analysis run."""
from datetime import datetime
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _img(path, width):
    w, h = PILImage.open(path).size
    return Image(str(path), width=width, height=width * h / w)


def make_report(res, folder, bbox):
    folder = Path(folder)
    st = getSampleStyleSheet()
    sv, b, a = res["severity"], res["before_scene"], res["after_scene"]
    sensor = "Landsat (30 m)" if res["source"] == "landsat" else "Sentinel-2 (10 m)"
    lat, lon = (bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2

    story = [
        Paragraph("Satellite Change Analysis Report", st["Title"]),
        Paragraph(f"Centre: {lat:.4f}, {lon:.4f} | Area: {res['area_km2']} km2 | "
                  f"Images: {b['date']} and {a['date']} | Source: {sensor} | "
                  f"Generated: {datetime.now():%Y-%m-%d %H:%M}", st["Normal"]),
        Spacer(1, 0.4 * cm),
    ]
    imgs = [_img(folder / f, 5.6 * cm) for f in ("before.png", "after.png", "change.png")]
    caps = [Paragraph(c, st["Italic"]) for c in (f"Before ({b['date']})", f"After ({a['date']})", "Detected change")]
    story += [Table([imgs, caps], colWidths=[5.8 * cm] * 3), Spacer(1, 0.4 * cm)]

    story += [Paragraph("Alert", st["Heading2"]), Paragraph(res["alert"], st["Normal"]),
              Paragraph("Severity", st["Heading2"]),
              Paragraph(f"Score: {sv['score']}/100 ({sv['level']}) | Confidence: {sv['confidence']}%", st["Normal"]),
              Paragraph(sv["explanation"], st["Normal"]),
              Paragraph(f"<b>Recommended action:</b> {sv['action']}", st["Normal"]),
              Paragraph("Change by type", st["Heading2"])]
    rows = [["Type", "Share of area"]] + [[r["label"], f"{r['percent']}%"] for r in res["breakdown"]]
    t = Table(rows, colWidths=[11 * cm, 4 * cm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6efe9"))]))
    story += [t, Paragraph("Method and limitations", st["Heading2"]),
              Paragraph(
                  f"Imagery from {sensor} surface-reflectance archives, cropped to the chosen area. Vegetation, "
                  "built-up and water indices are compared between two dates and classified with fixed thresholds "
                  "(a rule-based method, not a trained neural network). Clouds, crop cycles, soil moisture and "
                  "seasonal differences can appear as change. The score is a screening aid: it does not check "
                  "permits, land records or zoning. Verify important findings on the ground.", st["Normal"]),
              Paragraph(
                  "Why this satellite: Landsat (30 m) is used for dates before 2017 because Sentinel-2's dependable "
                  "archive starts around then, and its 30 m pixels can miss small changes."
                  if res["source"] == "landsat" else
                  "Why this satellite: Sentinel-2 (10 m) is used for 2017 onward because its sharper pixels show "
                  "smaller changes than Landsat.", st["Normal"])]
    SimpleDocTemplate(str(folder / "report.pdf"), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                      topMargin=2 * cm, bottomMargin=2 * cm).build(story)
