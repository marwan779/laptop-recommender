"""HTML & CSS Email Builder Components.

Uses email-client safe inline CSS styles compatible with Gmail, Outlook,
Apple Mail, and mobile email clients.
"""

from typing import Any


def render_badge(status: str) -> str:
    """Render a color-coded status badge."""
    status_upper = status.upper()
    if status_upper in ("SUCCESS", "ALL COMPLETED"):
        bg, color, border = "#dcfce7", "#15803d", "#86efac"
    elif status_upper in ("PARTIAL", "PARTIAL_SUCCESS", "WARNING"):
        bg, color, border = "#fef3c7", "#b45309", "#fcd34d"
    else:
        bg, color, border = "#fee2e2", "#b91c1c", "#fca5a5"

    return (
        f'<span style="display: inline-block; padding: 4px 12px; font-size: 12px; '
        f'font-weight: 700; border-radius: 9999px; background-color: {bg}; '
        f'color: {color}; border: 1px solid {border}; text-transform: uppercase; '
        f'letter-spacing: 0.5px;">{status_upper.replace("_", " ")}</span>'
    )


def render_metric_cards(metrics: list[dict[str, Any]]) -> str:
    """Render a responsive row of 2-4 metric cards using table layout for universal email client support."""
    cards_html = []
    width_pct = int(100 / max(1, len(metrics)))

    for m in metrics:
        val = m.get("value", "0")
        label = m.get("label", "")
        color = m.get("color", "#0f172a")

        cards_html.append(
            f'<td style="width: {width_pct}%; padding: 6px; vertical-align: top;">'
            f'<div style="background-color: #f8fafc; border: 1px solid #e2e8f0; '
            f'border-radius: 8px; padding: 14px 12px; text-align: center;">'
            f'<div style="font-size: 24px; font-weight: 800; color: {color}; line-height: 1.2;">{val}</div>'
            f'<div style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; '
            f'letter-spacing: 0.5px; margin-top: 4px;">{label}</div>'
            f'</div></td>'
        )

    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin: 16px 0 24px 0;">'
        f'<tr>{"".join(cards_html)}</tr></table>'
    )


def render_pointers_list(pointers: list[str]) -> str:
    """Format the top 3 newest laptop pointers cleanly."""
    if not pointers:
        return '<span style="color: #94a3b8; font-style: italic;">None recorded</span>'

    items = "".join(
        f'<div style="margin-bottom: 3px; font-size: 12px; color: #1e293b; line-height: 1.3;">'
        f'<span style="color: #3b82f6; font-weight: bold; margin-right: 4px;">&bull;</span> {p}'
        f'</div>'
        for p in pointers[:3]
    )
    return f'<div style="padding-top: 2px;">{items}</div>'


def render_shell(title: str, content_html: str, subtitle: str | None = None) -> str:
    """Wrap content in a polished, responsive container with headers and footers."""
    sub_html = (
        f'<p style="margin: 6px 0 0 0; font-size: 13px; color: #94a3b8; font-weight: 400;">{subtitle}</p>'
        if subtitle
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin: 0; padding: 24px 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: #0f172a;">
  <div style="max-width: 660px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; border: 1px solid #cbd5e1; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); overflow: hidden;">
    
    <!-- Header -->
    <div style="background-color: #0f172a; padding: 24px 28px; border-bottom: 3px solid #3b82f6;">
      <div style="font-size: 11px; font-weight: 700; color: #60a5fa; text-transform: uppercase; letter-spacing: 1px;">
        Laptop Recommender &bull; Autonomous Ingestion Engine
      </div>
      <h1 style="margin: 8px 0 0 0; font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px;">
        {title}
      </h1>
      {sub_html}
    </div>

    <!-- Main Body -->
    <div style="padding: 24px 28px;">
      {content_html}
    </div>

    <!-- Footer -->
    <div style="background-color: #f8fafc; padding: 18px 28px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #64748b; line-height: 1.5;">
      <div>This is an automated notification dispatched by the <strong>Laptop Recommender Scraper Service</strong>.</div>
      <div style="margin-top: 4px; color: #94a3b8;">Watermark pointers will be automatically used to anchor the next incremental scraping cycle.</div>
    </div>

  </div>
</body>
</html>
"""

