"""Scraper Email Templates & Body Creators.

Builds concise, numbers-focused single-scraper and batch summary emails.
"""

from __future__ import annotations

from app.email.builder import (
    render_badge,
    render_metric_cards,
    render_pointers_list,
    render_shell,
)
from app.schemas.email import BatchScrapeReport, ScraperFinishedReport


def build_single_finished_email(report: ScraperFinishedReport) -> tuple[str, str, str]:
    """Generate subject, HTML body, and plaintext body for a single scraper completion event.

    Args:
        report: The ScraperFinishedReport DTO.

    Returns:
        tuple[subject, html_body, text_body]
    """
    category_label = "Brand Catalog" if report.target_type == "brand" else "Retail Store"
    status_tag = report.status.upper()

    # 1. Subject Line
    if report.status == "SUCCESS":
        subject = (
            f"[{status_tag}] {report.target_name} Scrape Report "
            f"- {report.scraped_count} Scraped, {report.skipped_count} Skipped ({report.duration_seconds}s)"
        )
    else:
        subject = f"[{status_tag}] {report.target_name} Scrape Failed ({report.duration_seconds}s)"

    # 2. Metric Cards (Numbers only)
    metrics = [
        {
            "label": "Total Scraped",
            "value": str(report.scraped_count),
            "color": "#16a34a" if report.status == "SUCCESS" else "#dc2626",
        },
        {
            "label": "Total Skipped",
            "value": str(report.skipped_count),
            "color": "#dc2626" if report.skipped_count > 0 else "#64748b",
        },
        {
            "label": "Mode",
            "value": report.mode,
            "color": "#0f172a",
        },
        {
            "label": "Duration",
            "value": f"{report.duration_seconds}s",
            "color": "#2563eb",
        },
    ]
    cards_html = render_metric_cards(metrics)

    # 3. Status bar
    status_bar_html = f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
      <span style="font-size: 14px; font-weight: 600; color: #334155;">
        Target: <strong style="color: #0f172a;">{report.target_name}</strong> ({category_label})
      </span>
      {render_badge(report.status)}
    </div>
    """

    # 4. Error box if failed
    error_html = ""
    if report.error_message:
        error_html = f"""
        <div style="margin: 16px 0; padding: 14px 16px; background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px;">
          <div style="font-size: 12px; font-weight: 700; color: #b91c1c; text-transform: uppercase; margin-bottom: 4px;">
            Execution Error
          </div>
          <div style="font-size: 13px; color: #7f1d1d; font-family: monospace;">
            {report.error_message}
          </div>
        </div>
        """

    # 5. Latest 3 Pointers section
    pointers_list_html = render_pointers_list(report.latest_pointers)
    pointers_section_html = f"""
    <div style="margin-top: 20px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
      <div style="font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">
        Latest 3 Pointers (Watermarks for Next Cycle)
      </div>
      {pointers_list_html}
    </div>
    """

    # Watermark info note
    watermark_html = ""
    if report.until_model:
        watermark_html = f"""
        <div style="margin-top: 12px; font-size: 12px; color: #64748b;">
          <strong>Incremental Watermark Used:</strong> <code style="background-color: #f1f5f9; padding: 2px 6px; border-radius: 4px;">{report.until_model}</code>
        </div>
        """

    # Storage upload info note
    storage_html = ""
    if report.storage_key:
        storage_html = f"""
        <div style="margin-top: 12px; padding: 10px 14px; background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; font-size: 12px; color: #166534;">
          <strong>Object Storage (AWS S3):</strong> <code style="background-color: #dcfce7; padding: 2px 6px; border-radius: 4px; color: #14532d; font-family: monospace;">{report.storage_key}</code>
        </div>
        """

    content_html = f"""
    {status_bar_html}
    {error_html}
    {cards_html}
    {pointers_section_html}
    {watermark_html}
    {storage_html}
    """

    html_body = render_shell(
        title=f"{report.target_name} Scraping Summary",
        subtitle=f"Finished at {report.timestamp} &bull; Took {report.duration_seconds}s",
        content_html=content_html,
    )

    # 6. Plaintext Fallback
    text_lines = [
        f"=== {report.target_name} Scraping Summary ===",
        f"Category: {category_label}",
        f"Status: {report.status}",
        f"Mode: {report.mode}",
        f"Total Scraped: {report.scraped_count}",
        f"Total Skipped: {report.skipped_count}",
        f"Duration: {report.duration_seconds}s",
        f"Finished At: {report.timestamp}",
    ]
    if report.storage_key:
        text_lines.append(f"Storage Key (S3): {report.storage_key}")
    if report.latest_pointers:
        text_lines.append("")
        text_lines.append("Latest 3 Pointers:")
        for p in report.latest_pointers[:3]:
            text_lines.append(f"  • {p}")
    if report.error_message:
        text_lines.append("")
        text_lines.append(f"Error: {report.error_message}")

    text_body = "\n".join(text_lines)

    return subject, html_body, text_body


def build_batch_finished_email(report: BatchScrapeReport) -> tuple[str, str, str]:
    """Generate subject, HTML body, and plaintext body for a batch scraping completion event."""
    batch_label = "Brand Catalogs" if report.batch_type == "brand" else "Retail Stores"
    status_tag = "SUCCESS" if report.status == "SUCCESS" else report.status.replace("_", " ")

    subject = (
        f"[{status_tag}] {batch_label} Scrape Complete "
        f"- {report.total_scraped} Ingested, {report.total_skipped} Skipped ({report.duration_seconds}s)"
    )

    metrics = [
        {
            "label": f"Targets ({report.batch_type.capitalize()}s)",
            "value": str(report.total_targets),
            "color": "#0f172a",
        },
        {
            "label": "Total Scraped",
            "value": str(report.total_scraped),
            "color": "#16a34a",
        },
        {
            "label": "Total Skipped",
            "value": str(report.total_skipped),
            "color": "#dc2626" if report.total_skipped > 0 else "#64748b",
        },
        {
            "label": "Duration",
            "value": f"{report.duration_seconds}s",
            "color": "#2563eb",
        },
    ]
    cards_html = render_metric_cards(metrics)

    table_rows = []
    for item in report.targets:
        pointers_html = render_pointers_list(item.latest_pointers)
        error_box = ""
        if item.error_message:
            error_box = f'<div style="font-size: 11px; color: #dc2626; margin-top: 4px;">{item.error_message}</div>'

        table_rows.append(f"""
        <tr style="border-bottom: 1px solid #f1f5f9;">
          <td style="padding: 12px; font-size: 13px; font-weight: 600; color: #0f172a;">
            {item.target_name}
            <span style="font-size: 11px; color: #64748b; display: block; font-weight: 400;">{item.mode}</span>
          </td>
          <td style="padding: 12px; font-size: 13px; font-weight: 700; color: #16a34a; text-align: center;">
            {item.scraped_count}
          </td>
          <td style="padding: 12px; font-size: 13px; font-weight: 600; color: {"#dc2626" if item.skipped_count > 0 else "#64748b"}; text-align: center;">
            {item.skipped_count}
          </td>
          <td style="padding: 12px; font-size: 12px; color: #334155;">
            {pointers_html}
            {error_box}
          </td>
          <td style="padding: 12px; text-align: center;">
            {render_badge(item.status)}
          </td>
        </tr>
        """)

    table_html = f"""
    <div style="overflow-x: auto; margin-top: 16px;">
      <table style="width: 100%; border-collapse: collapse; text-align: left; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;">
        <thead>
          <tr style="background-color: #f8fafc; border-bottom: 2px solid #e2e8f0;">
            <th style="padding: 12px; font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px;">Target</th>
            <th style="padding: 12px; font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; text-align: center;">Scraped</th>
            <th style="padding: 12px; font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; text-align: center;">Skipped</th>
            <th style="padding: 12px; font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px;">Latest Pointers</th>
            <th style="padding: 12px; font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; text-align: center;">Status</th>
          </tr>
        </thead>
        <tbody>
          {"".join(table_rows)}
        </tbody>
      </table>
    </div>
    """

    status_bar_html = f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
      <span style="font-size: 14px; font-weight: 600; color: #334155;">
        Batch Execution Result:
      </span>
      {render_badge(report.status)}
    </div>
    """

    content_html = f"""
    {status_bar_html}
    {cards_html}
    <h3 style="margin: 24px 0 8px 0; font-size: 15px; font-weight: 700; color: #1e293b;">
      Target Breakdown & Watermark Pointers
    </h3>
    {table_html}
    """

    html_body = render_shell(
        title=f"{batch_label} Ingestion Report",
        subtitle=f"Execution completed in {report.duration_seconds}s at {report.finished_at}",
        content_html=content_html,
    )

    text_lines = [
        f"=== {batch_label} Ingestion Report ===",
        f"Status: {report.status}",
        f"Total Ingested: {report.total_scraped}",
        f"Total Skipped: {report.total_skipped}",
        f"Duration: {report.duration_seconds}s",
        f"Finished At: {report.finished_at}",
        "",
        "--- Breakdown by Target ---",
    ]
    for item in report.targets:
        pointers_str = ", ".join(item.latest_pointers) if item.latest_pointers else "None"
        text_lines.append(
            f"• {item.target_name} ({item.mode}): {item.scraped_count} scraped, {item.skipped_count} skipped [{item.status}]"
        )
        text_lines.append(f"  Pointers: {pointers_str}")
        if item.error_message:
            text_lines.append(f"  Error: {item.error_message}")

    text_body = "\n".join(text_lines)

    return subject, html_body, text_body
