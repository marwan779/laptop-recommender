from app.stores.amazon import AmazonStoreScraper
from app.stores.base import BaseStoreScraper
from app.stores.btech import BTechStoreScraper
from app.stores.compumarts import CompumartsStoreScraper
from app.stores.elbadr import ElBadrStoreScraper
from app.stores.noon import NoonStoreScraper
from app.stores.registry import STORE_REGISTRY, get_all_store_scrapers, get_store_scraper
from app.stores.sigma import SigmaComputerStoreScraper
from app.stores.tradeline import TradelineStoreScraper
from app.stores.twob import TwoBStoreScraper

__all__ = [
    "AmazonStoreScraper",
    "BaseStoreScraper",
    "BTechStoreScraper",
    "CompumartsStoreScraper",
    "ElBadrStoreScraper",
    "NoonStoreScraper",
    "SigmaComputerStoreScraper",
    "TradelineStoreScraper",
    "TwoBStoreScraper",
    "STORE_REGISTRY",
    "get_store_scraper",
    "get_all_store_scrapers",
]
