import argparse
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.core.constants import BRAND_CATALOGS
from app.engine.scrapling_engine import ScraplingEngine
from app.schemas.orchestrator import ScrapeRequest
from app.services.orchestrator import BRAND_SERVICE_REGISTRY, ScrapeOrchestrator
from app.stores.registry import STORE_REGISTRY

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


console = Console(highlight=False)


def safe_terminal_text(text: str) -> str:
    """Sanitize strings for ASCII/Windows terminal output."""
    if not text:
        return ""
    # Replace common problematic characters
    replacements = {
        "\u2033": '"',
        "\u2032": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2022": "*",
        "\xae": "(R)",
        "\u2122": "(TM)",
        "\u2013": "-",
        "\u2014": "-",
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    return text


SUPPORTED_BRANDS = list(BRAND_CATALOGS.keys())
SUPPORTED_STORES = list(STORE_REGISTRY.keys())


def main():
    parser = argparse.ArgumentParser(
        description="Terminal CLI for Laptop Scraper Service (Pure Ingestion for Brands & Retail Stores)"
    )
    parser.add_argument(
        "--brand",
        type=str,
        default="asus",
        choices=SUPPORTED_BRANDS,
        help="Laptop brand to scrape (default: asus)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="brand-only",
        choices=["brand", "brand-only", "store", "stores"],
        help="Execution mode: 'brand-only'/'brand' (Official Brand Catalog Level 1/2) or 'store'/'stores' (Direct Retailer Store Scraping) (default: brand-only)",
    )
    parser.add_argument(
        "--stores",
        type=str,
        default="all",
        help=f"Comma-separated store keys to scrape ({','.join(SUPPORTED_STORES)}) or 'all' (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of laptops to search/scrape (default: unlimited)",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=1,
        choices=[1, 2],
        help="Extraction level: 1 (Summary/Cards) or 2 (Deep Crawl specs & PDP) (default: 1)",
    )
    parser.add_argument(
        "--save-json",
        type=str,
        default=None,
        help="Optional file path to save the scraped JSON output",
    )
    parser.add_argument(
        "--until-model",
        type=str,
        default=None,
        help="Watermark pointer: stop scraping when reaching this laptop model, name, or URL slug (e.g. 'S5452' or 'ASUS Vivobook S14 (S5452)')",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional maximum number of catalog pages to scan as a safety limit (default: None - all pages)",
    )

    args = parser.parse_args()

    limit_display = str(args.limit) if args.limit is not None else "Unlimited"
    max_pages_display = str(args.max_pages) if args.max_pages is not None else "Unlimited (All Pages)"

    console.print(
        Panel.fit(
            f"[bold cyan]Laptop Recommender - Autonomous Scraper Service CLI[/bold cyan]\n"
            f"[yellow]Target:[/yellow] {args.brand.upper() if args.mode in ('brand', 'brand-only') else args.stores.upper()} | "
            f"[yellow]Mode:[/yellow] {args.mode.upper()} | "
            f"[yellow]Until Model:[/yellow] {args.until_model or 'None (Full Catalog)'} | "
            f"[yellow]Max Pages:[/yellow] {max_pages_display} | "
            f"[yellow]Limit:[/yellow] {limit_display}",
            border_style="cyan",
        )
    )

    # ── Build ScrapeRequest from CLI args ────────────────────────────────

    if args.mode in ("store", "stores"):
        targets = "all" if args.stores.lower() == "all" else [s.strip().lower() for s in args.stores.split(",") if s.strip()]
        request = ScrapeRequest(
            target_type="store",
            targets=targets,
            level=args.level,
            until_model=args.until_model,
            max_pages=args.max_pages,
            limit=args.limit,
        )
    else:
        request = ScrapeRequest(
            target_type="brand",
            targets=[args.brand],
            level=args.level,
            until_model=args.until_model,
            max_pages=args.max_pages,
            limit=args.limit,
        )

    # ── Execute via orchestrator ─────────────────────────────────────────

    engine = ScraplingEngine()
    orchestrator = ScrapeOrchestrator(engine=engine)
    response = orchestrator.execute(request)

    # ── Display results ──────────────────────────────────────────────────

    for target_result in response.results:
        if target_result.error:
            console.print(f"[red][!] Error scraping {target_result.target_key}: {target_result.error}[/red]")
            continue

        if target_result.target_type == "store":
            _display_store_result(target_result, args)
        else:
            _display_brand_result(target_result, args)

    # ── Final summary ────────────────────────────────────────────────────

    if request.target_type == "store":
        store_keys = [r.target_key for r in response.results]
        console.print(
            Panel.fit(
                f"[bold green]Store Scraping Ingestion Complete![/bold green]\n"
                f"Stores Scraped: [bold]{', '.join(store_keys)}[/bold]\n"
                f"Note: Matching and entity resolution are handled downstream by catalog-service.",
                border_style="green",
            )
        )


def _display_store_result(target_result, args) -> None:
    """Render a Rich table for a single store scrape result."""
    catalog = target_result.store_result
    if not catalog:
        return

    table = Table(title=f"Store: {catalog.store_name} ({catalog.total_products} Laptops Scraped)")
    table.add_column("No.", style="dim", width=4)
    table.add_column("Product Title", style="bold")
    table.add_column("MPN / SKU", style="cyan")
    table.add_column("Specs", style="yellow")
    table.add_column("Price (EGP)", style="green")
    table.add_column("Stock", style="magenta")
    table.add_column("Product URL", style="blue")

    for idx, p in enumerate(catalog.products, 1):
        stock_str = "[green]In Stock[/green]" if p.in_stock else "[red]Out of Stock[/red]"
        table.add_row(
            str(idx),
            safe_terminal_text(p.title[:50] + ("..." if len(p.title) > 50 else "")),
            safe_terminal_text(p.retailer_sku or p.mpn or "N/A"),
            f"{len(p.specs)} fields",
            safe_terminal_text(p.price_str or str(p.price_egp or "N/A")),
            stock_str,
            p.product_url,
        )
    console.print(table)

    dest_file = args.save_json or f"store_{target_result.target_key}.json"
    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump(catalog.model_dump(), f, indent=2, ensure_ascii=False)
    console.print(f"[green][+] Saved {catalog.total_products} raw store products to {dest_file}[/green]")


def _display_brand_result(target_result, args) -> None:
    """Render Rich output for a single brand scrape result."""
    catalog = target_result.brand_result
    if not catalog:
        return

    if args.level == 1:
        table = Table(title=f"Level 1: {catalog.brand} Laptops ({catalog.total_laptops})")
        table.add_column("No.", style="dim", width=4)
        table.add_column("Laptop Name", style="bold")
        table.add_column("Family", style="cyan")
        table.add_column("Model Code", style="magenta")
        table.add_column("Est. Year", style="yellow")
        table.add_column("Price (EGP)", style="green")
        table.add_column("Product URL", style="blue")

        for idx, s in enumerate(catalog.laptops, 1):
            table.add_row(
                str(idx),
                safe_terminal_text(s.name),
                safe_terminal_text(s.family or "N/A"),
                safe_terminal_text(s.model or "N/A"),
                str(s.release_year or "N/A"),
                s.price or "N/A",
                s.product_url,
            )
        console.print(table)

    elif args.level == 2:
        for detail in catalog.laptops:
            console.print(f"\n[bold blue]{'='*80}[/bold blue]")
            console.print(f"[bold white on blue] LAPTOP: {safe_terminal_text(detail.name)} ({detail.family or 'Unknown'}) [/bold white on blue]")
            console.print(f"[cyan]Model / Variants:[/cyan] [bold magenta]{safe_terminal_text(detail.model or '')}[/bold magenta] ({len(detail.model_variants)} variants)")
            console.print(f"[cyan]Est. Release Date / Year:[/cyan] [bold yellow]{detail.release_date or detail.release_year or 'N/A'}[/bold yellow]")
            console.print(f"[cyan]Price (EGP):[/cyan] [bold green]{detail.price or 'N/A'}[/bold green]")
            console.print(f"[cyan]Configurations Identified:[/cyan] [bold cyan]{len(detail.configurations)}[/bold cyan]")
            console.print(f"[cyan]Total Specs Fields Extracted:[/cyan] [bold green]{len(detail.all_specs)}[/bold green]")

            if detail.structured_specs:
                spec_table = Table(title="Core Structured Hardware Specifications")
                spec_table.add_column("Component", style="bold yellow", width=25)
                spec_table.add_column("Specification Details", style="white")

                for k, v in detail.structured_specs.items():
                    if v:
                        spec_table.add_row(k.replace('_', ' ').title(), safe_terminal_text(v[:120]) + ("..." if len(v) > 120 else ""))
                console.print(spec_table)

    pointers_str = ", ".join(catalog.latest_pointers) if catalog.latest_pointers else "None"
    console.print(
        Panel.fit(
            f"[bold green]{catalog.brand.upper()} Brand Scraping Complete![/bold green]\n"
            f"Mode: [bold]{catalog.scrape_mode.upper()}[/bold]\n"
            f"Until Model: [bold]{catalog.until_model or 'None (Full Catalog)'}[/bold]\n"
            f"Latest Pointers (Top 3): [bold]{pointers_str}[/bold]\n"
            f"Total Laptops: [bold]{catalog.total_laptops}[/bold]\n"
            f"Total Configurations: [bold]{catalog.total_configurations}[/bold]",
            border_style="green",
        )
    )

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump(catalog.model_dump(), f, indent=2, ensure_ascii=False)
        console.print(f"[green][+] Saved results to {args.save_json}[/green]")


if __name__ == "__main__":
    main()
