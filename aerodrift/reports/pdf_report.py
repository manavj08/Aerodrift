"""PDF incident reports (reportlab Platypus).

One report covers a remediation run: an executive summary (status,
detection latency, time-to-heal), an incident table, one section per
incident (what drifted, the attack path, the exact AST-generated code,
the sandbox result and verification), and topology diffs
(baseline -> drifted -> healed) when available.
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#1E2761")
MUTED = colors.HexColor("#5A6B8C")
RULE = colors.HexColor("#E0E5F2")
OK = colors.HexColor("#1E7B45")
BAD = colors.HexColor("#C0392B")
_SEVERITY_COLORS = {
    "critical": BAD,
    "high": colors.HexColor("#D35400"),
    "medium": colors.HexColor("#B7950B"),
    "low": colors.HexColor("#2E7D32"),
}


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("AeroTitle", parent=s["Title"], fontSize=22, textColor=NAVY, spaceAfter=4, alignment=0))
    s.add(ParagraphStyle("AeroSubtitle", parent=s["Normal"], fontSize=10, textColor=MUTED, spaceAfter=12))
    s.add(ParagraphStyle("AeroHeading", parent=s["Heading2"], fontSize=13.5, textColor=NAVY, spaceBefore=14, spaceAfter=6))
    s.add(ParagraphStyle("AeroSub", parent=s["Heading3"], fontSize=11.5, textColor=NAVY, spaceBefore=10, spaceAfter=4))
    s.add(ParagraphStyle("AeroBody", parent=s["Normal"], fontSize=10, leading=14))
    s.add(ParagraphStyle("AeroCell", parent=s["Normal"], fontSize=8.5, leading=10.5))
    s.add(ParagraphStyle("AeroCode", parent=s["Code"], fontSize=7.8, leading=10.2, leftIndent=0, firstLineIndent=0))
    s.add(ParagraphStyle("AeroBanner", parent=s["Normal"], fontSize=13, leading=17, textColor=colors.white,
                         fontName="Helvetica-Bold"))
    return s


def _wrap_code(code: str, width: int = 92) -> str:
    """Wrap long generated-code lines for print.

    Prefers breaking at ', ' (argument boundaries); any line still too long
    (e.g. a docstring) is wrapped at spaces. Never splits inside a token.
    """
    out = []
    for line in code.splitlines():
        indent = line[: len(line) - len(line.lstrip())]
        current = ""
        for piece in line.split(", "):
            candidate = piece if not current else current + ", " + piece
            if current and len(candidate) > width:
                out.append(current + ",")
                current = indent + " " * 8 + piece.lstrip()
            else:
                current = candidate
        out.append(current)
    final = []
    for line in out:
        if len(line) <= width:
            final.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        final.extend(textwrap.wrap(line.lstrip(), width=width, initial_indent=indent,
                                   subsequent_indent=indent + " " * 4,
                                   break_long_words=False, break_on_hyphens=False))
    return "\n".join(final)


def _code_box(code: str, s) -> Table:
    t = Table([[Preformatted(_wrap_code(code), s["AeroCode"])]], colWidths=[6.8 * inch])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F6FB")),
                           ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CADCFC")),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def _rec(r) -> dict:
    return r.to_dict() if hasattr(r, "to_dict") else dict(r)


def _p(text, style):
    return Paragraph(escape(str(text)) if text is not None else "—", style)


def _grid(rows, widths, header=True, extra=None):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style + (extra or [])))
    return t


def _kv(rows, s):
    t = Table([[Paragraph(f"<b>{escape(k)}</b>", s["AeroCell"]), _p(v, s["AeroCell"])] for k, v in rows],
              colWidths=[1.6 * inch, 5.2 * inch])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def _diff_section(story, s, title, diff):
    story.append(Paragraph(escape(title), s["AeroSub"]))
    d = diff.to_dict() if hasattr(diff, "to_dict") else diff
    rows = [["", "Change", "Detail"]]
    marks = []
    for n in d.get("added_nodes", []):
        rows.append(["+", "resource added", f"{n['name']} ({n['resource_type']})"])
    for n in d.get("removed_nodes", []):
        rows.append(["-", "resource removed", f"{n['name']} ({n['resource_type']})"])
    for r in d.get("added_rules", []):
        rows.append(["+", "ingress rule", f"{r['rule']} -> {r['target_name']} (from {r['source_name']})"])
    for r in d.get("removed_rules", []):
        rows.append(["-", "ingress rule", f"{r['rule']} -> {r['target_name']} (from {r['source_name']})"])
    for l in d.get("added_links", []):
        rows.append(["+", f"{l['kind']} link", f"{l['source_name']} -> {l['target_name']}"])
    for l in d.get("removed_links", []):
        rows.append(["-", f"{l['kind']} link", f"{l['source_name']} -> {l['target_name']}"])
    for n in d.get("newly_exposed", []):
        rows.append(["!", "newly internet-exposed", n])
    for n in d.get("no_longer_exposed", []):
        rows.append(["ok", "exposure closed", n])
    if len(rows) == 1:
        story.append(Paragraph("No topology changes.", s["AeroBody"]))
        return
    for i, row in enumerate(rows[1:], start=1):
        col = OK if row[0] in ("-", "ok") else BAD
        marks.append(("TEXTCOLOR", (0, i), (0, i), col))
        marks.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
        rows[i] = [row[0], row[1], _p(row[2], s["AeroCell"])]
    story.append(_grid(rows, [0.35 * inch, 1.6 * inch, 4.85 * inch], extra=marks))


def generate_incident_report(output_path: str, records: list, *, diffs: list[tuple[str, object]] | None = None,
                             metrics: dict | None = None, environment: str = "simulated (moto)",
                             title: str = "AeroDrift Incident Report") -> str:
    """Write a PDF incident report and return its path.

    Args:
        output_path: destination file (parent dirs are created).
        records: ``RemediationRecord`` objects or their ``to_dict()`` form.
            A record with no execution result is reported as not executed.
        diffs: optional ``[(title, TopologyDiff), ...]`` sections.
        metrics: optional numbers for the summary, e.g.
            ``detection_latency_s``, ``time_to_heal_s``, ``collect_ms``.
        environment: shown in the header/footer (simulated vs live AWS).
    """
    s = _styles()
    recs = [_rec(r) for r in records]
    metrics = metrics or {}
    story = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    story.append(Paragraph(escape(title), s["AeroTitle"]))
    story.append(Paragraph(f"Generated {now} &nbsp;·&nbsp; Environment: {escape(environment)}", s["AeroSubtitle"]))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#CADCFC"), thickness=1.2))
    story.append(Spacer(1, 10))

    # ---- executive summary
    executed = [r for r in recs if r.get("result", {}).get("status") not in (None, "validated")]
    healed = [r for r in recs if r.get("verified")]
    if not recs:
        banner, bcol = "NO DRIFT — nothing to remediate", OK
    elif executed and len(healed) == len(recs):
        banner, bcol = f"SELF-HEALED — {len(recs)} drift(s) remediated and verified", OK
    elif not executed:
        banner, bcol = f"NOT EXECUTED — {len(recs)} remediation(s) generated for review", colors.HexColor("#B7950B")
    else:
        banner, bcol = f"ACTION REQUIRED — {len(recs) - len(healed)} of {len(recs)} drift(s) not verified healed", BAD
    bt = Table([[Paragraph(escape(banner), s["AeroBanner"])]], colWidths=[6.8 * inch])
    bt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bcol), ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
    story.append(bt)

    story.append(Paragraph("Executive Summary", s["AeroHeading"]))
    sev_counts = {}
    for r in recs:
        sev = (r.get("drift", {}).get("severity") or "unknown").lower()
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
    rows = [("Drifts detected", str(len(recs))),
            ("By severity", ", ".join(f"{k}: {v}" for k, v in sorted(sev_counts.items())) or "—"),
            ("Remediations executed", str(len(executed))),
            ("Verified healed", f"{len(healed)} of {len(recs)}")]
    labels = {"detection_latency_s": ("Detection latency", "{:.3f} s (target < 5 s)"),
              "time_to_heal_s": ("Time to heal", "{:.3f} s (detect -> verified)"),
              "collect_ms": ("Ingestion (async boto3)", "{:.1f} ms"),
              "detect_ms": ("Graph drift query", "{:.2f} ms"),
              "nodes": ("Topology size", "{} nodes"),
              "edges": ("Topology edges", "{}")}
    for key, (label, fmt) in labels.items():
        if metrics.get(key) is not None:
            rows.append((label, fmt.format(metrics[key])))
    story.append(_kv(rows, s))

    # ---- incident table
    if recs:
        story.append(Paragraph("Incidents", s["AeroHeading"]))
        table = [["#", "Severity", "Type", "Security group", "Rule", "Result"]]
        extra = []
        for i, r in enumerate(recs, start=1):
            d = r.get("drift", {})
            sev = (d.get("severity") or "?").lower()
            status = r.get("result", {}).get("status", "not executed")
            verified = r.get("verified")
            res = status + (" / verified" if verified else (" / NOT verified" if verified is False else ""))
            table.append([str(i), sev.upper(), _p(d.get("type"), s["AeroCell"]),
                          _p(d.get("affected_name", d.get("affected_node")), s["AeroCell"]),
                          _p((d.get("offending_edge") or {}).get("rule"), s["AeroCell"]), _p(res, s["AeroCell"])])
            extra += [("TEXTCOLOR", (1, i), (1, i), _SEVERITY_COLORS.get(sev, colors.grey)),
                      ("FONTNAME", (1, i), (1, i), "Helvetica-Bold")]
        story.append(_grid(table, [0.3 * inch, 0.8 * inch, 1.35 * inch, 1.35 * inch, 1.45 * inch, 1.55 * inch],
                           extra=extra))

    # ---- per-incident detail
    for i, r in enumerate(recs, start=1):
        d = r.get("drift", {})
        result = r.get("result") or {}
        block = [Paragraph(f"Incident {i}: {escape(str(d.get('type', '?')))} on "
                           f"{escape(str(d.get('affected_name', d.get('affected_node', '?'))))}", s["AeroHeading"])]
        kv = [("Drift ID", d.get("drift_id")), ("What happened", d.get("description")),
              ("Detected at", d.get("detected_at")),
              ("Security group", f"{d.get('affected_name', '')} ({d.get('affected_node', '?')})"),
              ("Exposed resource", d.get("target_name") or d.get("target_resource")),
              ("Attack path", "  ->  ".join(d.get("path_names") or []) or None),
              ("Offending rule", (d.get("offending_edge") or {}).get("rule"))]
        block.append(_kv([(k, v) for k, v in kv if v], s))
        block.append(Paragraph("Generated remediation (Python <font face='Courier'>ast</font>)", s["AeroSub"]))
        story.append(KeepTogether(block))
        code = r.get("code") or "# no code generated: " + str(result.get("message", ""))
        story.append(_code_box(code, s))
        story.append(Spacer(1, 6))
        status = result.get("status", "not executed")
        col = "#1E7B45" if status in ("success", "noop") else ("#B7950B" if status == "validated" else "#C0392B")
        lines = [f'Sandbox status: <font color="{col}"><b>{escape(status.upper())}</b></font>']
        if result.get("message"):
            lines.append(escape(str(result["message"])))
        if r.get("verified") is True:
            lines.append('<font color="#1E7B45"><b>Verified:</b></font> drift absent after re-ingesting cloud state.')
        elif r.get("verified") is False:
            lines.append('<font color="#C0392B"><b>Not verified:</b></font> drift still present after remediation.')
        if r.get("time_to_heal_s") is not None:
            lines.append(f"Time to heal: {r['time_to_heal_s']:.3f} s")
        story.append(Paragraph("<br/>".join(lines), s["AeroBody"]))

    # ---- diffs
    if diffs:
        story.append(Paragraph("Topology Changes", s["AeroHeading"]))
        for dtitle, diff in diffs:
            _diff_section(story, s, dtitle, diff)

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", color=RULE, thickness=0.75))
    story.append(Paragraph(
        f"Generated automatically by AeroDrift. Environment: {escape(environment)}. Remediation code was "
        "produced with Python's ast module, statically validated, and executed with no builtins through a "
        "least-privilege client proxy.", s["AeroSubtitle"]))

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.85 * inch, 0.5 * inch, "AeroDrift incident report")
        canvas.drawRightString(letter[0] - 0.85 * inch, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output_path), pagesize=letter, leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch, title=title, author="AeroDrift")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return str(output_path)
