from app.engine.base import IScraperEngine
from app.stores.amazon import AmazonStoreScraper
from app.stores.base import BaseStoreScraper
from app.stores.btech import BTechStoreScraper
from app.stores.compumarts import CompumartsStoreScraper
from app.stores.elbadr import ElBadrStoreScraper
from app.stores.noon import NoonStoreScraper
from app.stores.sigma import SigmaComputerStoreScraper
from app.stores.tradeline import TradelineStoreScraper
from app.stores.twob import TwoBStoreScraper

# Extensible registry of Egyptian retail stores
STORE_REGISTRY: dict[str, type[BaseStoreScraper]] = {
    "compumarts": CompumartsStoreScraper,
    "elbadr": ElBadrStoreScraper,
    "sigma": SigmaComputerStoreScraper,
    "twob": TwoBStoreScraper,
    "tradeline": TradelineStoreScraper,
    "amazon": AmazonStoreScraper,
    "noon": NoonStoreScraper,
    "btech": BTechStoreScraper,
}


def get_store_scraper(store_key: str, engine: IScraperEngine) -> BaseStoreScraper:
    """Instantiate a store scraper by key."""
    scraper_cls = STORE_REGISTRY.get(store_key.lower())
    if not scraper_cls:
        raise ValueError(f"Unknown store '{store_key}'. Available stores: {list(STORE_REGISTRY.keys())}")
    return scraper_cls(engine=engine)


def get_all_store_scrapers(engine: IScraperEngine) -> list[BaseStoreScraper]:
    """Instantiate all registered Egyptian store scrapers."""
    return [cls(engine=engine) for cls in STORE_REGISTRY.values()]
