"""Test verifying CompuMarts HTML parsing and full pipeline extraction."""

from bs4 import BeautifulSoup
from app.core.patterns.engine import PatternEngine
from app.pipeline.orchestrator import LaptopExtractionPipeline, RawScrapedProduct


def test_compumarts_html_parsing_and_pipeline_execution():
    compumarts_html = """
    <html>
    <head>
        <title>ASUS TUF Gaming A15 FA507NVR - AMD Ryzen 7 7435HS - RTX 4060 - 16GB DDR5</title>
        <script type="application/ld+json">
        {
            "@type": "Product",
            "sku": "FA507NVR-LP003W",
            "offers": {
                "price": "52999",
                "availability": "https://schema.org/InStock"
            }
        }
        </script>
    </head>
    <body>
        <h1 class="product-title">ASUS TUF Gaming A15 FA507NVR - AMD Ryzen 7 7435HS - RTX 4060 - 16GB DDR5</h1>
        <div class="product-description">
            <table>
                <tr><td>Processor</td><td>AMD Ryzen 7 7435HS Processor 3.1GHz (20MB Cache, up to 4.5GHz, 8 cores, 16 Threads)</td></tr>
                <tr><td>Graphics</td><td>NVIDIA GeForce RTX 4060 Laptop GPU 8GB GDDR6</td></tr>
                <tr><td>Memory</td><td>16GB DDR5-4800 SO-DIMM</td></tr>
                <tr><td>Storage</td><td>512GB PCIe 4.0 NVMe M.2 SSD</td></tr>
                <tr><td>Display</td><td>15.6-inch, FHD (1920 x 1080) 16:9, 144Hz, IPS-level, Anti-glare display</td></tr>
                <tr><td>Battery</td><td>90WHrs, 4S1P, 4-cell Li-ion</td></tr>
                <tr><td>Power Supply</td><td>ø6.0, 240W AC Adapter, Output: 20V DC, 12A, 240W</td></tr>
                <tr><td>Weight</td><td>2.20 Kg (4.85 lbs)</td></tr>
                <tr><td>Operating System</td><td>Windows 11 Home</td></tr>
            </table>
        </div>
    </body>
    </html>
    """

    soup = BeautifulSoup(compumarts_html, "html.parser")
    title_elem = soup.select_one("h1.product-title, h1")
    title = title_elem.get_text(strip=True) if title_elem else ""

    spec_res = PatternEngine.extract_specs(soup=soup, title=title, store_key="compumarts")
    assert len(spec_res.specs) >= 8
    assert "Processor" in spec_res.specs
    assert "Graphics" in spec_res.specs

    # Create RawScrapedProduct
    raw_prod = RawScrapedProduct(
        url="https://www.compumarts.com/products/asus-tuf-gaming-a15",
        store="CompuMarts",
        title=title,
        raw_html=compumarts_html,
        raw_tables={"specs": spec_res.specs},
        raw_sections={"Description": spec_res.raw_description or ""},
        price=spec_res.price_val or 52999.0,
    )

    pipeline = LaptopExtractionPipeline()
    result = pipeline.process_raw_product(raw_prod)

    # Verify CPU Ground Truth (AMD Ryzen 7 7435HS)
    assert result.cpu_key == "amd_ryzen_7_7435hs"
    assert result.specs["cpu"]["manufacturer"] == "AMD"
    assert result.specs["cpu"]["model"] == "Ryzen 7 7435HS"
    assert result.specs["cpu"]["cores"] == 8

    # Verify GPU
    assert result.specs["gpu"]["manufacturer"] == "NVIDIA"
    assert result.specs["gpu"]["model"] == "GeForce RTX 4060"
    assert result.specs["gpu"]["vram_gb"] == 8

    # Verify Memory & Storage
    assert result.specs["memory"]["capacity_gb"] == 16
    assert result.specs["memory"]["memory_type"] == "DDR5"
    assert result.specs["storage"]["capacity_gb"] == 512

    # Verify Display & Power
    assert result.specs["display"]["size_inches"] == 15.6
    assert result.specs["display"]["refresh_rate_hz"] == 144
    assert result.specs["power_battery"]["battery_capacity_wh"] == 90.0
    assert result.specs["power_battery"]["power_adapter_w"] == 240
    assert result.specs["physical"]["weight_kg"] == 2.2
