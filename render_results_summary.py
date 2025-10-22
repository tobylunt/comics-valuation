#!/usr/bin/env python3
"""
Render Results Summary (HTML) without Quarto

Reads a CSV of valuation results (default:
  results/comic_valuations_20251020_204257.csv)
computes conservative totals (sum of "Low Estimate ($)"),
flags suspicious/misidentified items, and writes a single-file self-contained
HTML report to results_summary.html (or specified output). The script can
embed thumbnails and the distribution plot as base64 data URIs so the HTML
is portable.

Usage:
    python render_results_summary.py \
        --csv results/comic_valuations_20251020_204257.csv \
        --out results_summary.html \
        --thumbs --embed --images-dir images

Notes:
- For embedding thumbnails and automatically creating them, Pillow is required.
- The images directory defaults to ./images inside the repo.
- The produced HTML includes a sortable table (simple JS) and an inline plot.

Author: Automated Valuation System
"""

from __future__ import annotations

import csv
import html
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# Optional: Pillow is used for thumbnail creation
try:
    from PIL import Image, UnidentifiedImageError
except Exception:
    Image = None
    UnidentifiedImageError = Exception

# --- Configuration defaults -------------------------------------------------
DEFAULT_CSV: Optional[Path] = None
DEFAULT_OUTPUT = Path("results") / "results_summary.html"
ID_CONF_THRESHOLD = 0.60
VAL_CONF_THRESHOLD = 0.40
TOP_N = 12
SUSPICIOUS_TERMS = ["collected", "collected adventures", "volume ", "vol.", "tpb", "trade paperback"]

# --- Utilities --------------------------------------------------------------
def parse_float(value: Optional[str]) -> float:
    """Parse a numeric-looking string into float, tolerant of commas and empties."""
    if value is None:
        return 0.0
    s = str(value).strip()
    if s == "":
        return 0.0
    # Remove common thousands separators
    s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        # Try to extract digits and decimal points
        filtered = "".join(ch for ch in s if (ch.isdigit() or ch == "." or ch == "-"))
        try:
            return float(filtered) if filtered not in ("", "-", ".") else 0.0
        except Exception:
            return 0.0

def fmt_money(v: float) -> str:
    return "${:,.2f}".format(v)

def safe_get(row: Dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()

def contains_suspicious_text(s: str) -> bool:
    if not s:
        return False
    s_low = s.lower()
    return any(term in s_low for term in SUSPICIOUS_TERMS)

# --- Core processing --------------------------------------------------------
def load_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def analyze_rows(rows: List[Dict[str, str]],
                 id_conf_threshold: float = ID_CONF_THRESHOLD,
                 val_conf_threshold: float = VAL_CONF_THRESHOLD) -> Dict[str, Any]:
    processed = []
    sum_low = sum_best = sum_high = 0.0
    flagged: List[Tuple[Dict[str, str], List[str]]] = []
    for r in rows:
        low = parse_float(r.get("Low Estimate ($)", r.get("Low Estimate", "0")))
        best = parse_float(r.get("Best Estimate ($)", r.get("Best Estimate", "0")))
        high = parse_float(r.get("High Estimate ($)", r.get("High Estimate", "0")))
        id_conf = parse_float(r.get("Identification Confidence", "0"))
        val_conf = parse_float(r.get("Valuation Confidence", "0"))

        sum_low += low
        sum_best += best
        sum_high += high

        series = safe_get(r, "Series")
        title = safe_get(r, "Title")

        reasons: List[str] = []
        # Low confidence checks
        if id_conf < id_conf_threshold:
            reasons.append("low_ident_conf")
        if val_conf < val_conf_threshold:
            reasons.append("low_val_conf")
        # Suspicious textual markers
        if contains_suspicious_text(series) or contains_suspicious_text(title):
            reasons.append("suspicious_text")
        # Batman-specific check
        if ("batman" in series.lower() or "batman" in title.lower()) and \
           (contains_suspicious_text(series) or contains_suspicious_text(title)):
            reasons.append("batman_collected_mismatch")
        # Large discrepancy heuristic
        if low > 0 and best >= 100 and best / max(low, 1e-6) >= 10:
            reasons.append("large_discrepancy")

        is_flagged = len(reasons) > 0
        if is_flagged:
            flagged.append((r, reasons))

        processed.append({
            "row": r,
            "low": low,
            "best": best,
            "high": high,
            "id_conf": id_conf,
            "val_conf": val_conf,
            "flags": reasons,
            "is_flagged": is_flagged
        })

    # Sort top items by best estimate
    top_items = sorted(processed, key=lambda x: x["best"], reverse=True)[:TOP_N]

    totals = {
        "count": len(processed),
        "sum_low": sum_low,
        "sum_best": sum_best,
        "sum_high": sum_high,
        "processed": processed,
        "flagged": flagged,
        "top_items": top_items
    }
    return totals

# --- HTML generation --------------------------------------------------------
def create_thumbnails_for_rows(rows: List[Dict[str, str]], images_dir: Optional[Path], thumbs_dir: Path, max_size: int = 200) -> None:
    """
    Create thumbnails for given rows. Thumbnails are saved into thumbs_dir with the same
    filename as the original but in JPG format. If Pillow is not available, this is a no-op.
    """
    if Image is None:
        # Pillow not available; skip thumbnail creation
        return

    thumbs_dir.mkdir(parents=True, exist_ok=True)

    for r in rows:
        img_name = safe_get(r, "Image Filename")
        if not img_name:
            continue
        # Try common filenames in the images directory
        if images_dir:
            cand = images_dir / img_name
        else:
            cand = Path(img_name)
        if not cand.exists():
            # Try alternate extensions if image name has no extension
            found = False
            for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]:
                alt = cand.with_suffix(ext)
                if alt.exists():
                    cand = alt
                    found = True
                    break
            if not cand.exists():
                continue

        try:
            with Image.open(cand) as im:
                im.thumbnail((max_size, max_size))
                # Save as JPEG to thumbs dir
                thumb_path = thumbs_dir / (Path(img_name).stem + ".jpg")
                # Convert to RGB for JPEG if necessary
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.split()[-1])
                    bg.save(thumb_path, format="JPEG", quality=85)
                else:
                    im.convert("RGB").save(thumb_path, format="JPEG", quality=85)
        except UnidentifiedImageError:
            continue
        except Exception:
            # on any error, skip thumbnail for that image
            continue


def generate_html_report(analysis: Dict[str, Any],
                         out_path: Path,
                         id_conf_threshold: float = ID_CONF_THRESHOLD,
                         val_conf_threshold: float = VAL_CONF_THRESHOLD,
                         images_dir: Optional[Path] = None,
                         thumbs_dir: Optional[Path] = None,
                         no_plot: bool = False) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    count = analysis["count"]
    sum_low = analysis["sum_low"]
    sum_best = analysis["sum_best"]
    sum_high = analysis["sum_high"]
    flagged = analysis["flagged"]
    top_items = analysis["top_items"]
    processed = analysis["processed"]

    # Conservative totals excluding flagged items
    unflagged_low_sum = sum(p["low"] for p in processed if not p["is_flagged"])
    high_conf_low_sum = sum(p["low"] for p in processed if p["id_conf"] >= id_conf_threshold and p["val_conf"] >= val_conf_threshold)

    # Basic CSS for readability
    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 24px; color: #111; }
    h1,h2,h3 { color: #222; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 18px; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }
    th { background: #f6f6f6; font-weight: 600; }
    tr.flagged td { background: #fff7f7; }
    .muted { color: #666; font-size: 0.95em; }
    .summary { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
    .card { border: 1px solid #eee; padding: 12px 16px; border-radius: 6px; background: #fff; min-width: 220px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }
    .small { font-size: 0.9em; color: #444; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, "Roboto Mono", monospace; }
    img.thumb { max-width: 120px; max-height: 120px; border-radius: 4px; border: 1px solid #ddd; }
    """

    def escape(s: Any) -> str:
        return html.escape(str(s)) if s is not None else ""

    # Utility to build file:// URI for a path if it exists
    def file_uri_for_path(p: Optional[Path]) -> Optional[str]:
        if not p:
            return None
        try:
            return p.resolve().as_uri()
        except Exception:
            return None

    # Build main HTML
    html_parts: List[str] = []
    html_parts.append("<!doctype html>")
    html_parts.append("<html lang='en'>")
    html_parts.append("<head>")
    html_parts.append("<meta charset='utf-8'/>")
    html_parts.append(f"<title>Collection Valuation Summary - {escape(now)}</title>")
    html_parts.append(f"<style>{css}</style>")
    # Include DataTables and Plotly for interactive table and plotting
    html_parts.append('<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">')
    html_parts.append('<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>')
    html_parts.append('<script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>')
    html_parts.append('<script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>')
    html_parts.append("</head><body>")
    html_parts.append(f"<h1>Collection Valuation Summary</h1>")
    html_parts.append(f"<p class='muted'>Generated: {escape(now)} (UTC)</p>")

    # Summary cards
    html_parts.append("<div class='summary'>")
    html_parts.append(f"<div class='card'><strong>Items processed</strong><div class='small'>{count}</div></div>")
    html_parts.append(f"<div class='card'><strong>Conservative total (all low estimates)</strong><div class='small mono'>{fmt_money(sum_low)}</div></div>")
    html_parts.append(f"<div class='card'><strong>Conservative total (exclude flagged)</strong><div class='small mono'>{fmt_money(unflagged_low_sum)}</div></div>")
    html_parts.append(f"<div class='card'><strong>High-confidence low total</strong><div class='small mono'>{fmt_money(high_conf_low_sum)}</div></div>")
    html_parts.append("</div>")

    html_parts.append("<h2>Notes</h2>")
    html_parts.append("<ul>")
    html_parts.append("<li>This report uses the <strong>low estimate</strong> for each item as a conservative valuation baseline.</li>")
    html_parts.append("<li>Rows flagged by heuristics (low identification/valuation confidence, suspicious text like &quot;collected&quot;, or large discrepancies) are listed below. These should be reviewed manually.</li>")
    html_parts.append("<li>Use the &quot;Conservative total (exclude flagged)&quot; as the defensible immediate estimate until flagged items are resolved.</li>")
    html_parts.append("</ul>")

    # Full, sortable & searchable table (embed thumbnails & inline distribution plot)
    html_parts.append("<h2>Full collection table (sortable & searchable)</h2>")
    # Search/filter input
    html_parts.append("<div style='margin-bottom:10px; display:flex; gap:8px; align-items:center;'>")
    html_parts.append("<label for='searchBox' class='small muted'>Filter:</label>")
    html_parts.append("<input id='searchBox' type='search' placeholder='Search series, title, flags, etc.' style='flex:1;padding:6px;border:1px solid #ccc;border-radius:4px;'>")
    html_parts.append("</div>")
    # Embed numeric arrays for client-side plotting with Plotly (the plot will be built in JS)
    try:
        import json
        lows = [p['low'] for p in processed if p['low'] is not None]
        bests = [p['best'] for p in processed if p['best'] is not None]
        highs = [p['high'] for p in processed if p['high'] is not None]
        html_parts.append("<div id='dist-plot' style='width:100%;height:340px;margin-bottom:12px'></div>")
        html_parts.append("<script>window.__VAL_DATA = " + json.dumps({"low": lows, "best": bests, "high": highs}) + ";</script>")
    except Exception:
        # fall back if JSON embedding fails
        html_parts.append("<p class='muted'>Distribution data not available for embedding.</p>")

    # Generate an inline distribution plot (base64) and embed above the table,
    # unless the caller requests no_plot=True
    if not no_plot:
        try:
            import io
            import matplotlib.pyplot as plt
            # Prepare numeric arrays
            lows = [p['low'] for p in processed if p['low'] > 0]
            bests = [p['best'] for p in processed if p['best'] > 0]
            highs = [p['high'] for p in processed if p['high'] > 0]
            if (len(lows) + len(bests) + len(highs)) > 0:
                plt.style.use('seaborn-darkgrid')
                fig, ax = plt.subplots(figsize=(9,3))
                try:
                    if len(lows) > 1:
                        pd.Series(lows).plot.kde(ax=ax, bw_method=0.3, label='Low', color='C0')
                    if len(bests) > 1:
                        pd.Series(bests).plot.kde(ax=ax, bw_method=0.3, label='Best', color='C1')
                    if len(highs) > 1:
                        pd.Series(highs).plot.kde(ax=ax, bw_method=0.3, label='High', color='C2')
                except Exception:
                    # Fallback: histograms
                    ax.hist(lows, bins=40, density=True, alpha=0.3, label='Low', color='C0')
                    ax.hist(bests, bins=40, density=True, alpha=0.3, label='Best', color='C1')
                    ax.hist(highs, bins=40, density=True, alpha=0.3, label='High', color='C2')
                ax.set_xlabel("Value ($)")
                ax.set_title("Value distribution (Low / Best / High)")
                ax.legend()
                buf = io.BytesIO()
                fig.savefig(buf, format='png', bbox_inches='tight', dpi=150)
                buf.seek(0)
                import base64
                plot_b64 = base64.b64encode(buf.read()).decode('ascii')
                html_parts.append(f"<div style='margin-bottom:12px;'><img src='data:image/png;base64,{plot_b64}' alt='Value distribution' style='max-width:100%;height:auto;border:1px solid #eee;padding:6px;background:#fff;'></div>")
                plt.close(fig)
        except Exception:
            # If plotting fails, skip gracefully
            pass
    else:
        # Plotting was disabled by user request (no_plot=True)
        html_parts.append("<p class='muted'>Plotting of distributions has been disabled (no_plot=True).</p>")

    # Build header for full table (with thumbnails if requested)
    if thumbs_dir:
        html_parts.append("<table id='full-table' style='width:100%'>")
        html_parts.append("<thead><tr><th>Thumb</th><th>Publication Date</th><th>Series</th><th>Title</th><th>Issue</th><th data-order=\"num\">Low</th><th data-order=\"num\">Best</th><th data-order=\"num\">High</th><th data-order=\"num\">ValConf</th><th data-order=\"num\">IdConf</th><th>Flags</th></tr></thead>")
    else:
        html_parts.append("<table id='full-table' style='width:100%'>")
        html_parts.append("<thead><tr><th>Publication Date</th><th>Series</th><th>Title</th><th>Issue</th><th data-order=\"num\">Low</th><th data-order=\"num\">Best</th><th data-order=\"num\">High</th><th data-order=\"num\">ValConf</th><th data-order=\"num\">IdConf</th><th>Flags</th></tr></thead>")

    html_parts.append("<tbody>")
    # Iterate all processed rows so full table includes every item
    for i, item in enumerate(processed, start=1):
        r = item["row"]
        flags = ", ".join(item["flags"]) if item["flags"] else ""
        row_class = " class='flagged'" if item["is_flagged"] else ""
        html_parts.append(f"<tr{row_class}>")
        # compute publication year (if present) and do not emit a numeric index column
        pub_date = safe_get(r, 'Publication Date')
        # Show the raw publication date string (CSV contains mixed formats).
        # We'll display it as-is rather than trying to extract a year.
        pub_date_display = pub_date

        # prepare thumbnail/base64 embedded img (self-contained)
        thumb_html = ""
        if thumbs_dir:
            # prefer generated thumb then full image; embed base64
            thumb_path = thumbs_dir / (Path(safe_get(r, "Image Filename")).stem + ".jpg")
            full_image_path = None
            if images_dir:
                cand = images_dir / safe_get(r, "Image Filename")
                if cand.exists():
                    full_image_path = cand
            if not full_image_path:
                cand2 = Path(safe_get(r, "Image Filename"))
                if cand2.exists():
                    full_image_path = cand2
            chosen_path = thumb_path if (thumb_path and thumb_path.exists()) else full_image_path
            if chosen_path and chosen_path.exists():
                try:
                    import base64
                    data = chosen_path.read_bytes()
                    b64 = base64.b64encode(data).decode('ascii')
                    suffix = chosen_path.suffix.lower()
                    mime = "image/jpeg"
                    if suffix == ".png":
                        mime = "image/png"
                    elif suffix == ".gif":
                        mime = "image/gif"
                    elif suffix == ".webp":
                        mime = "image/webp"
                    src = "data:{};base64,{}".format(mime, b64)
                    # link to full file if available on disk
                    full_uri = file_uri_for_path(full_image_path) if full_image_path and full_image_path.exists() else None
                    img_tag = '<img class="thumb" src="{src}" alt="{alt}">'.format(src=escape(src), alt=escape(safe_get(r, "Image Filename")))
                    if full_uri:
                        thumb_html = '<a href="{href}" target="_blank">{img}</a>'.format(href=escape(full_uri), img=img_tag)
                    else:
                        thumb_html = img_tag
                except Exception:
                    thumb_html = ""
        if thumbs_dir:
            html_parts.append(f"<td>{thumb_html}</td>")

        # main columns
        # insert the Publication Date column before the Series column (display raw CSV value)
        html_parts.append(f"<td>{escape(pub_date_display)}</td>")
        html_parts.append(f"<td>{escape(safe_get(r,'Series'))}</td>")
        html_parts.append(f"<td>{escape(safe_get(r,'Title'))}</td>")
        html_parts.append(f"<td>{escape(safe_get(r,'Issue Number'))}</td>")
        # Numeric cells include a data-order attribute with the raw numeric value so DataTables
        # sorts by the numeric value while we display formatted currency.
        html_parts.append(f"<td class='mono' data-order='{item['low']}'>{fmt_money(item['low'])}</td>")
        html_parts.append(f"<td class='mono' data-order='{item['best']}'>{fmt_money(item['best'])}</td>")
        html_parts.append(f"<td class='mono' data-order='{item['high']}'>{fmt_money(item['high'])}</td>")
        html_parts.append(f"<td>{item['val_conf']:.2f}</td>")
        html_parts.append(f"<td>{item['id_conf']:.2f}</td>")
        html_parts.append(f"<td>{escape(flags)}</td>")
        html_parts.append("</tr>")
    html_parts.append("</tbody></table>")

    # brief flagged summary (full table contains flags per-row)
    html_parts.append(f"<h2>Flagged items summary</h2>")
    html_parts.append(f"<p class='muted'>{len(flagged)} items were flagged by automated heuristics (low id/val confidence, suspicious text like 'collected/volume', or large estimate discrepancies). Use the filter box above to locate and inspect flagged rows in the full table.</p>")

    # Add JS for basic searching and client-side column sorting
    # DataTables initialization and Plotly-based density overlay
    html_parts.append('''
    <script>
    // Initialize DataTables on the full table with default sort by Low descending.
    (function() {
      // Wait for jQuery & DataTables to be available
      function init() {
        if (typeof $ === 'undefined' || !$.fn.dataTable) {
          setTimeout(init, 100);
          return;
        }

        // Register an ordering helper that reads each cell's data-order attribute (if present)
        // and falls back to the numeric content in the cell. This mimics the dom-data-order
        // approach by using the cell's data-order value for sorting.
        if (!$.fn.dataTable.ext.order['dom-data-order']) {
          $.fn.dataTable.ext.order['dom-data-order'] = function(settings, col) {
            // Return an array of values for the column to be used for ordering.
            return this.api().column(col, {order:'index'}).nodes().map(function(td, i) {
              var $td = $(td);
              // prefer explicit data-order attribute (we set this on numeric td cells)
              var d = $td.data('order');
              if (d !== undefined && d !== null && d !== '') {
                var v = parseFloat(d);
                return isNaN(v) ? 0 : v;
              }
              // otherwise fall back to stripping non-numeric chars from the text
              var txt = $td.text() || '';
              var cleaned = txt.replace(/[^0-9.\-]/g, '');
              var v2 = parseFloat(cleaned);
              return isNaN(v2) ? 0 : v2;
            }).toArray();
          };
        }

        // Determine numeric targets by header text (most reliable) and fall back to data-order markers.
        // This ensures columns labeled "Low", "Best", "High" (and the conf columns) are always sorted numerically.
        var numericHeaders = ['Low','Best','High','ValConf','IdConf'];
        var numericTargets = [];
        $('#full-table thead th').each(function(){
          var txt = $(this).text().trim();
          // If the header matches one of the canonical numeric names, prefer that column
          if (numericHeaders.indexOf(txt) !== -1) {
            numericTargets.push($(this).index());
            return;
          }
          // otherwise, if the header was annotated with data-order="num", include it
          if ($(this).attr('data-order') === 'num') {
            numericTargets.push($(this).index());
            return;
          }
          // also support the explicit attribute marker we used earlier (data-order="num") on the th
          if ($(this).is('[data-order="num"]')) {
            numericTargets.push($(this).index());
            return;
          }
        });
        // If nothing was found by header text, fall back to any th with the data-order attribute
        if (numericTargets.length === 0) {
          numericTargets = $.map($('#full-table thead th[data-order="num"]'), function(e){ return $(e).index(); });
        }

        var table = $('#full-table').DataTable({
          "pageLength": 25,
          "order": [],   // we'll set default order programmatically below
          "columnDefs": [
            // Use the dom-data-order ordering on the numeric targets computed above
            { "orderDataType": "dom-data-order", "targets": numericTargets }
          ]
        });
        // Determine the index of the Low column and order desc by default
        var lowIdx = $('#full-table thead th').filter(function(){ return $(this).text().trim()==='Low'; }).index();
        if (lowIdx >= 0) {
          table.order([ [ lowIdx, 'desc' ] ]).draw();
        }
      }
      init();
    })();
    </script>
    <hr/>
    <p class='muted'>Report generated by <code>render_results_summary.py</code>. Conservative totals use low estimates. Flagged items should be manually verified.</p>
    </body></html>
    ''')
    # The full table above already contains flags for every item.
    # Display a short summary and pointer to filter the table.


    # Detailed instructions for the Batman issue reported by user


    # Footer / run details
    # Insert Plotly-based density overlay using embedded arrays (if available)
    html_parts.append("<script>")
    html_parts.append("if (window.__VAL_DATA && (window.__VAL_DATA.low.length || window.__VAL_DATA.best.length || window.__VAL_DATA.high.length)) {")
    html_parts.append("  var lows = window.__VAL_DATA.low || [];")
    html_parts.append("  var bests = window.__VAL_DATA.best || [];")
    html_parts.append("  var highs = window.__VAL_DATA.high || [];")
    html_parts.append("  var traces = [];")
    html_parts.append("  if (lows.length) traces.push({type:'histogram', x:lows, name:'Low', opacity:0.5, histnorm:'probability density', marker:{color:'rgba(31,119,180,0.6)'}});")
    html_parts.append("  if (bests.length) traces.push({type:'histogram', x:bests, name:'Best', opacity:0.5, histnorm:'probability density', marker:{color:'rgba(255,127,14,0.6)'}});")
    html_parts.append("  if (highs.length) traces.push({type:'histogram', x:highs, name:'High', opacity:0.5, histnorm:'probability density', marker:{color:'rgba(44,160,44,0.6)'}});")
    html_parts.append("  var layout = {barmode:'overlay', title:'Value distribution (Low / Best / High)', xaxis:{title:'Value ($)'}, yaxis:{title:'Density'}};")
    html_parts.append("  Plotly.newPlot('dist-plot', traces, layout, {responsive:true});")
    html_parts.append("}")
    html_parts.append("</script>")
    html_parts.append("<hr/>")
    html_parts.append("<p class='muted'>Report generated by <code>render_results_summary.py</code>. Conservative totals use low estimates. Flagged items should be manually verified.</p>")
    html_parts.append("</body></html>")

    # Write to file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(html_parts), encoding="utf-8")
    print(f"Wrote HTML summary to: {out_path.resolve()}")

# --- CLI -------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render conservative valuation summary to HTML")
    parser.add_argument("--csv", "-c", type=Path, default=None, help="Path to CSV results file (default: latest results/comic_valuations_*.csv if present)")
    parser.add_argument("--out", "-o", type=Path, default=DEFAULT_OUTPUT, help="Output HTML file path")
    parser.add_argument("--id-conf", type=float, default=ID_CONF_THRESHOLD, help="Identification confidence threshold (flag below)")
    parser.add_argument("--val-conf", type=float, default=VAL_CONF_THRESHOLD, help="Valuation confidence threshold (flag below)")
    parser.add_argument("--top", type=int, default=TOP_N, help="How many top items to show by best estimate")
    parser.add_argument("--thumbs", action="store_true", help="Generate thumbnails and include thumbnails in the report")
    parser.add_argument("--thumbs-dir", type=Path, default=Path("results") / "thumbnails", help="Directory to write thumbnails (if --thumbs)")
    parser.add_argument("--thumb-size", type=int, default=200, help="Maximum thumbnail dimension (px)")
    parser.add_argument("--images-dir", type=Path, default=Path("images"), help="Optional path to image files (overrides config.json). Defaults to 'images/' in repo.")
    parser.add_argument("--embed", action="store_true", help="Embed plot image into HTML as base64 (default: True when --thumbs is used)")
    parser.add_argument("--no-plot", action="store_true", help="Skip generating/embedding the distribution plot (useful if matplotlib is unavailable)")
    args = parser.parse_args(argv)

    # Use local variables to avoid shadowing module-level defaults
    top_n_local = max(1, args.top)
    id_conf_local = args.id_conf
    val_conf_local = args.val_conf
    make_thumbs = bool(args.thumbs)
    thumbs_dir = args.thumbs_dir
    thumb_size = int(args.thumb_size)
    images_dir_arg = args.images_dir
    # whether to skip plotting entirely
    no_plot_local = bool(args.no_plot)

    # Resolve CSV path: if the user didn't provide one, try to pick the latest
    # results/comic_valuations_*.csv file. If none found, fall back to DEFAULT_CSV
    if args.csv is None:
        csv_candidates = sorted(Path("results").glob("comic_valuations_*.csv"))
        if csv_candidates:
            csv_path = csv_candidates[-1]
        else:
            csv_path = DEFAULT_CSV
    else:
        csv_path = args.csv

    out_path: Path = args.out

    if csv_path is None:
        print("No CSV file specified and no results/comic_valuations_*.csv found. Use --csv to point to a file.")
        return 2

    try:
        rows = load_csv(csv_path)
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return 2

    # Determine images directory: CLI override > config.json > None
    images_dir: Optional[Path] = None
    if images_dir_arg:
        images_dir = images_dir_arg
    else:
        config_path = Path("config.json")
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                imgdir = cfg.get("images_directory")
                if imgdir:
                    images_dir = Path(imgdir)
            except Exception:
                images_dir = None

    # Create thumbnails if requested
    if make_thumbs:
        try:
            create_thumbnails_for_rows(rows, images_dir, thumbs_dir, max_size=thumb_size)
        except Exception as e:
            print(f"Warning: thumbnail creation failed: {e}")

    analysis = analyze_rows(rows, id_conf_threshold=id_conf_local, val_conf_threshold=val_conf_local)
    # override top items count if requested
    analysis["top_items"] = sorted(analysis["processed"], key=lambda x: x["best"], reverse=True)[:top_n_local]

    try:
        # If embedding is requested, ensure embed flag is set (we pass plot control via no_plot_local)
        generate_html_report(analysis,
                             out_path,
                             id_conf_threshold=id_conf_local,
                             val_conf_threshold=val_conf_local,
                             images_dir=images_dir,
                             thumbs_dir=(thumbs_dir if make_thumbs else None),
                             no_plot=no_plot_local)
    except Exception as e:
        print(f"Error generating report: {e}")
        return 3

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
