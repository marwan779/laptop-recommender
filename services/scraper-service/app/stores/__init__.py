from app.stores.base import BaseStoreScraper
from app.stores.compumarts import CompumartsStoreScraper
from app.stores.registry import STORE_REGISTRY, get_all_store_scrapers, get_store_scraper
from app.stores.sigma import SigmaComputerStoreScraper
from app.stores.twob import TwoBStoreScraper

__all__ = [
    "BaseStoreScraper",
    "CompumartsStoreScraper",
    "SigmaComputerStoreScraper",
    "TwoBStoreScraper",
    "STORE_REGISTRY",
    "get_store_scraper",
    "get_all_store_scrapers",
]
