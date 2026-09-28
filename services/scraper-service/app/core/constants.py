from typing import TypedDict


class BrandConfig(TypedDict):
    name: str
    slug: str
    catalog_url: str
    region: str


BRAND_CATALOGS: dict[str, BrandConfig] = {
    "asus": {
        "name": "ASUS",
        "slug": "asus",
        "catalog_url": "https://www.asus.com/eg-en/store/laptops/",
        "region": "eg-en",
    },
    "lenovo": {
        "name": "Lenovo",
        "slug": "lenovo",
        "catalog_url": "https://www.lenovo.com/eg/en/laptops/subseries-results/",
        "region": "eg-en",
    },
    "hp": {
        "name": "HP",
        "slug": "hp",
        "catalog_url": "https://www.hp.com/eg-en/shop/laptops.html",
        "region": "eg-en",
    },
    "dell": {
        "name": "Dell",
        "slug": "dell",
        "catalog_url": "https://www.dell.com/en-eg/shop/dell-laptops/sc/laptops",
        "region": "eg-en",
    },
    "acer": {
        "name": "Acer",
        "slug": "acer",
        "catalog_url": "https://www.acer.com/eg-en/laptops",
        "region": "eg-en",
    },
    "gigabyte": {
        "name": "GigaByte",
        "slug": "gigabyte",
        "catalog_url": "https://www.gigabyte.com/eg/Laptop",
        "region": "eg",
    },
}
