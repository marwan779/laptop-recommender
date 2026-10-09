"""Unit tests for the Hybrid Table Extraction & Local LLM Specification Pipeline.

Verifies:
1. Deterministic HTML table, list, and attribute extraction (extract_raw_spec_table).
2. Prompt formatting (format_table_for_prompt).
3. Power specification splitting into battery and adapter (split_power_specs).
4. Deterministic reconciliation ensuring zero data loss (reconcile_specs).
5. LocalModelExtractor schema extraction and fallback handling.
6. LocalLLMCompumartsScraper end-to-end PDP extraction and reconciliation.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from local_extractor.schema import LaptopSpecExtraction
from local_extractor.extractor import LocalModelExtractor
from local_extractor.table_extractor import (
    extract_raw_spec_table,
    format_table_for_prompt,
    reconcile_specs,
    split_power_specs,
)
from local_extractor.test_compumarts_pipeline import (
    LocalLLMCompumartsScraper,
    extract_all_technical_data,
)


class TestTableExtractor:
    """Tests for extract_raw_spec_table across varied HTML layouts."""

    def test_extract_standard_html_table(self):
        html = """
        <html><body>
          <table>
            <tr><td>CPU</td><td>Intel Core i7-13650HX</td></tr>
            <tr><td>GPU</td><td>NVIDIA GeForce RTX 4060 8GB</td></tr>
            <tr><td>MEMORY</td><td>16GB DDR5-4800</td></tr>
            <tr><td>STORAGE</td><td>512GB SSD M.2</td></tr>
            <tr><td>DISPLAY</td><td>15.6 FHD 144Hz</td></tr>
            <tr><td>POWER</td><td>60Wh Battery, 170W Slim Tip AC Adapter</td></tr>
            <tr><td>CONNECTIVITY</td><td>1x HDMI 2.1, 2x USB-C, 2x USB 3.2</td></tr>
            <tr><td>OS</td><td>Windows 11 Home</td></tr>
          </table>
        </body></html>
        """
        table = extract_raw_spec_table(html)
        assert len(table) == 8
        assert table["CPU"] == "Intel Core i7-13650HX"
        assert table["GPU"] == "NVIDIA GeForce RTX 4060 8GB"
        assert table["MEMORY"] == "16GB DDR5-4800"
        assert table["STORAGE"] == "512GB SSD M.2"
        assert table["DISPLAY"] == "15.6 FHD 144Hz"
        assert table["POWER"] == "60Wh Battery, 170W Slim Tip AC Adapter"
        assert table["CONNECTIVITY"] == "1x HDMI 2.1, 2x USB-C, 2x USB 3.2"
        assert table["OS"] == "Windows 11 Home"

    def test_extract_table_with_th_headers_and_multi_columns(self):
        html = """
        <table>
          <tr><th>Processor</th><td>AMD Ryzen 7 7840HS</td></tr>
          <tr><th>Graphics</th><td>RTX 4070</td><td>8GB GDDR6</td></tr>
          <tr><th>Battery</th><td>80Wh</td></tr>
        </table>
        """
        table = extract_raw_spec_table(html)
        assert table["Processor"] == "AMD Ryzen 7 7840HS"
        assert table["Graphics"] == "RTX 4070 | 8GB GDDR6"
        assert table["Battery"] == "80Wh"

    def test_extract_data_raw_spec_attribute(self):
        raw_text = (
            "Part No\n90NR0N06-M00JB0\n"
            "Processor\nIntel Core 7 Processor 240H\n"
            "Graphics\nNVIDIA GeForce RTX 4050 6GB\n"
            "Memory\n16GB DDR5-5600\n"
            "Storage\n512GB PCIe 4.0 SSD"
        )
        html = f"""
        <table class="dark-spec-table">
          <tbody data-raw-spec="{raw_text}"></tbody>
        </table>
        """
        table = extract_raw_spec_table(html)
        assert table["Part No"] == "90NR0N06-M00JB0"
        assert table["Processor"] == "Intel Core 7 Processor 240H"
        assert table["Graphics"] == "NVIDIA GeForce RTX 4050 6GB"
        assert table["Memory"] == "16GB DDR5-5600"
        assert table["Storage"] == "512GB PCIe 4.0 SSD"

    def test_extract_definition_list(self):
        html = """
        <dl>
          <dt>CPU</dt><dd>Intel Core i5-12450H</dd>
          <dt>RAM</dt><dd>8GB DDR4</dd>
          <dt>Warranty</dt><dd>1 Year Local</dd>
        </dl>
        """
        table = extract_raw_spec_table(html)
        assert table["CPU"] == "Intel Core i5-12450H"
        assert table["RAM"] == "8GB DDR4"
        assert table["Warranty"] == "1 Year Local"

    def test_extract_spec_row_divs(self):
        html = """
        <div class="specs-container">
          <div class="spec-row">
            <span class="label">Display</span>
            <span class="val">16.0 OLED 3.2K 120Hz</span>
          </div>
          <div class="specification-row" data-label="Camera" data-value="1080p FHD IR"></div>
        </div>
        """
        table = extract_raw_spec_table(html)
        assert table["Display"] == "16.0 OLED 3.2K 120Hz"
        assert table["Camera"] == "1080p FHD IR"

    def test_filter_junk_store_labels(self):
        html = """
        <table>
          <tr><td>CPU</td><td>Core i7</td></tr>
          <tr><td>Welcome to our store</td><td>Click here</td></tr>
          <tr><td>Shipping calculated at checkout</td><td>Yes</td></tr>
          <tr><td>Add to cart</td><td>Now</td></tr>
        </table>
        """
        table = extract_raw_spec_table(html)
        assert "CPU" in table
        assert "Welcome to our store" not in table
        assert "Shipping calculated at checkout" not in table
        assert "Add to cart" not in table


class TestSplitPowerSpecs:
    """Tests for split_power_specs regex logic."""

    def test_split_combined_power_string(self):
        power = "75WHrs, 4S1P, 4-cell Li-ion, 200W AC Adapter"
        battery, adapter = split_power_specs(power)
        assert battery == "75WHrs, 4S1P, 4-cell Li-ion"
        assert adapter == "200W AC Adapter"

    def test_split_lenovo_power_string(self):
        power = "60Wh Battery, 170W Slim Tip AC Adapter"
        battery, adapter = split_power_specs(power)
        assert "60Wh" in battery
        assert "170W Slim Tip AC Adapter" in adapter

    def test_battery_only(self):
        battery, adapter = split_power_specs("57Wh Li-ion")
        assert "57Wh" in battery
        assert adapter is None

    def test_adapter_only(self):
        battery, adapter = split_power_specs("230W AC Adapter")
        assert battery is None
        assert adapter == "230W AC Adapter"


class TestReconcileSpecs:
    """Tests for reconcile_specs guaranteeing zero data loss."""

    def test_reconcile_when_llm_misses_vital_specs(self):
        llm_model = LaptopSpecExtraction(
            processor="Intel Core i7-13620H",
            graphics="NVIDIA GeForce RTX 4050 6GB",
            ram="16GB DDR5 4800Hz",
            storage="512GB NVMe Gen 4",
            display="15.6-inch FHD 165Hz",
            battery=None,
            operating_system=None,
            ports=None,
        )
        raw_table = {
            "CPU": "Intel Core i7-13620H",
            "GPU": "NVIDIA GeForce RTX 4050 6GB",
            "BATTERY": "57Wh",
            "OS": "Windows 11",
            "CONNECTIVITY": "1x HDMI 2.1, 2x USB-C",
            "KEYBOARD": "White Backlit",
            "COLOR": "Obsidian Black",
        }

        reconciled = reconcile_specs(llm_model, raw_table)

        assert reconciled["processor"] == "Intel Core i7-13620H"
        assert reconciled["graphics"] == "NVIDIA GeForce RTX 4050 6GB"
        assert reconciled["battery"] == "57Wh"
        assert reconciled["operating_system"] == "Windows 11"
        assert reconciled["ports"] == "1x HDMI 2.1, 2x USB-C"
        assert reconciled["keyboard"] == "White Backlit"
        assert reconciled["color"] == "Obsidian Black"

    def test_reconcile_preserves_os_none_and_freedos(self):
        raw_table = {
            "CPU": "Ryzen 7 7735HS",
            "GPU": "RTX 4060",
            "MEMORY": "16GB",
            "STORAGE": "512GB",
            "DISPLAY": "15.6 FHD",
            "OS": "FreeDOS",
        }
        reconciled = reconcile_specs(None, raw_table)
        assert reconciled["operating_system"] == "FreeDOS"

    def test_reconcile_splits_power_into_battery_and_adapter(self):
        raw_table = {
            "CPU": "Core Ultra 7 155H",
            "GPU": "RTX 4060",
            "MEMORY": "16GB",
            "STORAGE": "1TB",
            "DISPLAY": "16.0 3.2K OLED",
            "POWER": "75WHrs, 4S1P, 4-cell Li-ion, 200W AC Adapter",
        }
        reconciled = reconcile_specs(None, raw_table)
        assert "75WHrs" in reconciled["battery"]
        assert "200W AC Adapter" in reconciled["power_adapter"]

    def test_reconcile_offline_llm_fallback(self):
        raw_table = {
            "CPU": "Core i7-13650HX",
            "GPU": "RTX 4060 8GB",
            "MEMORY": "16GB DDR5",
            "STORAGE": "512GB SSD",
            "DISPLAY": "15.6 FHD 144Hz",
            "WARRANTY": "2 Years",
            "WEIGHT": "2.38 kg",
        }
        reconciled = reconcile_specs(None, raw_table)
        assert reconciled["processor"] == "Core i7-13650HX"
        assert reconciled["graphics"] == "RTX 4060 8GB"
        assert reconciled["ram"] == "16GB DDR5"
        assert reconciled["storage"] == "512GB SSD"
        assert reconciled["display"] == "15.6 FHD 144Hz"
        assert reconciled["warranty"] == "2 Years"
        assert reconciled["weight"] == "2.38 kg"


class TestPromptFormatting:
    """Tests for format_table_for_prompt."""

    def test_format_table_for_prompt(self):
        table = {
            "CPU": "Intel Core i9-13900H",
            "GPU": "RTX 4070 8GB",
            "MEMORY": "32GB DDR5",
        }
        text = format_table_for_prompt(table, title="Lenovo Legion Pro 5", extra_context="Gaming Beast")
        assert "Product Title: Lenovo Legion Pro 5" in text
        assert "=== RAW SPECIFICATIONS TABLE ===" in text
        assert "CPU: Intel Core i9-13900H" in text
        assert "GPU: RTX 4070 8GB" in text
        assert "MEMORY: 32GB DDR5" in text
        assert "=== ADDITIONAL CONTEXT ===" in text
        assert "Gaming Beast" in text


class TestLocalModelExtractor:
    """Tests for LocalModelExtractor."""

    @patch("httpx.Client.post")
    def test_successful_structured_extraction(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_payload = {
            "processor": "Intel Core i7-13650HX",
            "graphics": "NVIDIA GeForce RTX 4060 8GB",
            "ram": "16GB DDR5",
            "storage": "512GB SSD",
            "display": "15.6 FHD 144Hz",
            "battery": "60Wh",
            "power_adapter": "170W Slim Tip",
            "operating_system": "Windows 11 Home",
            "ports": "1x HDMI 2.1, 2x USB-C",
        }
        mock_response.json.return_value = {
            "message": {"content": json.dumps(mock_payload)}
        }
        mock_post.return_value = mock_response

        extractor = LocalModelExtractor()
        specs, latency, err = extractor.extract("Some input text")

        assert err is None
        assert specs is not None
        assert specs.processor == "Intel Core i7-13650HX"
        assert specs.graphics == "NVIDIA GeForce RTX 4060 8GB"
        assert specs.battery == "60Wh"
        assert specs.operating_system == "Windows 11 Home"

    @patch("httpx.Client.post")
    def test_extract_specs_with_reconciliation(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_payload = {
            "processor": "Intel Core i7-13650HX",
            "graphics": "NVIDIA GeForce RTX 4060 8GB",
            "ram": "16GB DDR5",
            "storage": "512GB SSD",
            "display": "15.6 FHD 144Hz",
        }
        mock_response.json.return_value = {
            "message": {"content": json.dumps(mock_payload)}
        }
        mock_post.return_value = mock_response

        raw_table = {
            "CPU": "Intel Core i7-13650HX",
            "BATTERY": "60Wh",
            "CONNECTIVITY": "1x HDMI, 2x USB",
        }

        extractor = LocalModelExtractor()
        reconciled, model, latency, err = extractor.extract_specs("Some text", raw_table=raw_table)

        assert reconciled["processor"] == "Intel Core i7-13650HX"
        assert reconciled["battery"] == "60Wh"
        assert reconciled["ports"] == "1x HDMI, 2x USB"


class TestCompumartsPipelineScraper:
    """Tests for LocalLLMCompumartsScraper with hybrid table extraction."""

    def test_pipeline_extracts_and_reconciles_pdp(self, monkeypatch):
        scraper = LocalLLMCompumartsScraper()
        mock_html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "Product",
              "name": "Lenovo LOQ 15IRX9",
              "sku": "83DV01HRPS",
              "offers": {
                "@type": "Offer",
                "price": "52000.00",
                "availability": "http://schema.org/InStock"
              }
            }
            </script>
          </head>
          <body>
            <table>
              <tr><td>CPU</td><td>Intel Core i7-13645HX</td></tr>
              <tr><td>GPU</td><td>NVIDIA GeForce RTX 4050 6GB</td></tr>
              <tr><td>MEMORY</td><td>16GB DDR5-4800</td></tr>
              <tr><td>STORAGE</td><td>512GB SSD M.2</td></tr>
              <tr><td>DISPLAY</td><td>15.6 FHD 144Hz G-SYNC</td></tr>
              <tr><td>POWER</td><td>60Wh Battery, 170W Slim Tip AC Adapter</td></tr>
              <tr><td>CONNECTIVITY</td><td>1x HDMI 2.1, 2x USB-C 3.2</td></tr>
              <tr><td>OS</td><td>Windows 11 Home</td></tr>
              <tr><td>WARRANTY</td><td>2 Years Lenovo Warranty</td></tr>
            </table>
          </body>
        </html>
        """
        monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_html)

        mock_llm_specs = LaptopSpecExtraction(
            processor="Intel Core i7-13645HX",
            graphics="NVIDIA GeForce RTX 4050 6GB",
            ram="16GB DDR5-4800",
            storage="512GB SSD M.2",
            display="15.6 FHD 144Hz G-SYNC",
            battery="60Wh",
            power_adapter="170W Slim Tip AC Adapter",
            operating_system="Windows 11 Home",
            ports="1x HDMI 2.1, 2x USB-C 3.2",
            warranty="2 Years Lenovo Warranty",
        )
        monkeypatch.setattr(scraper.extractor, "extract", lambda text: (mock_llm_specs, 0.1, None))

        spec_res = scraper._extract_product_specs(
            "https://www.compumarts.com/products/lenovo-loq",
            title="Lenovo LOQ 15IRX9 83DV01HRPS Gaming Laptop",
        )

        assert spec_res.sku == "83DV01HRPS"
        assert spec_res.price_val == 52000.0
        assert spec_res.in_stock is True
        assert spec_res.specs["processor"] == "Intel Core i7-13645HX"
        assert spec_res.specs["graphics"] == "NVIDIA GeForce RTX 4050 6GB"
        assert spec_res.specs["ram"] == "16GB DDR5-4800"
        assert spec_res.specs["storage"] == "512GB SSD M.2"
        assert spec_res.specs["display"] == "15.6 FHD 144Hz G-SYNC"
        assert spec_res.specs["battery"] == "60Wh"
        assert spec_res.specs["power_adapter"] == "170W Slim Tip AC Adapter"
        assert spec_res.specs["ports"] == "1x HDMI 2.1, 2x USB-C 3.2"
        assert spec_res.specs["operating_system"] == "Windows 11 Home"
        assert spec_res.specs["warranty"] == "2 Years Lenovo Warranty"
        assert spec_res.spec_res.specs_extraction_source == "hybrid_table_llm"

    def test_pipeline_scraper_only_mode(self, monkeypatch):
        scraper = LocalLLMCompumartsScraper(scraper_only=True)
        mock_html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "Product",
              "name": "Acer Aspire Go 16",
              "sku": "NX.JV0EM.006",
              "offers": {
                "@type": "Offer",
                "price": "49999.00",
                "availability": "http://schema.org/InStock"
              }
            }
            </script>
          </head>
          <body>
            <table>
              <tr><td>CPU</td><td>Intel Core 9 270H</td></tr>
              <tr><td>GPU</td><td>Intel Graphics</td></tr>
              <tr><td>MEMORY</td><td>16GB DDR5</td></tr>
              <tr><td>STORAGE</td><td>512GB SSD</td></tr>
              <tr><td>DISPLAY</td><td>16 WUXGA IPS 120Hz</td></tr>
              <tr><td>OS</td><td>EShell</td></tr>
            </table>
          </body>
        </html>
        """
        monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_html)

        spec_res = scraper._extract_product_specs(
            "https://www.compumarts.com/products/acer-aspire-go",
            title="Acer Aspire Go 16 Laptop",
        )

        assert spec_res.sku == "NX.JV0EM.006"
        assert spec_res.price_val == 49999.0
        assert spec_res.in_stock is True
        # In scraper-only mode, specs contain the raw table keys directly
        assert spec_res.specs["CPU"] == "Intel Core 9 270H"
        assert spec_res.specs["GPU"] == "Intel Graphics"
        assert spec_res.specs["MEMORY"] == "16GB DDR5"
        assert spec_res.specs["STORAGE"] == "512GB SSD"
        assert spec_res.specs["DISPLAY"] == "16 WUXGA IPS 120Hz"
        assert spec_res.specs["OS"] == "EShell"
        assert spec_res.spec_res.specs_extraction_source == "scraper_raw_table"

