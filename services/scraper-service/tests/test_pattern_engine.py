from bs4 import BeautifulSoup

from app.core.patterns import (
    PatternEngine,
    PatternRegistry,
    SpecExtractionResult,
    StorePatternConfig,
    TitleSpecExtractor,
)


def test_title_spec_extractor():
    title = (
        'Asus ROG Strix G16 G614PH-RV161W Gaming Laptop, AMD R9 8940HX, '
        '16GB RAM, 1TB SSD, RTX 5050 8GB, 16" FHD+ WUXGA 165Hz, Win11, Gray, 90NR0KX7-M001J0'
    )
    specs = TitleSpecExtractor.extract(title)

    assert "Processor" in specs
    assert "8940HX" in specs["Processor"]
    assert "Memory" in specs
    assert "16GB" in specs["Memory"]
    assert "Storage" in specs
    assert "1TB" in specs["Storage"]
    assert "Graphics" in specs
    assert "RTX 5050" in specs["Graphics"]
    assert "Operating System" in specs
    assert "Win11" in specs["Operating System"]


def test_title_spec_extractor_flyer_laptop():
    title = (
        "LENOVO LOQ 15IRX10 83JE00DAED — Core i7-14700HX 20 Cores – 24GB DDR5 5600 – "
        "512GB SSD – RTX 5050 8GB GDDR7 – 15.6 FHD IPS 100% sRGB 144Hz G-SYNC – Win 11 - 2Y Warranty"
    )
    specs = TitleSpecExtractor.extract(title)

    assert specs.get("Processor") == "Core i7-14700HX"
    assert specs.get("Memory") == "24GB DDR5"
    assert specs.get("Storage") == "512GB SSD"
    assert "RTX 5050" in specs.get("Graphics", "")
    assert specs.get("Operating System") == "Win 11"


def test_pattern_registry_registration():
    custom_cfg = StorePatternConfig(
        store_key="custom_store",
        name="Custom Store",
        container_selectors=[".specs-div"],
        delimiters=[":"],
    )
    PatternRegistry.register(custom_cfg)
    retrieved = PatternRegistry.get("custom_store")
    assert retrieved.name == "Custom Store"
    assert retrieved.container_selectors == [".specs-div"]


def test_pattern_engine_dom_markdown_extraction():
    html = """
    <html>
      <body>
        <ul class="product-stats">
          <li>Model: G614PH-RV161W</li>
          <li>MPN: 90NR0KX7-M001J0</li>
        </ul>
        <div class="product_blocks-default">
          <div class="block-content">
            <p><img src="/image/catalog/banner.jpg" /></p>
          </div>
          <div class="block-content">
            <div class="qwen-markdown-paragraph">
              Model Name: ASUS ROG Strix G16 G614PH-RV161W
            </div>
            <ul class="qwen-markdown-list">
              <li>CPU : AMD Ryzen 9 8940HX</li>
              <li>RAM : 16 GB DDR5</li>
              <li>GPU : NVIDIA GeForce RTX 5050</li>
              <li>Storage : 1 TB NVMe SSD</li>
            </ul>
          </div>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    title = "Asus ROG Strix G16 Gaming Laptop"
    res = PatternEngine.extract_specs(
        soup=soup,
        title=title,
        store_key="elbadr",
        base_url="https://elbadrgroupeg.store",
    )

    assert res.has_text_specs is True
    assert res.specs_extraction_source == "dom"
    assert res.specs_fallback_reason is None
    assert res.has_specs_image is True
    assert res.specs_image_url == "https://elbadrgroupeg.store/image/catalog/banner.jpg"
    assert res.mpn == "90NR0KX7-M001J0"
    assert res.model_code == "G614PH-RV161W"
    assert res.specs.get("CPU") == "AMD Ryzen 9 8940HX"
    assert res.specs.get("RAM") == "16 GB DDR5"
    assert res.specs.get("GPU") == "NVIDIA GeForce RTX 5050"
    assert res.specs.get("Model Name") == "ASUS ROG Strix G16 G614PH-RV161W"


def test_pattern_engine_flyer_only_fallback():
    html = """
    <html>
      <body>
        <ul class="product-stats">
          <li>Stock: In Stock</li>
          <li>Model: 83JE00DAED</li>
        </ul>
        <div class="product_blocks-default">
          <div class="block-content">
            <p><img src="/image/catalog/screencapture-lenovo-loq.jpg" /></p>
          </div>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    title = "LENOVO LOQ 15IRX10 83JE00DAED — Core i7-14700HX – 24GB DDR5 – 512GB SSD – RTX 5050 8GB – Win 11"
    res = PatternEngine.extract_specs(
        soup=soup,
        title=title,
        store_key="elbadr",
        base_url="https://elbadrgroupeg.store",
    )

    assert res.has_text_specs is False
    assert res.specs_extraction_source == "title_fallback"
    assert "No text specs found in PDP; image flyer only" in res.specs_fallback_reason
    assert res.has_specs_image is True
    assert res.specs_image_url == "https://elbadrgroupeg.store/image/catalog/screencapture-lenovo-loq.jpg"
    assert res.specs.get("Processor") == "Core i7-14700HX"
    assert res.specs.get("Memory") == "24GB DDR5"
    assert res.specs.get("Storage") == "512GB SSD"
    assert "RTX 5050" in res.specs.get("Graphics", "")
    assert res.specs.get("Model") == "83JE00DAED"


def test_pattern_engine_capacity_collision_prevention():
    html = """
    <html>
      <body>
        <div class="product_blocks-default">
          <div class="block-content">
            <p>Storage</p>
            <p>Capacity: 512 GB</p>
            <p>Interface: PCIe NVMe 4.0</p>
            <p>Battery</p>
            <p>Capacity: 76 Wh</p>
          </div>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    title = "Acer Nitro V 15 Gaming Laptop - 16GB RAM - 512GB SSD"
    res = PatternEngine.extract_specs(soup=soup, title=title, store_key="elbadr")
    # Storage Capacity must NOT be overwritten by Battery Capacity
    assert res.specs.get("Storage Capacity") == "512 GB" or res.specs.get("Capacity") == "512 GB" or "512" in str(res.specs.get("Storage", ""))
    assert "76 Wh" in str(res.specs.get("Battery Capacity", "")) or "76 Wh" in str(res.specs.get("Battery", ""))


def test_pattern_engine_hybrid_title_enrichment():
    html = """
    <html>
      <body>
        <div class="product_blocks-default">
          <div class="block-content">
            <p>CPU: Intel Core Ultra 9 275HX</p>
            <p>RAM: 32GB DDR5</p>
            <p>GPU: RTX 5080</p>
          </div>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    title = "ASUS ROG Strix G16 - 1TB SSD - 16 FHD 165Hz"
    res = PatternEngine.extract_specs(soup=soup, title=title, store_key="elbadr")
    # DOM had CPU, RAM, GPU but missed Storage and Display. Hybrid enrichment backfills them from title!
    assert res.specs.get("CPU") == "Intel Core Ultra 9 275HX"
    assert res.specs.get("Storage") == "1TB" or "1TB" in res.specs.get("Storage", "")
    assert "16" in res.specs.get("Display", "") or "FHD" in res.specs.get("Display", "")

