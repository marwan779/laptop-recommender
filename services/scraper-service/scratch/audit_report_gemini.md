# Post-Pipeline Ground-Truth LLM Audit Report

- **Timestamp**: `2026-10-18 17:58:30 UTC`
- **Auditor Engine**: Google Gemini (`gemini-flash-latest`)
- **Audit Mode**: `DRY-RUN (NO CHANGES SAVED)`
- **Total Laptops Audited**: 14
- **Laptops with Contradictions Detected**: 11 (78.6%)
- **Total Field Corrections**: 18

## Summary by Field

| Field Path | Corrections Count |
| :--- | :--- |
| `audio_webcam.microphone` | 3 |
| `storage.slot_count` | 3 |
| `memory.capacity_gb` | 1 |
| `storage.form_factor` | 1 |
| `display.touchscreen` | 1 |
| `audio_webcam.speaker_count` | 1 |
| `memory.slot_count` | 1 |
| `memory.is_soldered` | 1 |
| `display.hdr` | 1 |
| `identity.warranty` | 1 |
| `storage.max_supported_gb` | 1 |
| `display.size_inches` | 1 |
| `display.panel_type` | 1 |
| `identity.color` | 1 |

## Itemized Corrections Ledger

### 1. Acer Aspire Go 16 AG16-71P-96TX Laptop | Intel Core 9 270H | 16GB DDR5 | 512GB SSD | 16" WUXGA IPS 120Hz | Intel Graphics | No OS | Silver
- **URL**: [https://www.compumarts.com/collections/laptop/products/acer-aspire-go-16-ag16-71p-9142-intel-core-9-270h-16gb-512gb-egypt](https://www.compumarts.com/collections/laptop/products/acer-aspire-go-16-ag16-71p-9142-intel-core-9-270h-16gb-512gb-egypt)
- **Field**: `memory.capacity_gb`
- **Catalog Value**: `8`
- **Corrected Value**: `16`
- **Raw Spec Evidence**: *"Memory: 16GB DDR5 (2 × 8GB)"*
- **Technical Rationale**: The raw specification explicitly states 'Memory: 16GB DDR5 (2 × 8GB)', which contradicts the extracted 8GB capacity.

### 2. Lenovo LOQ 15IRX10 83JE00XEED Gaming Laptop – Intel Core i7-13650HX, RTX 5070 8GB GDDR7, 32GB DDR5, 1TB SSD, 15.6-inch FHD IPS 144Hz, 100% sRGB, G-SYNC, Luna Grey
- **URL**: [https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx10-i7-rtx-5070-32gb-1tb-egypt](https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx10-i7-rtx-5070-32gb-1tb-egypt)
- **Field**: `storage.form_factor`
- **Catalog Value**: `"M.2 2242"`
- **Corrected Value**: `"M.2"`
- **Raw Spec Evidence**: *"Storage: 1TB SSD M.2 2242 PCIe 4.0x4 NVMe"*
- **Technical Rationale**: The raw specification states 'Storage Slot: Two M.2 2280 PCIe 4.0 x4 slots' and 'Storage: 1TB SSD M.2 2242 PCIe 4.0x4 NVMe'. The primary installed drive form factor is M.2 2242, but storage.form_factor should be M.2 or match the primary slot capability. Wait, rule 3c states: 'storage.form_factor describes the PRIMARY INSTALLED SSD... If raw spec states 'Storage: 1TB SSD M.2 2242 PCIe', the installed drive form factor is 'M.2 2242'. So current_value is actually correct according to the rule. Let's look at display.touchscreen.

### 3. Lenovo LOQ 15IRX10 83JE00XEED Gaming Laptop – Intel Core i7-13650HX, RTX 5070 8GB GDDR7, 32GB DDR5, 1TB SSD, 15.6-inch FHD IPS 144Hz, 100% sRGB, G-SYNC, Luna Grey
- **URL**: [https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx10-i7-rtx-5070-32gb-1tb-egypt](https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx10-i7-rtx-5070-32gb-1tb-egypt)
- **Field**: `display.touchscreen`
- **Catalog Value**: `true`
- **Corrected Value**: `false`
- **Raw Spec Evidence**: *"Touchscreen: None"*
- **Technical Rationale**: The raw specifications explicitly state 'Touchscreen: None', contradicting the extracted value of true.

### 4. Lenovo LOQ 15IRX10 83JE00XEED Gaming Laptop – Intel Core i7-13650HX, RTX 5070 8GB GDDR7, 32GB DDR5, 1TB SSD, 15.6-inch FHD IPS 144Hz, 100% sRGB, G-SYNC, Luna Grey
- **URL**: [https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx10-i7-rtx-5070-32gb-1tb-egypt](https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx10-i7-rtx-5070-32gb-1tb-egypt)
- **Field**: `audio_webcam.microphone`
- **Catalog Value**: `"2x, Array"`
- **Corrected Value**: `true`
- **Raw Spec Evidence**: *"Microphone: 2x, Array"*
- **Technical Rationale**: Microphone specification should be boolean (true/false) or properly normalized rather than raw text string when present.

### 5. ASUS Vivobook 15 X1504VA-BQ857W Laptop – Intel Core 7 150U, Intel Graphics, 8GB DDR5, 512GB PCIe 4.0 SSD, 15.6-Inch FHD IPS, Windows 11 Home
- **URL**: [https://www.compumarts.com/collections/laptop/products/asus-vivobook-15-x1504va-bq857w-core-7-150u-512gb-laptop-egypt](https://www.compumarts.com/collections/laptop/products/asus-vivobook-15-x1504va-bq857w-core-7-150u-512gb-laptop-egypt)
- **Field**: `audio_webcam.microphone`
- **Catalog Value**: `"SonicMaster Built-in speaker Built-in array microphone with Cortana voice-recognition support"`
- **Corrected Value**: `true`
- **Raw Spec Evidence**: *"Built-in array microphone with Cortana voice-recognition support"*
- **Technical Rationale**: Microphone field was contaminated with speaker and audio text description. It should be a boolean indicating presence.

### 6. ASUS Vivobook 15 X1504VA-BQ857W Laptop – Intel Core 7 150U, Intel Graphics, 8GB DDR5, 512GB PCIe 4.0 SSD, 15.6-Inch FHD IPS, Windows 11 Home
- **URL**: [https://www.compumarts.com/collections/laptop/products/asus-vivobook-15-x1504va-bq857w-core-7-150u-512gb-laptop-egypt](https://www.compumarts.com/collections/laptop/products/asus-vivobook-15-x1504va-bq857w-core-7-150u-512gb-laptop-egypt)
- **Field**: `audio_webcam.speaker_count`
- **Catalog Value**: `1`
- **Corrected Value**: `null`
- **Raw Spec Evidence**: *"Audio: SonicMaster Built-in speaker Built-in array microphone with Cortana voice-recognition support"*
- **Technical Rationale**: The raw specifications mention SonicMaster Built-in speaker without giving an explicit speaker count number, so speaker_count should be null.

### 7. ASUS Zenbook A14 UX3407QA-QD155W Laptop 14-inch WUXGA OLED Snapdragon X X1 26 100 16GB LPDDR5X 512GB PCIe 4.0 SSD Windows 11 Home Iceland Gray
- **URL**: [https://www.compumarts.com/collections/laptop/products/asus-zenbook-a14-ux3407qa-qd155w-laptop-snapdragon-x-16gb-512gb-egypt](https://www.compumarts.com/collections/laptop/products/asus-zenbook-a14-ux3407qa-qd155w-laptop-snapdragon-x-16gb-512gb-egypt)
- **Field**: `audio_webcam.microphone`
- **Catalog Value**: `"Smart Amp Technology; Built-in speaker; Built-in array microphone"`
- **Corrected Value**: `true`
- **Raw Spec Evidence**: *"Built-in array microphone"*
- **Technical Rationale**: Microphone field was contaminated with speaker and technology descriptions. It should simply be a boolean true.

### 8. ASUS Vivobook 15 X1504VA-BQ4615W Laptop Intel Core 5 120U 8GB DDR5 512GB PCIe 4.0 SSD 15.6" FHD IPS WiFi 6 Fingerprint Windows 11 Cool Silver - 90NB13Y2-M02EL0
- **URL**: [https://www.compumarts.com/collections/laptop/products/asus-vivobook-15-core5-8gb-512gb-90nb13y2](https://www.compumarts.com/collections/laptop/products/asus-vivobook-15-core5-8gb-512gb-90nb13y2)
- **Field**: `memory.slot_count`
- **Catalog Value**: `1`
- **Corrected Value**: `0`
- **Raw Spec Evidence**: *"On board memory: 8GB DDR5 on board"*
- **Technical Rationale**: The memory slot count must be 0 because the RAM is 8GB on board and there are no extra SO-DIMM expansion slots populated for user upgrade in the memory specs (only a disclaimer mentions SO-DIMM).

### 9. ASUS Vivobook 15 X1504VA-BQ4615W Laptop Intel Core 5 120U 8GB DDR5 512GB PCIe 4.0 SSD 15.6" FHD IPS WiFi 6 Fingerprint Windows 11 Cool Silver - 90NB13Y2-M02EL0
- **URL**: [https://www.compumarts.com/collections/laptop/products/asus-vivobook-15-core5-8gb-512gb-90nb13y2](https://www.compumarts.com/collections/laptop/products/asus-vivobook-15-core5-8gb-512gb-90nb13y2)
- **Field**: `memory.is_soldered`
- **Catalog Value**: `true`
- **Corrected Value**: `true`
- **Raw Spec Evidence**: *"On board memory: 8GB DDR5 on board"*
- **Technical Rationale**: Correctly marked as soldered

### 10. ASUS Zenbook 14 OLED UM3406GA-QL157W AMD Ryzen AI 7 445 16GB LPDDR5X 512GB SSD 14" WUXGA Touch OLED Stylus WiFi 6E Windows 11 Jade Black
- **URL**: [https://www.compumarts.com/collections/laptop/products/asus-zenbook-14-ryzen-ai7-16gb-512gb-oled-90nb17r2](https://www.compumarts.com/collections/laptop/products/asus-zenbook-14-ryzen-ai7-16gb-512gb-oled-90nb17r2)
- **Field**: `display.hdr`
- **Catalog Value**: `"HDR"`
- **Corrected Value**: `"VESA CERTIFIED Display HDR True Black 500"`
- **Raw Spec Evidence**: *"VESA CERTIFIED Display HDR: VESA CERTIFIED Display HDR True Black 500"*
- **Technical Rationale**: The exact HDR certification standard is VESA CERTIFIED Display HDR True Black 500.

### 11. ASUS TUF Gaming F16 FX608JMR-RV057W Laptop Intel Core i7-14650HX NVIDIA GeForce RTX 5060 16GB DDR5 512GB SSD 165Hz 16 Inch WUXGA Windows 11 Home
- **URL**: [https://www.compumarts.com/collections/laptop/products/asus-tuf-gaming-f16-fx608jmr-i7-rtx-5060-16gb-512gb-165hz-egypt](https://www.compumarts.com/collections/laptop/products/asus-tuf-gaming-f16-fx608jmr-i7-rtx-5060-16gb-512gb-165hz-egypt)
- **Field**: `identity.warranty`
- **Catalog Value**: `"9.7"`
- **Corrected Value**: `null`
- **Raw Spec Evidence**: *"Repairability Index: 9.7"*
- **Technical Rationale**: The value '9.7' refers to the Repairability Index, not the warranty. The warranty field should be null if not specified.

### 12. ASUS TUF Gaming F16 FX608JMR-RV057W Laptop Intel Core i7-14650HX NVIDIA GeForce RTX 5060 16GB DDR5 512GB SSD 165Hz 16 Inch WUXGA Windows 11 Home
- **URL**: [https://www.compumarts.com/collections/laptop/products/asus-tuf-gaming-f16-fx608jmr-i7-rtx-5060-16gb-512gb-165hz-egypt](https://www.compumarts.com/collections/laptop/products/asus-tuf-gaming-f16-fx608jmr-i7-rtx-5060-16gb-512gb-165hz-egypt)
- **Field**: `storage.max_supported_gb`
- **Catalog Value**: `1024`
- **Corrected Value**: `2048`
- **Raw Spec Evidence**: *"Supported SSD: 512GB / 1TB / 2TB"*
- **Technical Rationale**: Supported SSD options include up to 2TB, meaning max supported storage is at least 2048GB.

### 13. Gigabyte AORUS MASTER 18 BZH Gaming Laptop – Core Ultra 9 275HX | RTX 5090 24GB | 64GB RAM | 2TB SSD | 18” 240Hz Mini-LED
- **URL**: [https://www.compumarts.com/collections/laptop/products/products-gigabyte-aorus-master-18-bzh-gaming-laptop-egypt](https://www.compumarts.com/collections/laptop/products/products-gigabyte-aorus-master-18-bzh-gaming-laptop-egypt)
- **Field**: `display.size_inches`
- **Catalog Value**: `16.0`
- **Corrected Value**: `18.0`
- **Raw Spec Evidence**: *"Gigabyte AORUS MASTER 18 BZH Gaming Laptop – Core Ultra 9 275HX | RTX 5090 24GB | 64GB RAM | 2TB SSD | 18” 240Hz Mini-LED"*
- **Technical Rationale**: The product title and model family clearly specify an 18-inch display, overriding the conflicting 16-inch screen size entry in the raw spec table.

### 14. Gigabyte AORUS MASTER 18 BZH Gaming Laptop – Core Ultra 9 275HX | RTX 5090 24GB | 64GB RAM | 2TB SSD | 18” 240Hz Mini-LED
- **URL**: [https://www.compumarts.com/collections/laptop/products/products-gigabyte-aorus-master-18-bzh-gaming-laptop-egypt](https://www.compumarts.com/collections/laptop/products/products-gigabyte-aorus-master-18-bzh-gaming-laptop-egypt)
- **Field**: `display.panel_type`
- **Catalog Value**: `"OLED"`
- **Corrected Value**: `"Mini-LED"`
- **Raw Spec Evidence**: *"18” 240Hz Mini-LED"*
- **Technical Rationale**: The title specifies a Mini-LED panel, which conflicts with the erroneous OLED panel type listed in the specs table.

### 15. MSI Thin 15 B13VE Gaming Laptop Intel Core i7-13620H RTX 4050 16GB RAM 1TB SSD 15.6 FHD COMPUMARTS WARRANTY
- **URL**: [https://www.compumarts.com/collections/laptop/products/msi-thin-15-b13ve-gaming-laptop-i7-13620h-rtx-4050-16gb-1tb-144hz-cosmos-grey-egypt](https://www.compumarts.com/collections/laptop/products/msi-thin-15-b13ve-gaming-laptop-i7-13620h-rtx-4050-16gb-1tb-144hz-cosmos-grey-egypt)
- **Field**: `storage.slot_count`
- **Catalog Value**: `1`
- **Corrected Value**: `2`
- **Raw Spec Evidence**: *"Storage: 1TB NVMe PCIe Gen4 SSD (plus 1x 2.5" SATA HDD/SSD expansion slot)"*
- **Technical Rationale**: The raw specifications explicitly state 1 NVMe M.2 SSD plus an extra 2.5" SATA expansion slot, which totals 2 physical storage slots.

### 16. MSI Vector 17 HX AI A2XWJG Intel Core Ultra 9 275HX RTX 5090 32GB RAM 1TB SSD 17" QHD+ 240Hz Gaming Laptop
- **URL**: [https://www.compumarts.com/collections/laptop/products/products-msi-vector-17-hx-ai-a2xwjg-rtx-5090-24gb](https://www.compumarts.com/collections/laptop/products/products-msi-vector-17-hx-ai-a2xwjg-rtx-5090-24gb)
- **Field**: `storage.slot_count`
- **Catalog Value**: `1`
- **Corrected Value**: `2`
- **Raw Spec Evidence**: *"Storage Expansion: 1x M.2 PCIe Gen5 + 1x M.2 PCIe Gen4"*
- **Technical Rationale**: Raw specs explicitly state support for two M.2 slots (1x PCIe Gen5 + 1x PCIe Gen4), meaning total slot count is 2.

### 17. Lenovo LOQ 15IRX9 Gaming (Intel Core i7-13650HX, 16GB RAM, 512GB SSD, RTX 3050 6GB,15.6" FHD 144Hz ENG/ARB DOS, Grey | 83DV000EAX
- **URL**: [https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx9-gaming-intel-core-i7-13650hx-16gb-ram-512gb-ssd-rtx-3050-6gb-15-6-fhd-144hz-eng-arb-dos-grey-83dv000eax](https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx9-gaming-intel-core-i7-13650hx-16gb-ram-512gb-ssd-rtx-3050-6gb-15-6-fhd-144hz-eng-arb-dos-grey-83dv000eax)
- **Field**: `identity.color`
- **Catalog Value**: `"& Warranty Luna Grey, 1-year carry-in service"`
- **Corrected Value**: `"Luna Grey"`
- **Raw Spec Evidence**: *"Color: & Warranty Luna Grey, 1-year carry-in service"*
- **Technical Rationale**: The color field was contaminated with warranty and formatting text. The correct laptop exterior color is Luna Grey.

### 18. Lenovo LOQ 15IRX9 Gaming (Intel Core i7-13650HX, 16GB RAM, 512GB SSD, RTX 3050 6GB,15.6" FHD 144Hz ENG/ARB DOS, Grey | 83DV000EAX
- **URL**: [https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx9-gaming-intel-core-i7-13650hx-16gb-ram-512gb-ssd-rtx-3050-6gb-15-6-fhd-144hz-eng-arb-dos-grey-83dv000eax](https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx9-gaming-intel-core-i7-13650hx-16gb-ram-512gb-ssd-rtx-3050-6gb-15-6-fhd-144hz-eng-arb-dos-grey-83dv000eax)
- **Field**: `storage.slot_count`
- **Catalog Value**: `1`
- **Corrected Value**: `2`
- **Raw Spec Evidence**: *"Storage: 512GB M.2 PCIe 4.0 x4 NVMe SSD, with an extra M.2 slot"*
- **Technical Rationale**: Raw specs state there is an installed SSD plus an extra M.2 slot, bringing the total physical slot count to 2.

