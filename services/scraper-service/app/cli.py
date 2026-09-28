import argparse
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.core.constants import BRAND_CATALOGS
from app.engine.scrapling_engine import ScraplingEngine
from app.scrapers.asus import AsusBrandScraper

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SUPPORTED_STORES = ["compumarts", "elbadr", "sigma", "twob"]

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



def main():
    parser = argparse.ArgumentParser(
        description="Terminal CLI for Laptop Scraper Service (Pure Ingestion for Brands & Retail Stores)"
    )
    parser.add_argument(
        "--brand",
        type=str,
        default="asus",
        choices=list(BRAND_CATALOGS.keys()),
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
        default=20,
        help="Maximum number of catalog pages to scan as a safety limit (default: 20)",
    )

    args = parser.parse_args()

    limit_display = str(args.limit) if args.limit is not None else "Unlimited"

    console.print(
        Panel.fit(
            f"[bold cyan]Laptop Recommender - Autonomous Scraper Service CLI[/bold cyan]\n"
            f"[yellow]Target:[/yellow] {args.brand.upper() if args.mode in ('brand', 'brand-only') else args.stores.upper()} | "
            f"[yellow]Mode:[/yellow] {args.mode.upper()} | "
            f"[yellow]Until Model:[/yellow] {args.until_model or 'None (Full Catalog)'} | "
            f"[yellow]Max Pages:[/yellow] {args.max_pages} | "
            f"[yellow]Limit:[/yellow] {limit_display}",
            border_style="cyan",
        )
    )

    engine = ScraplingEngine()

    # =========================================================================
    # Mode 1: Direct Retailer Store Scraping (Compumarts, Sigma, 2B, etc.)
    # (Pure Ingestion into Standalone JSON - Matching Deferred to catalog-service)
    # =========================================================================
    if args.mode in ("store", "stores"):
        from app.schemas.laptop import StoreCatalogResult
        from app.stores.registry import STORE_REGISTRY, get_store_scraper

        console.print(f"\n[bold green]Running Direct Retailer Store Scraping...[/bold green]")
        store_keys = (
            list(STORE_REGISTRY.keys())
            if args.stores.lower() == "all"
            else [s.strip().lower() for s in args.stores.split(",") if s.strip()]
        )

        for s_key in store_keys:
            store_scraper = get_store_scraper(s_key, engine)
            console.print(f"\n[cyan]Scraping retailer:[/cyan] [bold white]{store_scraper.store_name}[/bold white] ({store_scraper.base_url})")

            raw_products = store_scraper.scrape_catalog(
                level=args.level,
                until_model=args.until_model,
                max_pages=args.max_pages,
                limit=args.limit,
            )

            store_catalog = StoreCatalogResult(
                store_name=store_scraper.store_name,
                store_key=store_scraper.store_key,
                store_domain=store_scraper.base_domain,
                scrape_mode=f"level{args.level}",
                until_model=args.until_model,
                total_products=len(raw_products),
                products=raw_products,
            )

            table = Table(title=f"Store: {store_catalog.store_name} ({store_catalog.total_products} Laptops Scraped)")
            table.add_column("No.", style="dim", width=4)
            table.add_column("Product Title", style="bold")
            table.add_column("MPN / SKU", style="cyan")
            table.add_column("Specs", style="yellow")
            table.add_column("Price (EGP)", style="green")
            table.add_column("Stock", style="magenta")
            table.add_column("Product URL", style="blue")

            for idx, p in enumerate(store_catalog.products, 1):
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

            dest_file = args.save_json or f"store_{s_key}.json"
            with open(dest_file, "w", encoding="utf-8") as f:
                json.dump(store_catalog.model_dump(), f, indent=2, ensure_ascii=False)
            console.print(f"[green][+] Saved {store_catalog.total_products} raw store products to {dest_file}[/green]")

        console.print(
            Panel.fit(
                f"[bold green]Store Scraping Ingestion Complete![/bold green]\n"
                f"Stores Scraped: [bold]{', '.join(store_keys)}[/bold]\n"
                f"Note: Matching and entity resolution are handled downstream by catalog-service.",
                border_style="green",
            )
        )
        return

    # =========================================================================
    # Mode 2: Brand-Only Official Catalog Scraping (Level 1 / Level 2)
    # =========================================================================
    elif args.mode in ("brand", "brand-only"):
        if args.brand == "asus":
            from app.services.asus_scraper_service import AsusScraperService
            brand_service = AsusScraperService(engine=engine)
        elif args.brand == "lenovo":
            from app.services.lenovo_scraper_service import LenovoScraperService
            brand_service = LenovoScraperService(engine=engine)
        elif args.brand == "hp":
            from app.services.hp_scraper_service import HpScraperService
            brand_service = HpScraperService(engine=engine)
        else:
            console.print(f"[red]Brand service for '{args.brand}' is in progress. Supported brands: asus, lenovo, hp.[/red]")
            sys.exit(1)


        mode_str = f"level{args.level}"
        catalog_result = brand_service.scrape(
            mode=mode_str,
            until_model=args.until_model,
            max_pages=args.max_pages,
            limit=args.limit,
            output_file=args.save_json,
        )

        if args.level == 1:
            table = Table(title=f"Level 1: {catalog_result.brand} Laptops ({catalog_result.total_laptops})")
            table.add_column("No.", style="dim", width=4)
            table.add_column("Laptop Name", style="bold")
            table.add_column("Family", style="cyan")
            table.add_column("Model Code", style="magenta")
            table.add_column("Est. Year", style="yellow")
            table.add_column("Price (EGP)", style="green")
            table.add_column("Product URL", style="blue")

            for idx, s in enumerate(catalog_result.laptops, 1):
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
            for detail in catalog_result.laptops:
                console.print(f"\n[bold blue]{'='*80}[/bold blue]")
                console.print(f"[bold white on blue] LAPTOP: {safe_terminal_text(detail.name)} ({detail.family or 'Unknown'}) [/bold white on blue]")
                console.print(f"[cyan]Model / Variants:[/cyan] [bold magenta]{safe_terminal_text(detail.model or '')}[/bold magenta] ({len(detail.model_variants)} variants)")
                console.print(f"[cyan]Est. Release Date / Year:[/cyan] [bold yellow]{detail.release_date or detail.release_year or 'N/A'}[/bold yellow]")
                console.print(f"[cyan]Price (EGP):[/cyan] [bold green]{detail.price or 'N/A'}[/bold green]")
                console.print(f"[cyan]Configurations Identified:[/cyan] [bold cyan]{len(detail.configurations)}[/bold cyan]")
                console.print(f"[cyan]Total Specs Fields Extracted:[/cyan] [bold green]{len(detail.all_specs)}[/bold green]")

                if detail.structured_specs:
                    spec_table = Table(title=f"Core Structured Hardware Specifications")
                    spec_table.add_column("Component", style="bold yellow", width=25)
                    spec_table.add_column("Specification Details", style="white")

                    for k, v in detail.structured_specs.items():
                        if v:
                            spec_table.add_row(k.replace('_', ' ').title(), safe_terminal_text(v[:120]) + ("..." if len(v) > 120 else ""))
                    console.print(spec_table)


        pointers_str = ", ".join(catalog_result.latest_pointers) if catalog_result.latest_pointers else "None"
        console.print(
            Panel.fit(
                f"[bold green]{catalog_result.brand.upper()} Brand Scraping Complete![/bold green]\n"
                f"Mode: [bold]{catalog_result.scrape_mode.upper()}[/bold]\n"
                f"Until Model: [bold]{catalog_result.until_model or 'None (Full Catalog)'}[/bold]\n"
                f"Latest Pointers (Top 3): [bold]{pointers_str}[/bold]\n"
                f"Total Laptops: [bold]{catalog_result.total_laptops}[/bold]\n"
                f"Total Configurations: [bold]{catalog_result.total_configurations}[/bold]",
                border_style="green",
            )
        )


if __name__ == "__main__":
    main()

