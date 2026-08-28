"""Research brief renderer. Distinguishes OBSERVATION / HYPOTHESIS / OPPORTUNITY."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import BUSINESS_GOAL, DISCLAIMER


def _bullets(items: list[dict[str, Any]], key: str = "name") -> str:
    if not items:
        return "- Insufficient evidence in the current corpus.\n"
    lines = []
    for item in items:
        if isinstance(item, dict):
            name = item.get(key) or item.get("opportunity_name") or item.get("topic") or ""
            count = item.get("count") or item.get("evidence_count")
            extra = f" (n={count})" if count is not None else ""
            note = item.get("note") or item.get("problem_statement") or ""
            line = f"- **{name}**{extra}"
            if note:
                line += f" — {note}"
            lines.append(line)
        else:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def render_research_brief(summary: dict[str, Any], window_days: int = 30) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    kpis = summary.get("kpis") or {}
    data_note = f"Live public-source collection. Research window: last {window_days} days (publication date)."
    opp = summary.get("top_opportunities") or []
    evidence_blocks = []
    for item in opp:
        quotes = item.get("supporting_evidence") or []
        qlines = []
        for q in quotes[:3]:
            qlines.append(
                f"  - “{q.get('quote')}” — {q.get('source')} ({q.get('url') or 'no url'}), "
                f"intent={q.get('intent')}, status={q.get('status')}, confidence={q.get('confidence')}"
            )
        if not qlines:
            qlines = ["  - no direct evidence"]
        evidence_blocks.append(
            f"- **{item.get('opportunity_name')}** (score {item.get('opportunity_score')}, "
            f"segment: {item.get('user_segment')}, evidence n={item.get('evidence_count')})\n"
            + "\n".join(qlines)
        )

    hypotheses = summary.get("hypotheses") or []
    hyp_lines = "\n".join(f"- HYPOTHESIS: {h}" for h in hypotheses)

    return f"""# Myntra Wishlist Conversion — AI Research Brief

Generated: {now}

Business goal: {BUSINESS_GOAL}

**{DISCLAIMER}**

Data: {data_note}

Scores below are **research-based opportunity prioritization**, not proof of causality
and not Myntra internal analytics.

Corpus snapshot (RAW DATA counts, then ANALYZED DATA labels):

- Total conversations collected (RAW): {kpis.get('total_conversations', 0)}
- Relevant conversations (ANALYZED): {kpis.get('relevant', 0)}
- Wishlist-related (ANALYZED): {kpis.get('wishlist_related', 0)}
- High-intent friction (ANALYZED): {kpis.get('high_intent', 0)}
- Needs human validation: {kpis.get('needs_validation', 0)}

---

## What we learned

These are OBSERVATIONS about the analyzed public corpus, not population facts.

{_bullets(summary.get('top_problems') or [])}

## Why users wishlist

OBSERVATION — motivations mentioned in relevant conversations:

{_bullets(summary.get('motivations') or [])}

## Why users don't purchase

OBSERVATION — blockers mentioned. Frequency ≠ causation.

{_bullets(summary.get('top_blockers') or [])}

## What high-intent users struggle with

Filter: purchase_intent = high AND status in considering / postponed / abandoned / waiting / alternative_purchased.

{_bullets(summary.get('high_intent_top_problems') or [])}

## External behavior

OBSERVATION — where users report seeking information outside Myntra:

{_bullets(summary.get('top_workarounds') or [])}

## Opportunity areas

OPPORTUNITY = prioritized hypothesis space (0–100 composite). Do not treat rank as ROI.

{_bullets(opp, key='opportunity_name')}

### Evidence supporting each opportunity

{chr(10).join(evidence_blocks) if evidence_blocks else '- no direct evidence'}

## Contradictory evidence

{(chr(10).join('- ' + c.get('note', '') for c in summary.get('contradictory_evidence') or []) or '- None flagged in this run.')}

## Evidence gaps

{(chr(10).join('- ' + g for g in summary.get('evidence_gaps') or []) or '- None flagged.')}

## Research hypotheses

Questions for user interviews (HYPOTHESIS, not findings):

{hyp_lines}

## Recommended target segment for primary research

**{summary.get('recommended_segment') or 'unknown'}**

## Recommended problem to investigate

**{summary.get('recommended_problem') or 'insufficient evidence'}**

{summary.get('recommendation_why') or ''}

{summary.get('causal_caveat') or ''}

---

## Structured discovery output

### 1. Top 10 user problems
{_bullets(summary.get('top_problems') or [])}

### 2. Top 10 purchase blockers
{_bullets(summary.get('top_blockers') or [])}

### 3. Top 10 uncertainties
{_bullets(summary.get('top_uncertainties') or [])}

### 4. Top user segments
{_bullets(summary.get('top_segments') or [])}

### 5. Top external workarounds
{_bullets(summary.get('top_workarounds') or [])}

### 6. Top 5 opportunity areas
{_bullets(opp, key='opportunity_name')}

### 7–12. See evidence, contradictions, gaps, hypotheses, segment, and recommended problem above.

Do not propose a product solution in this discovery phase.
"""


def brief_to_pdf_bytes(markdown_text: str) -> bytes:
    """Simple PDF export (plain text layout)."""
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.75 * inch, rightMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    story = []
    for line in markdown_text.splitlines():
        clean = (
            line.replace("**", "")
            .replace("# ", "")
            .replace("## ", "")
            .replace("### ", "")
        )
        if not clean.strip():
            story.append(Spacer(1, 8))
            continue
        escaped = (
            clean.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        style = styles["Heading2"] if line.startswith("#") else styles["BodyText"]
        story.append(Paragraph(escaped, style))
    doc.build(story)
    return buffer.getvalue()
