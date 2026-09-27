import argparse
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rich.tree import Tree

from app.core.constants import BRAND_CATALOGS
from app.engine.scrapling_engine import ScraplingEngine
from app.scrapers.asus import AsusBrandScraper
from app.services.store_aggregator import StoreAggregatorService
from app.stores.registry import STORE_REGISTRY

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="Terminal CLI for Laptop Scraper Service (Multi-Store & Official Catalogs)"
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
        default="stores",
        choices=["stores", "brand-only"],
        help="Execution mode: 'stores' (Brand Level 1 -> Egyptian Stores Deep Search) or 'brand-only' (Brand official site Level 1/2) (default: stores)",
    )
    parser.add_argument(
        "--stores",
        type=str,
        default="all",
        help=f"Comma-separated store keys to search ({','.join(STORE_REGISTRY.keys())}) or 'all' (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of laptops to search/scrape (default: unlimited in brand-only mode, 3 in stores mode)",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=1,
        choices=[1, 2],
        help="Brand extraction level when in 'brand-only' mode: 1 (Summary) or 2 (Deep Crawl specs) (default: 1)",
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
        default=5,
        help="Maximum number of catalog pages to scan as a safety limit (default: 5)",
    )

    args = parser.parse_args()

    limit_display = str(args.limit) if args.limit is not None else ("3 (Default)" if args.mode == "stores" else "Unlimited")

    console.print(
        Panel.fit(
            f"[bold cyan]Laptop Recommender - Multi-Store Scraper Service CLI[/bold cyan]\n"
            f"[yellow]Brand:[/yellow] {args.brand.upper()} | "
            f"[yellow]Mode:[/yellow] {args.mode.upper()} | "
            f"[yellow]Until Model:[/yellow] {args.until_model or 'None (Full Catalog)'} | "
            f"[yellow]Max Pages:[/yellow] {args.max_pages} | "
            f"[yellow]Limit:[/yellow] {limit_display}",
            border_style="cyan",
        )
    )

    engine = ScraplingEngine()

    if args.brand == "asus":
        scraper = AsusBrandScraper(engine=engine)
    else:
        console.print(f"[red]Scraper for brand '{args.brand}' is not implemented yet. Starting with ASUS first![/red]")
        sys.exit(1)

    # =========================================================================
    # Mode 1: Multi-Store Deep Search (Brand L1 -> Compumarts, Sigma, 2B, etc.)
    # =========================================================================
    if args.mode == "stores":
        console.print(f"\n[bold green]Running Multi-Store Search Flow...[/bold green]")
        store_keys = (
            None
            if args.stores.lower() == "all"
            else [s.strip().lower() for s in args.stores.split(",") if s.strip()]
        )

        aggregator = StoreAggregatorService(engine=engine)
        store_limit = args.limit if args.limit is not None else 3
        catalog_result = aggregator.aggregate_brand_laptops(
            brand_scraper=scraper,
            laptop_limit=store_limit,
            store_keys=store_keys,
            offers_per_store=2,
        )

        # Render Rich nested Tree: Brand -> ModelFamily -> ConfigurationItem -> RetailOffer
        root_tree = Tree(
            f"[bold cyan]BRAND: {catalog_result.brand}[/bold cyan] "
            f"([dim]{catalog_result.official_catalog_url}[/dim])"
        )

        for family in catalog_result.model_families:
            family_node = root_tree.add(
                f"[bold white]{family.name}[/bold white] | "
                f"Family: [cyan]{family.family or 'N/A'}[/cyan] | "
                f"Base Model: [bold magenta]{family.base_model or 'N/A'}[/bold magenta] | "
                f"Configurations: [green]{len(family.configurations)}[/green]"
            )
            family_node.add(f"[dim blue]{family.product_url}[/dim blue]")

            for config in family.configurations:
                mpn_str = f" [dim](MPN: {config.mpn})[/dim]" if config.mpn else ""
                specs_count = len(config.official_specs)
                config_node = family_node.add(
                    f"⚙️  [bold yellow]{config.model}[/bold yellow]{mpn_str} | "
                    f"Series: [magenta]{config.model_series or 'N/A'}[/magenta] | "
                    f"Specs: [green]{specs_count}[/green] | "
                    f"Offers: [green]{len(config.stores)}[/green]"
                )

                if config.stores:
                    for offer in config.stores:
                        stock_badge = "[green][In Stock][/green]" if offer.in_stock else "[red][Out of Stock][/red]"
                        price_badge = f"[bold green]{offer.price_str or 'Price N/A'}[/bold green]"
                        match_badge = f"[{offer.match_status.value} via {offer.match_method.value} ({offer.match_confidence:.0%})]"
                        offer_node = config_node.add(
                            f"🛒 [bold cyan]{offer.store_name}[/bold cyan]: {offer.title}\n"
                            f"   Price: {price_badge} | Stock: {stock_badge} | [dim]{match_badge}[/dim]"
                        )
                        offer_node.add(f"[blue]{offer.product_url}[/blue]")
                        if offer.retailer_mpn:
                            offer_node.add(f"[dim]Store MPN/SKU: {offer.retailer_mpn}[/dim]")
                else:
                    config_node.add("[dim yellow]No verified retail offers found for this configuration[/dim yellow]")

        console.print("\n", root_tree)

        console.print(
            Panel.fit(
                f"[bold green]Multi-Store Aggregation Complete![/bold green]\n"
                f"Model Families: [bold]{catalog_result.total_families}[/bold]\n"
                f"Official Configurations: [bold]{catalog_result.total_configurations}[/bold]\n"
                f"Total Retail Offers Found in Stores: [bold]{catalog_result.total_store_offers}[/bold]",
                border_style="green",
            )
        )

        if args.save_json:
            with open(args.save_json, "w", encoding="utf-8") as f:
                json.dump(catalog_result.model_dump(), f, indent=2, ensure_ascii=False)
            console.print(f"[green]Saved nested catalog to {args.save_json}[/green]")

    # =========================================================================
    # Mode 2: Brand-Only Official Catalog Scraping (Level 1 / Level 2)
    # =========================================================================
    elif args.mode == "brand-only":
        from app.services.asus_scraper_service import AsusScraperService

        asus_service = AsusScraperService(engine=engine)
        mode_str = f"level{args.level}"
        catalog_result = asus_service.scrape(
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
                    s.name,
                    s.family or "N/A",
                    s.model or "N/A",
                    str(s.release_year or "N/A"),
                    s.price or "N/A",
                    s.product_url,
                )
            console.print(table)

        elif args.level == 2:
            for detail in catalog_result.laptops:
                console.print(f"\n[bold blue]{'='*80}[/bold blue]")
                console.print(f"[bold white on blue] LAPTOP: {detail.name} ({detail.family or 'Unknown'}) [/bold white on blue]")
                console.print(f"[cyan]Model / Variants:[/cyan] [bold magenta]{detail.model}[/bold magenta] ({len(detail.model_variants)} variants)")
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
                            spec_table.add_row(k.replace('_', ' ').title(), v[:120] + ("..." if len(v) > 120 else ""))
                    console.print(spec_table)

        pointers_str = ", ".join(catalog_result.latest_pointers) if catalog_result.latest_pointers else "None"
        console.print(
            Panel.fit(
                f"[bold green]ASUS Brand Scraping Complete![/bold green]\n"
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


