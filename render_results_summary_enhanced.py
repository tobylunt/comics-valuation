#!/usr/bin/env python3
"""
Enhanced HTML report generator for comic book valuations with modals for detailed information.
Adds estimated grade column and modals for condition/analysis notes and grounding sources.
"""

import json
import html
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import pandas as pd

# Default confidence thresholds
ID_CONF_THRESHOLD = 0.80
VAL_CONF_THRESHOLD = 0.60

def parse_float(value: Any) -> Optional[float]:
    """Parse a value as float, returning None if invalid."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            # Remove currency symbols and commas
            cleaned = value.replace('$', '').replace(',', '').strip()
            if cleaned == "":
                return None
            return float(cleaned)
        return float(value)
    except (ValueError, TypeError):
        return None

def fmt_money(value: Optional[float]) -> str:
    """Format a float as currency."""
    return f"${value:.2f}" if value is not None else "$0.00"

def safe_get(row: Dict[str, Any], key: str) -> str:
    """Safely get a value from a row, returning empty string if missing."""
    return str(row.get(key, "")) if row.get(key) is not None else ""

def contains_suspicious_text(text: str) -> bool:
    """Check if text contains suspicious keywords that might indicate incorrect identification."""
    if not text:
        return False
    suspicious = ["collected", "volume", "collection", "omnibus", "hardcover"]
    return any(word in text.lower() for word in suspicious)

def load_json_data(json_path: Path) -> Dict[str, Any]:
    """Load the JSON data file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_json_data(data: Dict[str, Any],
                     id_conf_threshold: float = ID_CONF_THRESHOLD,
                     val_conf_threshold: float = VAL_CONF_THRESHOLD) -> Dict[str, Any]:
    """Analyze the JSON data and prepare it for HTML rendering."""

    processed = []
    flagged = []

    for result in data.get('results', []):
        if not result.get('success', False):
            continue

        valuation = result.get('valuation', {})
        if not valuation:
            continue

        # Extract basic info
        series = valuation.get('series', '')
        title = valuation.get('title', '')
        issue = valuation.get('issue_number', '')
        pub_date = valuation.get('publication_date', '')
        estimated_grade = valuation.get('estimated_grade', '')

        # Extract valuation data
        val_data = valuation.get('valuation', {})
        low = parse_float(val_data.get('low_estimate', 0))
        best = parse_float(val_data.get('best_estimate', 0))
        high = parse_float(val_data.get('high_estimate', 0))
        val_conf = parse_float(val_data.get('confidence', 0))
        id_conf = parse_float(valuation.get('identification_confidence', 0))

        # Extract detailed info for modals
        condition_notes = valuation.get('condition_notes', [])
        analysis_notes = valuation.get('analysis_notes', '')
        grounding_sources = valuation.get('grounding_metadata', {}).get('sources', [])
        grounding_queries = valuation.get('grounding_metadata', {}).get('search_queries', [])

        # Determine flags
        flags = []
        if id_conf and id_conf < id_conf_threshold:
            flags.append("low_id_confidence")
        if val_conf and val_conf < val_conf_threshold:
            flags.append("low_val_confidence")
        if contains_suspicious_text(title):
            flags.append("suspicious_text")
        if low and high and (high / low) > 3:
            flags.append("large_discrepancy")
        if "batman" in series.lower() and "collected" in title.lower():
            flags.append("batman_collected_mismatch")

        is_flagged = len(flags) > 0

        item = {
            'filename': result.get('image_filename', ''),
            'series': series,
            'title': title,
            'issue': issue,
            'pub_date': pub_date,
            'estimated_grade': estimated_grade,
            'low': low or 0,
            'best': best or 0,
            'high': high or 0,
            'val_conf': val_conf or 0,
            'id_conf': id_conf or 0,
            'flags': flags,
            'is_flagged': is_flagged,
            'condition_notes': condition_notes,
            'analysis_notes': analysis_notes,
            'grounding_sources': grounding_sources,
            'grounding_queries': grounding_queries
        }

        processed.append(item)
        if is_flagged:
            flagged.append(item)

    # Calculate totals
    count = len(processed)
    sum_low = sum(item['low'] for item in processed)
    sum_best = sum(item['best'] for item in processed)
    sum_high = sum(item['high'] for item in processed)

    return {
        'count': count,
        'sum_low': sum_low,
        'sum_best': sum_best,
        'sum_high': sum_high,
        'processed': processed,
        'flagged': flagged
    }

def create_thumbnails_for_items(items: List[Dict[str, Any]],
                               images_dir: Path,
                               thumbs_dir: Path) -> None:
    """Create thumbnails for the items (simplified version)."""
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    # This would create actual thumbnails - simplified for this example
    pass

def generate_enhanced_html_report(analysis: Dict[str, Any],
                                out_path: Path,
                                json_data: Dict[str, Any],
                                id_conf_threshold: float = ID_CONF_THRESHOLD,
                                val_conf_threshold: float = VAL_CONF_THRESHOLD,
                                images_dir: Optional[Path] = None,
                                thumbs_dir: Optional[Path] = None,
                                no_plot: bool = False) -> None:
    """Generate enhanced HTML report with modals."""

    now = datetime.utcnow().isoformat() + "Z"
    count = analysis["count"]
    sum_low = analysis["sum_low"]
    sum_best = analysis["sum_best"]
    sum_high = analysis["sum_high"]
    flagged = analysis["flagged"]
    processed = analysis["processed"]

    # Conservative totals excluding flagged items
    unflagged_low_sum = sum(p["low"] for p in processed if not p["is_flagged"])
    high_conf_low_sum = sum(p["low"] for p in processed if p["id_conf"] >= id_conf_threshold and p["val_conf"] >= val_conf_threshold)

    def escape(s: Any) -> str:
        return html.escape(str(s)) if s is not None else ""

    def file_uri_for_path(p: Optional[Path]) -> Optional[str]:
        if not p:
            return None
        try:
            return p.resolve().as_uri()
        except Exception:
            return None

    # Enhanced CSS with modal styles
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

    /* Modal styles */
    .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.5); }
    .modal-content { background-color: #fefefe; margin: 5% auto; padding: 20px; border: 1px solid #888; border-radius: 8px; width: 80%; max-width: 800px; max-height: 80vh; overflow-y: auto; }
    .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
    .close:hover, .close:focus { color: black; text-decoration: none; }
    .clickable { color: #0066cc; cursor: pointer; text-decoration: underline; }
    .clickable:hover { color: #0052a3; }
    .condition-note { background: #f8f9fa; border-left: 4px solid #007bff; padding: 8px 12px; margin: 8px 0; border-radius: 4px; }
    .source-item { background: #f8f9fa; border: 1px solid #dee2e6; padding: 10px; margin: 8px 0; border-radius: 4px; }
    .source-item a { color: #0066cc; text-decoration: none; }
    .source-item a:hover { text-decoration: underline; }
    .query-list { background: #fff; border: 1px solid #dee2e6; padding: 10px; margin: 8px 0; border-radius: 4px; max-height: 200px; overflow-y: auto; }
    .query-list ul { margin: 0; padding-left: 20px; }
    .query-list li { margin: 4px 0; font-size: 0.9em; }
    """

    # Build main HTML
    html_parts: List[str] = []
    html_parts.append("<!doctype html>")
    html_parts.append("<html lang='en'>")
    html_parts.append("<head>")
    html_parts.append("<meta charset='utf-8'/>")
    html_parts.append(f"<title>Enhanced Collection Valuation Summary - {escape(now)}</title>")
    html_parts.append(f"<style>{css}</style>")
    # Include dependencies
    html_parts.append('<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">')
    html_parts.append('<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>')
    html_parts.append('<script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>')
    html_parts.append('<script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>')
    html_parts.append("</head><body>")

    html_parts.append(f"<h1>Enhanced Collection Valuation Summary</h1>")
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
    html_parts.append("<li>Click on <strong>Series</strong> names to view detailed condition and analysis notes.</li>")
    html_parts.append("<li>Click on <strong>Best</strong> valuations to view grounding sources and search queries.</li>")
    html_parts.append("<li>Rows flagged by heuristics are highlighted and should be reviewed manually.</li>")
    html_parts.append("</ul>")

    # Enhanced table with new columns and modals
    html_parts.append("<h2>Full collection table (sortable & searchable)</h2>")
    html_parts.append("<div style='margin-bottom:10px; display:flex; gap:8px; align-items:center;'>")
    html_parts.append("<label for='searchBox' class='small muted'>Filter:</label>")
    html_parts.append("<input id='searchBox' type='search' placeholder='Search series, title, flags, etc.' style='flex:1;padding:6px;border:1px solid #ccc;border-radius:4px;'>")
    html_parts.append("</div>")

    # Embed numeric arrays for client-side plotting
    try:
        lows = [p['low'] for p in processed if p['low'] is not None]
        bests = [p['best'] for p in processed if p['best'] is not None]
        highs = [p['high'] for p in processed if p['high'] is not None]
        html_parts.append("<div id='dist-plot' style='width:100%;height:340px;margin-bottom:12px'></div>")
        html_parts.append("<script>window.__VAL_DATA = " + json.dumps({"low": lows, "best": bests, "high": highs}) + ";</script>")
    except Exception:
        html_parts.append("<p class='muted'>Distribution data not available for embedding.</p>")

    if not no_plot:
        html_parts.append("<p class='muted'>Interactive distribution chart will load above the table.</p>")
    else:
        html_parts.append("<p class='muted'>Plotting of distributions has been disabled (no_plot=True).</p>")

    # Enhanced table header with Grade column
    if thumbs_dir:
        html_parts.append("<table id='full-table' style='width:100%'>")
        html_parts.append("<thead><tr><th>Thumb</th><th>Publication Date</th><th>Series</th><th>Title</th><th>Issue</th><th>Grade</th><th data-order=\"num\">Low</th><th data-order=\"num\">Best</th><th data-order=\"num\">High</th><th data-order=\"num\">ValConf</th><th data-order=\"num\">IdConf</th><th>Flags</th></tr></thead>")
    else:
        html_parts.append("<table id='full-table' style='width:100%'>")
        html_parts.append("<thead><tr><th>Publication Date</th><th>Series</th><th>Title</th><th>Issue</th><th>Grade</th><th data-order=\"num\">Low</th><th data-order=\"num\">Best</th><th data-order=\"num\">High</th><th data-order=\"num\">ValConf</th><th data-order=\"num\">IdConf</th><th>Flags</th></tr></thead>")

    html_parts.append("<tbody>")

    # Generate table rows with modal triggers
    for i, item in enumerate(processed):
        flags = ", ".join(item["flags"]) if item["flags"] else ""
        row_class = " class='flagged'" if item["is_flagged"] else ""
        html_parts.append(f"<tr{row_class}>")

        # Thumbnail column (if enabled)
        if thumbs_dir:
            thumb_html = ""
            if images_dir:
                img_path = images_dir / item['filename']
                if img_path.exists():
                    try:
                        # Check if thumbnail exists first, prefer it over full image
                        thumb_path = thumbs_dir / item['filename'] if thumbs_dir else None
                        if thumb_path and thumb_path.exists():
                            # Use thumbnail with file URI
                            thumb_uri = file_uri_for_path(thumb_path)
                            if thumb_uri:
                                src = thumb_uri
                            else:
                                # Fallback to relative path
                                src = f"../results/thumbnails/{item['filename']}"
                        else:
                            # Use full image with file URI (but don't embed as base64)
                            full_uri = file_uri_for_path(img_path)
                            if full_uri:
                                src = full_uri
                            else:
                                # Fallback to relative path
                                src = f"../images/{item['filename']}"

                        img_tag = f'<img class="thumb" src="{escape(src)}" alt="{escape(item["filename"])}">'

                        # Always link to full image for viewing
                        full_uri = file_uri_for_path(img_path)
                        if full_uri:
                            thumb_html = f'<a href="{escape(full_uri)}" target="_blank">{img_tag}</a>'
                        else:
                            thumb_html = img_tag
                    except Exception:
                        thumb_html = ""
            html_parts.append(f"<td>{thumb_html}</td>")

        # Main columns
        html_parts.append(f"<td>{escape(item['pub_date'])}</td>")

        # Series column with modal trigger for details
        series_modal_id = f"details-modal-{i}"
        html_parts.append(f"<td><span class='clickable' onclick='showDetailsModal(\"{series_modal_id}\")'>{escape(item['series'])}</span></td>")

        html_parts.append(f"<td>{escape(item['title'])}</td>")
        html_parts.append(f"<td>{escape(item['issue'])}</td>")
        html_parts.append(f"<td>{escape(item['estimated_grade'])}</td>")
        html_parts.append(f"<td class='mono' data-order='{item['low']}'>{fmt_money(item['low'])}</td>")

        # Best column with modal trigger for grounding sources
        best_modal_id = f"sources-modal-{i}"
        html_parts.append(f"<td class='mono' data-order='{item['best']}'><span class='clickable' onclick='showSourcesModal(\"{best_modal_id}\")'>{fmt_money(item['best'])}</span></td>")

        html_parts.append(f"<td class='mono' data-order='{item['high']}'>{fmt_money(item['high'])}</td>")
        html_parts.append(f"<td>{item['val_conf']:.2f}</td>")
        html_parts.append(f"<td>{item['id_conf']:.2f}</td>")
        html_parts.append(f"<td>{escape(flags)}</td>")
        html_parts.append("</tr>")

    html_parts.append("</tbody></table>")

    # Generate modals for each item
    html_parts.append("<!-- Modals for detailed information -->")
    for i, item in enumerate(processed):
        # Details modal (condition notes + analysis notes)
        details_modal_id = f"details-modal-{i}"
        html_parts.append(f'<div id="{details_modal_id}" class="modal" onclick="closeModal(\'{details_modal_id}\')">')
        html_parts.append('<div class="modal-content" onclick="event.stopPropagation();">')
        html_parts.append(f'<span class="close" onclick="closeModal(\'{details_modal_id}\')">&times;</span>')
        html_parts.append(f'<h3>{escape(item["series"])} #{escape(item["issue"])}</h3>')
        html_parts.append(f'<h4>Title: {escape(item["title"])}</h4>')
        html_parts.append(f'<p><strong>Publication Date:</strong> {escape(item["pub_date"])}</p>')
        html_parts.append(f'<p><strong>Estimated Grade:</strong> {escape(item["estimated_grade"])}</p>')

        html_parts.append('<h4>Condition Notes:</h4>')
        if item['condition_notes']:
            for note in item['condition_notes']:
                html_parts.append(f'<div class="condition-note">{escape(note)}</div>')
        else:
            html_parts.append('<p class="muted">No specific condition notes available.</p>')

        html_parts.append('<h4>Analysis Notes:</h4>')
        if item['analysis_notes']:
            # Remove market data section from analysis notes
            analysis_text = item['analysis_notes']
            if ' | Market data:' in analysis_text:
                analysis_text = analysis_text.split(' | Market data:')[0].strip()
            html_parts.append(f'<p style="white-space: pre-wrap; background: #f8f9fa; padding: 12px; border-radius: 4px;">{escape(analysis_text)}</p>')
        else:
            html_parts.append('<p class="muted">No analysis notes available.</p>')

        html_parts.append('</div>')
        html_parts.append('</div>')

        # Sources modal (grounding sources + search queries)
        sources_modal_id = f"sources-modal-{i}"
        html_parts.append(f'<div id="{sources_modal_id}" class="modal" onclick="closeModal(\'{sources_modal_id}\')">')
        html_parts.append('<div class="modal-content" onclick="event.stopPropagation();">')
        html_parts.append(f'<span class="close" onclick="closeModal(\'{sources_modal_id}\')">&times;</span>')
        html_parts.append(f'<h3>Valuation Sources for {escape(item["series"])} #{escape(item["issue"])}</h3>')
        html_parts.append(f'<p><strong>Best Estimate:</strong> {fmt_money(item["best"])}</p>')

        html_parts.append('<h4>Grounding Sources:</h4>')
        if item['grounding_sources']:
            for source in item['grounding_sources']:
                title = source.get('title', 'Unknown Source')
                url = source.get('url', '')
                html_parts.append('<div class="source-item">')
                if url:
                    html_parts.append(f'<a href="{escape(url)}" target="_blank">{escape(title)}</a>')
                else:
                    html_parts.append(f'<strong>{escape(title)}</strong>')
                html_parts.append('</div>')
        else:
            html_parts.append('<p class="muted">No grounding sources available.</p>')

        html_parts.append('<h4>Search Queries Used:</h4>')
        if item['grounding_queries']:
            html_parts.append('<div class="query-list">')
            html_parts.append('<ul>')
            for query in item['grounding_queries']:
                html_parts.append(f'<li>{escape(query)}</li>')
            html_parts.append('</ul>')
            html_parts.append('</div>')
        else:
            html_parts.append('<p class="muted">No search queries available.</p>')

        html_parts.append('</div>')
        html_parts.append('</div>')

    # Flagged items summary
    html_parts.append(f"<h2>Flagged items summary</h2>")
    html_parts.append(f"<p class='muted'>{len(flagged)} items were flagged by automated heuristics. Use the filter box above to locate flagged rows.</p>")

    # JavaScript for DataTables, Plotly, and modals
    html_parts.append('''
    <script>
    // Modal functionality
    function showDetailsModal(modalId) {
        document.getElementById(modalId).style.display = 'block';
    }

    function showSourcesModal(modalId) {
        document.getElementById(modalId).style.display = 'block';
    }

    function closeModal(modalId) {
        document.getElementById(modalId).style.display = 'none';
    }

    // Modal click-outside handling is done via inline onclick handlers on modal divs

    // Initialize DataTables
    (function() {
        function init() {
            if (typeof $ === 'undefined' || !$.fn.dataTable) {
                setTimeout(init, 100);
                return;
            }

            if (!$.fn.dataTable.ext.order['dom-data-order']) {
                $.fn.dataTable.ext.order['dom-data-order'] = function(settings, col) {
                    return this.api().column(col, {order:'index'}).nodes().map(function(td, i) {
                        var $td = $(td);
                        var d = $td.data('order');
                        if (d !== undefined && d !== null && d !== '') {
                            var v = parseFloat(d);
                            return isNaN(v) ? 0 : v;
                        }
                        var txt = $td.text() || '';
                        var cleaned = txt.replace(/[^0-9.\-]/g, '');
                        var v2 = parseFloat(cleaned);
                        return isNaN(v2) ? 0 : v2;
                    }).toArray();
                };
            }

            var numericHeaders = ['Low','Best','High','ValConf','IdConf'];
            var numericTargets = [];
            $('#full-table thead th').each(function(){
                var txt = $(this).text().trim();
                if (numericHeaders.indexOf(txt) !== -1) {
                    numericTargets.push($(this).index());
                }
            });

            var table = $('#full-table').DataTable({
                "pageLength": 25,
                "order": [],
                "columnDefs": [
                    { "orderDataType": "dom-data-order", "targets": numericTargets }
                ]
            });

            var lowIdx = $('#full-table thead th').filter(function(){ return $(this).text().trim()==='Low'; }).index();
            if (lowIdx >= 0) {
                table.order([[ lowIdx, 'desc' ]]).draw();
            }

            // Connect search box
            $('#searchBox').on('keyup', function() {
                table.search(this.value).draw();
            });
        }
        init();
    })();

    // Initialize Plotly chart
    if (window.__VAL_DATA && (window.__VAL_DATA.low.length || window.__VAL_DATA.best.length || window.__VAL_DATA.high.length)) {
        var lows = window.__VAL_DATA.low || [];
        var bests = window.__VAL_DATA.best || [];
        var highs = window.__VAL_DATA.high || [];
        var traces = [];
        if (lows.length) traces.push({type:'histogram', x:lows, name:'Low', opacity:0.5, histnorm:'probability density', marker:{color:'rgba(31,119,180,0.6)'}});
        if (bests.length) traces.push({type:'histogram', x:bests, name:'Best', opacity:0.5, histnorm:'probability density', marker:{color:'rgba(255,127,14,0.6)'}});
        if (highs.length) traces.push({type:'histogram', x:highs, name:'High', opacity:0.5, histnorm:'probability density', marker:{color:'rgba(44,160,44,0.6)'}});
        var layout = {barmode:'overlay', title:'Value distribution (Low / Best / High)', xaxis:{title:'Value ($)'}, yaxis:{title:'Density'}};
        Plotly.newPlot('dist-plot', traces, layout, {responsive:true});
    }
    </script>
    ''')

    html_parts.append("<hr/>")
    html_parts.append("<p class='muted'>Enhanced report generated with detailed modals. Click on Series names for condition/analysis details, and Best valuations for grounding sources.</p>")
    html_parts.append("</body></html>")

    # Write to file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(html_parts), encoding="utf-8")
    print(f"Wrote enhanced HTML summary to: {out_path.resolve()}")

def main():
    """Main function to generate enhanced HTML report."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate enhanced HTML report from comic valuation JSON")
    parser.add_argument("json_file", type=Path, help="Path to the JSON results file")
    parser.add_argument("-o", "--output", type=Path, default=Path("results/enhanced_summary.html"), help="Output HTML file path")
    parser.add_argument("--images-dir", type=Path, help="Directory containing original images")
    parser.add_argument("--thumbs-dir", type=Path, help="Directory for thumbnails")
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting")
    parser.add_argument("--id-conf-threshold", type=float, default=ID_CONF_THRESHOLD, help="ID confidence threshold")
    parser.add_argument("--val-conf-threshold", type=float, default=VAL_CONF_THRESHOLD, help="Valuation confidence threshold")

    args = parser.parse_args()

    if not args.json_file.exists():
        print(f"Error: JSON file {args.json_file} not found")
        return 1

    print(f"Loading JSON data from {args.json_file}")
    json_data = load_json_data(args.json_file)

    print("Analyzing data...")
    analysis = analyze_json_data(json_data, args.id_conf_threshold, args.val_conf_threshold)

    print(f"Generating enhanced HTML report...")
    generate_enhanced_html_report(
        analysis=analysis,
        out_path=args.output,
        json_data=json_data,
        id_conf_threshold=args.id_conf_threshold,
        val_conf_threshold=args.val_conf_threshold,
        images_dir=args.images_dir,
        thumbs_dir=args.thumbs_dir,
        no_plot=args.no_plot
    )

    print(f"Enhanced HTML report generated successfully!")
    return 0

if __name__ == "__main__":
    exit(main())
