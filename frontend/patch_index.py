"""
Applies the cloud warning and input validation changes to frontend/index.html.

Usage (from the frontend folder):   python patch_index.py
A backup is saved as index.html.bak. Each change is checked, and nothing is
written unless every change matches exactly once.
"""
import shutil
import sys
from pathlib import Path

FILE = Path(sys.argv[1] if len(sys.argv) > 1 else "index.html")
src = FILE.read_text(encoding="utf-8")

CHANGES = []  # (name, old, new)


def change(name, old, new):
    CHANGES.append((name, old, new))


# 1. CSS for the warning box
change("css", r"""  a { color:var(--moss); font-weight:600; }
</style>""", r"""  .warnbox { margin:.7rem 0; padding:.7rem .9rem; border-radius:10px; background:#fff3d6; color:#7a5300; font-size:.9rem; line-height:1.6; }
  a { color:var(--moss); font-weight:600; }
</style>""")

# 2. Warning box above the Compare button
change("warnBox html", r"""      <div>
        <button id="go" class="btn primary" type="button">Compare images</button>""", r"""      <div id="warnBox" class="warnbox hidden" role="alert"></div>
      <div>
        <button id="go" class="btn primary" type="button">Compare images</button>""")

# 3. Warning box on the results page
change("resWarn html", r"""    <div id="alert" class="alertbox"></div>""", r"""    <div id="alert" class="alertbox"></div>
    <div id="resWarn" class="warnbox hidden" role="alert" style="margin-bottom:1rem"></div>""")

# 4. Helper functions
change("helpers", r"""const $ = id => document.getElementById(id);""", r"""const $ = id => document.getElementById(id);

const CLOUD_WARN = 20;   // warn when cloud cover is more than this %

function showWarn(id, list) {
  const el = $(id);
  if (!list || !list.length) { el.classList.add("hidden"); el.innerHTML = ""; return; }
  el.innerHTML = list.map(w => "\u26a0\ufe0f " + w).join("<br>");
  el.classList.remove("hidden");
}
function inputProblem() {
  if (!bounds) return "Please select an area on the map first (click the map or draw a rectangle).";
  if (!valid) return $("areaInfo").textContent;
  if (!$("before").value || !$("after").value) return "Please pick both a Before and an After date.";
  if ($("before").value === $("after").value) return "No change: both dates are the same. Please pick two different dates.";
  return null;
}
function cloudWarnings(label, list) {
  if (!list || !list.length) return [];
  const best = list.reduce((a, b) => b.cloud < a.cloud ? b : a);
  return best.cloud > CLOUD_WARN
    ? [`${label}: even the clearest image (${best.date}) is ${best.cloud}% cloudy. Try other dates.`] : [];
}""")

# 5. Compare button is no longer disabled when no area is chosen
change("updateGo", r"""function updateGo() { $("go").disabled = busy || !valid; }""",
       r"""function updateGo() { $("go").disabled = busy; }""")

# 6. Compare click handler checks
change("compare handler", r"""  if (!bounds) return say("Choose an area on the map first.", "error");
  busy = true; updateGo(); startProgress();""", r"""  const problem = inputProblem();
  if (problem) return say(problem, "error");
  showWarn("warnBox", []);
  busy = true; updateGo(); startProgress();""")

# 7. Check cloud cover button checks
change("cloud button checks", r"""  if (!bounds) return say("Choose an area on the map first.", "error");
  const box = $("clouds");""", r"""  const problem = inputProblem();
  if (problem) return say(problem, "error");
  say(""); showWarn("warnBox", []);
  const box = $("clouds");""")

# 8. Show warnings after the cloud check
change("cloud check warnings", r"""    if (!resp.ok) throw new Error(d.error || "Could not check images.");""",
       r"""    if (!resp.ok) throw new Error(d.error || "Could not check images.");
    showWarn("warnBox", [...cloudWarnings("Before", d.before), ...cloudWarnings("After", d.after), ...(d.warnings || [])]);""")

# 9. Clear warnings when dates change
change("clear on date change",
       r"""["before", "after"].forEach(id => $(id).addEventListener("change", () => $("clouds").innerHTML = ""));""",
       r"""["before", "after"].forEach(id => $(id).addEventListener("change", () => { $("clouds").innerHTML = ""; showWarn("warnBox", []); }));""")

# 10. Warnings on the results page
change("result warnings", r"""  renderInsight(d); $("pdfLink").href = d.pdf_url;""", r"""  renderInsight(d); $("pdfLink").href = d.pdf_url;
  const w = [];
  [["Before", d.before_scene], ["After", d.after_scene]].forEach(([l, s]) => {
    const c = s.local_cloud ?? s.cloud;
    if (c > CLOUD_WARN) w.push(`${l} image (${s.date}): ${c}% cloud over your area. Some detected change may be cloud, not land.`);
  });
  showWarn("resWarn", [...w, ...(d.warnings || [])]);""")

# ---- apply ----
if "const CLOUD_WARN" in src:
    sys.exit("This file already looks patched. Nothing changed.")

problems = [n for n, old, _ in CHANGES if src.count(old) != 1]
if problems:
    sys.exit("Could not patch. These spots did not match exactly once: " + ", ".join(problems)
             + "\nNothing was changed. Send me your current index.html.")

for _, old, new in CHANGES:
    src = src.replace(old, new, 1)

shutil.copy(FILE, str(FILE) + ".bak")
FILE.write_text(src, encoding="utf-8")
print(f"Done. Applied {len(CHANGES)} changes. Backup saved as {FILE}.bak")
