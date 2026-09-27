# Catalog Database Entities & Required Fields Report

This report summarizes all required fields across the `catalog-service` database entities, compares them against what is currently extracted from official brand portals (such as ASUS Egypt), and identifies fields that **cannot** be obtained from manufacturer spec sheets and must be enriched via secondary sources.

---

## 1. Required Fields by Database Entity

A concise checklist of all database entities in [`services/catalog-service/app/models/`](file:///d:/Development/Side%20Projects/laptop-recommender/services/catalog-service/app/models):

### 🏷️ Product Hierarchy (`laptop.py`)
* **`Brand`**: `name`, `slug`, `website_url`
* **`LaptopFamily`**: `name`, `slug`, `description`
* **`LaptopModel`**: `manufacturer_model` (e.g. `S5452`), `name`, `slug`, `region`
* **`LaptopConfiguration`**: `manufacturer_part_number` (MPN), `identity_hash` (unique SHA-256)

### ⚙️ Core Hardware Components (`components.py`)
* **`CPU`**: `manufacturer`, `name`, `architecture`, `generation`, `cores`, `performance_cores`, `efficiency_cores`, `threads`, `base_clock_ghz`, `boost_clock_ghz`, `tdp_w`, `benchmark_score`
* **`GPU`**: `manufacturer`, `name`, `architecture`, `vram_gb`, `memory_type`, `tdp_w`, `integrated` (bool), `benchmark_score`
* **`Display`**: `size_inches`, `resolution_width`, `resolution_height`, `panel_type` (`OLED`/`IPS`), `refresh_rate_hz`, `aspect_ratio`, `brightness_nits`, `color_gamut`, `srgb_coverage`, `dci_p3_coverage`, `response_time_ms`, `touchscreen`, `oled`, `hdr`
* **`MemoryModule`** & **`LaptopMemory`**: `capacity_gb`, `memory_type`, `speed_mhz`, `is_soldered`, `slot_count`, `max_supported_gb`
* **`StorageDevice`**, **`LaptopStorage`** & **`LaptopStorageSlot`**: `capacity_gb`, `type`, `interface`, `form_factor`, `occupied`, `supports_upgrade`

### 🔋 Mobility, Build & Ergonomics (`configuration.py`)
* **`Battery`**: `capacity_wh`, `cells`, `measured_runtime_h`
* **`LaptopMeasurement`**: `weight_kg`, `length_mm` (width), `width_mm` (depth), `height_mm` (thickness)
* **`LaptopBuild`**: `chassis_material`, `military_standard` (e.g. `MIL-STD 810H`)
* **`LaptopConnectivity`**: `wifi_standard`, `bluetooth_version`, `ethernet`, `ethernet_speed`, `has_hdmi`, `has_sd_card_reader`, `has_headphone_jack`
* **`LaptopPort`**: `port_type`, `quantity`, `version`, `supports_power_delivery`, `supports_display_output`
* **`LaptopWebcam`**: `resolution`, `megapixels`, `has_ir`, `has_privacy_shutter`
* **`LaptopAudio`**: `speaker_quality`, `speaker_loudness_db`, `microphone_quality`
* **`LaptopThermals`**: `cpu_load_temp_c`, `gpu_load_temp_c`, `surface_temp_c`, `fan_noise_db`, `idle_noise_db`, `sustained_performance`, `throttling_observed`

### 📦 Ingestion & Store Mapping (`pipeline.py`)
* **`RawLaptopRecord`**: `data_source_id`, `external_id`, `raw_payload` (JSONB), `processing_status`, `collected_at`
* **`SpecificationEvidence`**: `laptop_configuration_id`, `field_name`, `field_value`, `source_url`, `confidence`, `collected_at`
* **`LaptopConfigurationAlias`**: `canonical_configuration_id`, `source_id`, `external_id`, `alias_type`

---

## 2. Fields Obtained from Official Brand Spec Sheets

Based on real scraped data from the ASUS Egypt portal (e.g. `asus_new_laptops.json` and spec sheets), official brand websites reliably provide:

| Category | Available Fields from Brand Website |
| :--- | :--- |
| **Model & Identity** | Brand (`ASUS`), Family (`Vivobook`), Model Chassis (`S5452`), Sub-Model (`S5452MA`), Full MPN (`90NB1991-M00F40`), Product & Store URLs, Official Price (EGP). |
| **Processor** | Commercial Name (`Intel Core 7 Processor 350`), Base/Boost Clocks (`1.5 GHz up to 4.8 GHz`), Cache (`6MB`), Total Cores & Threads (`6 cores, 6 Threads`), NPU TOPS (`17 TOPS`). |
| **Graphics** | GPU Marketing Name (`Intel Graphics`, `NVIDIA GeForce RTX 4060`), Integrated/Discrete distinction. |
| **Display** | Screen Size (`14.0-inch`), Resolution (`1920 x 1200 WUXGA`), Aspect Ratio (`16:10`), Panel Type (`IPS-level` / `OLED`), Refresh Rate (`60Hz` / `120Hz`), Brightness (`300 nits` / `500 nits`), Color Gamut (`100% sRGB` / `100% DCI-P3`). |
| **Memory** | RAM Capacity (`8GB`, `16GB`, `32GB`), RAM Standard (`LPDDR5X`, `DDR5`), Soldered Status (`on board`), Max system memory. |
| **Storage** | Primary SSD Capacity (`512GB`, `1TB`), SSD Interface (`M.2 NVMe PCIe 4.0`), Expansion Slot Specs (`1x M.2 2280 PCIe 4.0x4`). |
| **Ports & Connectivity** | Exact count of USB-C, USB-A, HDMI versions (`HDMI 2.1 TMDS`), Audio jack (`3.5mm`), Power Delivery & DisplayPort flags, Wi-Fi standard (`Wi-Fi 6 802.11ax`), Bluetooth version (`5.4`). |
| **Battery & Power** | Nominal Capacity (`52.5WHrs`), Battery Chemistry & Cells (`3-cell Li-ion`), Power Adapter Wattage (`48W Type-C`). |
| **Physical & Build** | Exact Weight (`1.20 kg`), Dimensions (`31.31 x 22.08 x 1.54 ~ 1.64 cm`), Military Standard (`US MIL-STD 810H`), Physical Colors (`Matte Gray`). |
| **Webcam & Audio** | Camera Resolution (`1080p FHD`), Infrared Face Unlock (`IR webcam with Windows Hello`), Array Microphone & Built-in Speaker specs. |

> [!NOTE]
> `test_asus_specs.json` captured an unreleased/empty marketing placeholder (`Viewing 1 - 0 of 0`), yielding empty specs `{}`. The scraper's Level 2 placeholder filter correctly skips these empty cards to prevent invalid database rows.

---

## 3. Fields NOT Obtained from Brand Websites (Secondary Source Enrichment Required)

The following database fields **never appear on official brand specification sheets** and must be resolved by `catalog-service` via third-party hardware APIs, benchmark databases, or physical testing:

| Database Entity | Field Not on Brand Site | Why It's Missing on Brand Portal | Required Resolution Method |
| :--- | :--- | :--- | :--- |
| **`CPU`** | `benchmark_score` | Manufacturers do not publish standardized comparative scores (e.g. PassMark / Geekbench). | Query PassMark / Geekbench API by CPU name. |
| **`CPU`** | `architecture` | Brands state marketing names (e.g. `Core Ultra 7 258V`), not architecture codenames (e.g. `Lunar Lake`). | Lookup via static CPU taxonomy table. |
| **`CPU`** | `performance_cores` / `efficiency_cores` | Consumer spec sheets often only state total cores (e.g. `6 cores, 6 threads`). | Derive from CPU spec database. |
| **`CPU`** | `tdp_w` | Brands list adapter wattage (e.g. `48W AC Adapter`), but rarely the chip's base TDP. | Lookup CPU nominal TDP (e.g. `17W` / `28W`). |
| **`GPU`** | `benchmark_score` | 3DMark TimeSpy / FireStrike graphics scores are not published by laptop OEMs. | Query 3DMark benchmark database. |
| **`GPU`** | `tdp_w` (TGP) | OEMs frequently omit exact Total Graphics Power (TGP) limits on thin-and-light models. | Enrich from hardware reviews or manufacturer whitepapers. |
| **`Battery`** | `measured_runtime_h` | Brands list nominal Watt-hours (`52.5Wh`), but not standardized real-world runtime hours. | Enrich from lab reviews (PCMark 10 modern office battery test). |
| **`LaptopThermals`** | `cpu_load_temp_c`, `gpu_load_temp_c`, `fan_noise_db`, `throttling_observed` | Thermal limits and acoustic noise levels are never disclosed by manufacturers. | Lab hardware review telemetry. |
| **`LaptopAudio`** | `speaker_loudness_db`, `headphone_output_quality` | Audio decibels and DAC impedance are third-party lab acoustic measurements. | Acoustic review databases. |
| **`StorageDevice`** | `model_name` | OEMs multi-source SSDs (e.g. Samsung PM9A1, Micron 2400) and only specify `512GB PCIe 4.0`. | Leave `model_name` nullable or set to generic OEM drive. |
| **`LaptopConfigurationAlias`** | `external_id`, `source_id` | Retail offers and store SKU IDs do not exist on manufacturer websites. | Populated by retailer store scrapers (Compumarts, Sigma, 2B). |
