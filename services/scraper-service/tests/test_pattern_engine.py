from bs4 import BeautifulSoup

from app.core.normalizer import ModelNormalizer
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
    assert specs.get("Cores") == "20 Cores"
    assert specs.get("Memory") == "24GB DDR5 5600"
    assert specs.get("Storage") == "512GB SSD"
    assert "RTX 5050" in specs.get("Graphics", "")
    assert specs.get("Operating System") == "Win 11"
    assert specs.get("Warranty") == "2Y Warranty"


def test_title_spec_extractor_dual_storage_lenovo():
    title = "LENOVO GAMING 3 RYZEN 7 5800H 16GB 1TB HDD 256GB SSD RTX 3050 15.6 FHD 165Hz"
    specs = TitleSpecExtractor.extract(title)
    assert specs.get("Processor") == "RYZEN 7 5800H"
    assert specs.get("Memory") == "16GB"
    assert specs.get("Storage") == "1TB HDD + 256GB SSD"
    assert specs.get("Graphics") == "RTX 3050"
    assert "15.6" in specs.get("Display", "")
    assert "165Hz" in specs.get("Display", "")


def test_title_spec_extractor_dell_3510_no_display_hallucination():
    title = "DELL 3510 Core I5 1135G7 4GB 1TB HDD MX350 2GB"
    specs = TitleSpecExtractor.extract(title)
    assert specs.get("Processor") == "Core I5 1135G7"
    assert specs.get("Memory") == "4GB"
    assert specs.get("Storage") == "1TB HDD"
    assert specs.get("Graphics") == "MX350 2GB"
    assert "Display" not in specs  # MUST NOT hallucinate display
    tokens = ModelNormalizer.extract_model_tokens(title)
    assert tokens.get("base_model") == "3510"


def test_title_spec_extractor_xpg_xenia_specs():
    title = 'XPG 15.6" XENIA Xe Gaming Lifestyle Ultrabook Intel EVO Core i7-1135G7 16GB DDR4 4266 Intel Iris Xe FHD Touch 1TB SSD Windows 10 Home'
    specs = TitleSpecExtractor.extract(title)
    assert specs.get("Processor") == "Core i7-1135G7"
    assert specs.get("Memory") == "16GB DDR4 4266"
    assert specs.get("Storage") == "1TB SSD"
    assert specs.get("Graphics") == "Intel Iris Xe"
    assert "15.6" in specs.get("Display", "")
    assert "Touch" in specs.get("Display", "")
    assert "FHD" in specs.get("Display", "")
    assert specs.get("Certification") == "Intel EVO"
    assert specs.get("Operating System") == "Windows 10 Home"


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


def test_autonomous_discovery_data_attribute():
    html = """
    <html>
      <body>
        <div class="product-page">
          <tbody data-oem-specs="Part No: 99-XYZ\nProcessor: Intel Core i7-14700HX\nGraphics: NVIDIA RTX 4070 8GB\nMemory: 32GB DDR5\nStorage: 1TB NVMe SSD">
          </tbody>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    # Using a store with zero pre-registered selectors for this attribute
    store_cfg = StorePatternConfig(store_key="brand_new_store", name="Brand New Store", container_selectors=[".unrelated"])
    PatternRegistry.register(store_cfg)

    res = PatternEngine.extract_specs(
        soup=soup,
        title="Gaming Laptop 16-inch",
        store_key="brand_new_store",
    )

    assert res.has_text_specs is True
    assert res.specs_extraction_source == "dom"
    assert res.pattern_learned is True
    assert "data_attribute:data-oem-specs" in res.learned_pattern_type
    assert res.specs.get("Processor") == "Intel Core i7-14700HX"
    assert res.specs.get("Graphics") == "NVIDIA RTX 4070 8GB"
    # Verify it was auto-registered into PatternRegistry
    registered_cfg = PatternRegistry.get("brand_new_store")
    assert "data-oem-specs" in registered_cfg.learned_data_attributes


def test_autonomous_discovery_unregistered_table():
    html = """
    <html>
      <body>
        <div class="some-random-wrapper">
          <table class="deep-oem-specs-table">
            <tr><td>Processor</td><td>AMD Ryzen 7 7840HS 8 Cores</td></tr>
            <tr><td>Graphics</td><td>NVIDIA GeForce RTX 4060 8GB</td></tr>
            <tr><td>RAM</td><td>16GB DDR5</td></tr>
            <tr><td>SSD</td><td>512GB M.2 NVMe</td></tr>
          </table>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    store_cfg = StorePatternConfig(store_key="table_store", name="Table Store", container_selectors=[".non_existent"])
    PatternRegistry.register(store_cfg)

    res = PatternEngine.extract_specs(
        soup=soup,
        title="Laptop Ryzen 7",
        store_key="table_store",
    )

    assert res.has_text_specs is True
    assert res.specs_extraction_source == "dom"
    assert res.pattern_learned is True
    assert "unregistered_table:" in res.learned_pattern_type
    assert "7840HS" in res.specs.get("Processor", "")
    assert "RTX 4060" in res.specs.get("Graphics", "")
    # Verify selector was dynamically added to container_selectors
    registered_cfg = PatternRegistry.get("table_store")
    assert any("deep-oem-specs-table" in sel for sel in registered_cfg.container_selectors)


def test_autonomous_discovery_collapsible_panel():
    html = """
    <html>
      <body>
        <details class="tech-accordion">
          <summary>Full Tech Specs</summary>
          <p>Processor: Intel Core Ultra 7 155H</p>
          <p>Memory: 16GB LPDDR5X</p>
          <p>Storage: 1TB PCIe 4.0 SSD</p>
          <p>Display: 14.0-inch 2.8K OLED</p>
        </details>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    store_cfg = StorePatternConfig(store_key="panel_store", name="Panel Store", container_selectors=[".empty"])
    PatternRegistry.register(store_cfg)

    res = PatternEngine.extract_specs(
        soup=soup,
        title="ASUS Zenbook 14 OLED",
        store_key="panel_store",
    )

    assert res.has_text_specs is True
    assert res.specs_extraction_source == "dom"
    assert res.pattern_learned is True
    assert "collapsible_panel:" in res.learned_pattern_type
    assert res.specs.get("Processor") == "Intel Core Ultra 7 155H"
    assert res.specs.get("Memory") == "16GB LPDDR5X"


def test_autonomous_discovery_script_payload():
    raw_spec = "Processor\nCore i9-13900HX\nGraphics\nRTX 4090 16GB\nMemory\n64GB DDR5\nStorage\n2TB SSD"
    html = f"""
    <html>
      <body>
        <div class="empty-block"></div>
        <script>
          window.__renderSpecTable("target-elem", "{raw_spec}");
        </script>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    store_cfg = StorePatternConfig(store_key="script_store", name="Script Store", container_selectors=[".empty-block"])
    PatternRegistry.register(store_cfg)

    res = PatternEngine.extract_specs(
        soup=soup,
        title="MSI Titan GT77",
        store_key="script_store",
    )

    assert res.has_text_specs is True
    assert res.specs_extraction_source == "dom"
    assert res.pattern_learned is True
    assert "script_payload:window.__renderSpecTable" in res.learned_pattern_type
    assert res.specs.get("Processor") == "Core i9-13900HX"
    assert res.specs.get("Graphics") == "RTX 4090 16GB"


def test_pattern_anomaly_alerting():
    html = """
    <html>
      <body>
        <div class="empty-block">
          <p>Call store for information</p>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = PatternEngine.extract_specs(
        soup=soup,
        title="Dell Latitude 5540 - Core i5 - 16GB - 512GB SSD",
        store_key="anomaly_store",
    )

    assert res.has_text_specs is False
    assert res.specs_extraction_source == "title_fallback"
    assert res.is_anomaly is True
    assert res.anomaly_reason is not None
    assert "neither text specs nor flyer images" in res.anomaly_reason


