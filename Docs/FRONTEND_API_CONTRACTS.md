# Frontend API Contracts & Integration Guide

This document defines the complete API contracts, data types, and UI/UX integration rules for developing the **Laptop Recommender** frontend application (Next.js / React / Vue / Mobile).

---

## 1. Network & Gateway Architecture

All frontend requests route through **Nginx** (acting as the unified API Gateway & Reverse Proxy):

* **Gateway Base URL**: `http://localhost/api/v1` (or your staging/production domain)
* **Direct Backend (Dev Only)**: `http://localhost:8000/api/v1`
* **Interactive Swagger UI**: `http://localhost/docs`
* **OpenAPI Specification**: `http://localhost/openapi.json`
* **Health Check**: `http://localhost/health`

### Key Gateway Features
* **CORS**: Enabled for all `localhost` origins and production web domains.
* **Rate Limiting**: `20 requests/second` per client IP with a burst of up to `30`.
* **Gzip Compression**: Automatically active on all JSON payloads $> 1\text{ KB}$.
* **Timeout**: 60-second read timeout for complex vector similarity searches.

---

## 2. API Endpoints Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/recommendations` | **Core Recommender**: 10-criteria TOPSIS + ChromaDB dual-impact review matching |
| `GET` | `/api/v1/laptops` | **Catalog Search & Browse**: Paginated list with price, brand, and stock filters |
| `GET` | `/api/v1/laptops/{id}` | **Product Details**: Complete 35+ specifications, store offers, metrics, and reviews |
| `GET` | `/health` | **System Health**: Health status of PostgreSQL, ChromaDB, and Redis cache |

---

## 3. Detailed Endpoint Contracts

### 3.1 Recommendation Engine (`POST /api/v1/recommendations`)

Executes Vector-Normalized TOPSIS ranking across candidate laptops, integrating ChromaDB dual-vector semantic review matching, Arabic/English intent parsing, and smart budget flooring.

#### Request Headers
```http
Content-Type: application/json
Accept: application/json
```

#### Request Payload
```json
{
  "budget_egp": 45000,
  "min_budget_egp": 30000,
  "persona": "gaming",
  "personas": ["gaming"],
  "user_text_prompt": "عايز لاب يشغل Cyberpunk على Ultra وتبريده ممتاز",
  "min_ram_gb": 16,
  "min_storage_gb": 512,
  "require_dgpu": true,
  "brand_filter": ["Lenovo", "ASUS"],
  "top_k": 5
}
```

#### Request Field Specifications

| Field | Type | Required | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `budget_egp` | `number` | **Yes** | - | Maximum budget in Egyptian Pounds (EGP). |
| `min_budget_egp` | `number` | No | `null` | Optional minimum budget floor. |
| `persona` | `string` | No | `"balanced"` | Primary persona: `"gaming"`, `"software_engineering"`, `"content_creation"`, `"data_science"`, `"business_mobility"`, `"student_budget"`, `"balanced"`. |
| `personas` | `string[]` | No | `null` | Multi-persona blending (e.g., `["gaming", "software_engineering"]`). Averages weights smoothly. |
| `user_text_prompt` | `string` | No | `null` | Free-text prompt in **Arabic or English**. Dynamically boosts criteria and searches ChromaDB review embeddings. |
| `min_ram_gb` | `integer` | No | `null` | Hard constraint on minimum RAM capacity in GB. |
| `min_storage_gb` | `integer` | No | `null` | Hard constraint on minimum storage capacity in GB. |
| `require_dgpu` | `boolean` | No | `null` | `true` forces discrete GPU; `false` forces integrated GPU. |
| `brand_filter` | `string[]` | No | `null` | Whitelist of brands (case-insensitive): `["ASUS", "Lenovo", "HP", "Dell", "Apple"]`. |
| `custom_weights` | `object` | No | `null` | Advanced: direct weight overrides for any of the 10 criteria. |
| `top_k` | `integer` | No | `10` | Maximum number of ranked recommendations to return. |

#### Successful Response (`200 OK`)
```json
{
  "persona": "gaming",
  "persona_label_ar": "الألعاب الثقيلة والـ Esports",
  "persona_label_en": "Heavy Gaming & Esports",
  "status": "OK",
  "gates_relaxed_for_low_budget": false,
  "total_candidates_before_floor": 28,
  "total_candidates_after_gates_and_floor": 14,
  "applied_budget_window_egp": [27000, 45000],
  "parsed_text_prompt": {
    "extracted_filters": {
      "require_dgpu": true
    },
    "weight_boosts": {
      "community_nlp_score": 0.14,
      "gpu_score": 0.15,
      "power_therm_score": 0.20
    }
  },
  "effective_weights": {
    "cpu_score": 0.1014,
    "gpu_score": 0.3043,
    "power_therm_score": 0.2029,
    "display_score": 0.0880,
    "mobility_score": 0.0203,
    "longevity_score": 0.0338,
    "ergonomics_score": 0.0135,
    "connectivity_score": 0.0203,
    "community_nlp_score": 0.1486,
    "effective_price_egp": 0.0669
  },
  "results": [
    {
      "rank": 1,
      "canonical_id": "laptop_lenovo_loq_15arp9_83jc0001us",
      "brand": "Lenovo",
      "laptop_family": "Loq 15Arp9",
      "laptop_model": "LOQ 15ARP9",
      "title": "Lenovo LOQ 15ARP9 Ryzen 5 7235HS, RTX 3050 6GB, 12GB DDR5, 512GB SSD, 15.6 FHD 144Hz 100% sRGB",
      "thumbnail_url": "https://www.compumarts.com/cdn/shop/files/Lenovo-LOQ-15ARP9-Gaming-Laptop_01.jpg",
      "topsis_match_score": 88.42,
      "effective_price_egp": 40600,
      "cheapest_store": "compumarts",
      "cheapest_offer_url": "https://www.compumarts.com/products/lenovo-loq-15arp9",
      "available_stores": ["compumarts", "elbadr"],
      "prices_by_store": {
        "compumarts": 40600,
        "elbadr": 41999
      },
      "urls_by_store": {
        "compumarts": "https://www.compumarts.com/products/lenovo-loq-15arp9",
        "elbadr": "https://elbadrgroupeg.store/lenovo-loq-15arp9"
      },
      "offers": [
        {
          "store_key": "compumarts",
          "store_name": "Compumarts",
          "price_egp": 40600,
          "product_url": "https://www.compumarts.com/products/lenovo-loq-15arp9",
          "in_stock": true,
          "is_cheapest": true,
          "last_checked_at": "2026-11-09T04:42:29Z"
        }
      ],
      "why_recommended_ar": [
        "كارت شاشة GeForce RTX 3050 (6GB) بقدرة 95W ومعالج AMD Ryzen 5 7235HS",
        "شاشة 15.6 بوصة IPS بتردد 144Hz وتغطية ألوان 100% sRGB",
        "رام 12GB DDR5 (تقبل حتى 32GB) وتخزين 512GB (2 فتحات M.2)",
        "متاح بسعر 40,600 ج.م لدى compumarts"
      ],
      "why_recommended_en": [
        "GeForce RTX 3050 (6GB, 95W TGP) paired with AMD Ryzen 5 7235HS",
        "15.6-inch IPS 144Hz display (100% sRGB)",
        "12GB DDR5 RAM (up to 32GB) & 512GB SSD (2x M.2 slots)",
        "Available at 40,600 EGP via compumarts"
      ],
      "pros_ar": [
        "تبريد ممتاز بفتحات خلفية يطرد الحرارة بعيداً عن الشاشة واليدين ويحافظ على ثبات أداء GeForce RTX 3050 (95W)",
        "كيبورد ممتازة جداً في الكتابة والبرمجة واللعب مستوحاة من سلسلة Legion مع شاسيه MIL-STD متين",
        "شاشة بألوان 100% sRGB مع دعم G-SYNC تمنع تمزق الإطارات وتقدم ألواناً ممتازة في فئتها"
      ],
      "pros_en": [
        "Rear-exhaust dual-fan hyperchamber cooling handles 95W GeForce RTX 3050 smoothly without hot air hitting the screen or mouse hand",
        "Excellent 1.5mm key-travel keyboard feel (inherited from Legion) and MIL-STD-810H polycarbonate durability",
        "100% sRGB display with G-SYNC prevents screen tearing and offers great color accuracy for the price"
      ],
      "cons_ar": [
        "البطارية (60Wh) متوسطة وتدوم حوالي 3.5 إلى 4.5 ساعات في الاستخدام المتوسط بعيداً عن الشاحن",
        "صوت السماعات السفلية متوسط في الأماكن المفتوحة"
      ],
      "cons_en": [
        "60Wh battery drains in ~3.5-4.5 hours of mixed use when unplugged",
        "Downward-firing 2W stereo speakers have modest bass"
      ],
      "reviews_evidence_count": 9,
      "aspect_scores": {
        "thermals_score": 79.8,
        "acoustics_score": 78.2,
        "build_and_hinges_score": 78.7,
        "keyboard_and_trackpad_score": 79.8,
        "real_battery_and_reliability_score": 73.9
      },
      "topsis_inputs": {
        "cpu_score": 60.18,
        "gpu_score": 39.11,
        "power_therm_score": 89.0,
        "display_score": 62.5,
        "mobility_score": 48.24,
        "longevity_score": 94.5,
        "ergonomics_score": 60.0,
        "connectivity_score": 71.0,
        "community_nlp_score": 83.71,
        "effective_price_egp": 40600.0,
        "value_score": 98.35,
        "in_stock_active": true
      }
    }
  ]
}
```

---

### 3.2 Catalog Search & Browse (`GET /api/v1/laptops`)

Returns a paginated list of catalog laptops with review intelligence summaries, ideal for category browsing, filtering sidebars, and grid/list views.

#### Query Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :---: | :--- |
| `min_price` | `number` | - | Filter laptops $\ge$ this price in EGP. |
| `max_price` | `number` | - | Filter laptops $\le$ this price in EGP. |
| `brand` | `string` | - | Filter by brand name (e.g. `Lenovo`, `ASUS`, `HP`, `Apple`). |
| `in_stock_only` | `boolean` | `true` | Only return laptops with at least one in-stock store offer. |
| `offset` | `integer` | `0` | Number of items to skip (pagination offset). |
| `limit` | `integer` | `20` | Items per page (max `100`). |

#### Response (`200 OK`)
```json
{
  "total": 295,
  "offset": 0,
  "limit": 20,
  "items": [
    {
      "id": "c7280a38-f07c-4814-aa5c-abe8e76bd4b0",
      "canonical_id": "laptop_lenovo_loq_15arp9_83jc0001us",
      "mpn": "83JC0001US",
      "brand": "Lenovo",
      "laptop_family": "Loq 15Arp9",
      "laptop_model": "LOQ 15ARP9",
      "title": "Lenovo LOQ 15ARP9 Ryzen 5 7235HS, RTX 3050 6GB, 12GB DDR5, 512GB SSD, 15.6 FHD 144Hz",
      "thumbnail_url": "https://www.compumarts.com/cdn/shop/files/Lenovo-LOQ-15ARP9-Gaming-Laptop_01.jpg",
      "min_price_egp": 40600.0,
      "cheapest_store": "compumarts",
      "in_stock": true,
      "stores_count": 2,
      "ram_capacity_gb": 12,
      "storage_capacity_gb": 512,
      "gpu_model": "GeForce RTX 3050 6GB",
      "cpu_model": "Ryzen 5 7235HS",
      "display_size_inches": 15.6,
      "community_nlp_score": 83.71,
      "value_score": 98.35,
      "has_reviews": true,
      "reviews_evidence_count": 9,
      "pros_ar": ["تبريد ممتاز بفتحات خلفية...", "كيبورد ممتازة...", "شاشة بألوان 100% sRGB..."],
      "pros_en": ["Rear-exhaust dual-fan hyperchamber cooling...", "Excellent keyboard feel...", "100% sRGB display..."],
      "cons_ar": ["البطارية متوسطة...", "صوت السماعات متوسط..."],
      "cons_en": ["60Wh battery drains in ~3.5-4.5 hours...", "Modest bass speakers..."]
    }
  ]
}
```

---

### 3.3 Full Product Specifications (`GET /api/v1/laptops/{id}`)

Fetches all 35+ verified hardware dimensions, price spread across Egyptian retailers, 11 benchmark metrics, 5 review aspect scores, and bilingual bullet points. `{id}` accepts **UUID**, **canonical_id** (`laptop_asus_tuf_gaming_90nr0jf7m00tp0`), or **MPN** (`FA506NCG-HN857W`).

#### Response (`200 OK`)
Includes full hardware sections:
* `cpu`: cores, threads, clock speeds, cache, NPU TOPS, microarchitecture.
* `gpu`: model, VRAM capacity/type, TGP/TDP in watts, integrated vs discrete.
* `memory`: RAM capacity, technology (DDR4/DDR5/LPDDR5), slots, upgradeability.
* `storage`: primary SSD capacity, interface (PCIe 4.0), M.2 slot count.
* `display`: diagonal size, resolution, refresh rate (Hz), color gamut coverage, brightness nits.
* `power_battery`: battery Wh, cell count, charger wattage, USB-C Power Delivery.
* `physical`: weight in kg, dimensions in mm.
* `metrics`: 11 computed scores and silicon/display/mobility/upgradeability tiers.
* `aspect_scores`: 5 community aspect scores.
* `offers`: live retailer prices, direct product URLs, and stock status.

---

## 4. Frontend UI/UX Business Rules

### 4.1 Handling the 3 Recommendation Statuses

The `status` field in `RecommendationResponse` dictates the top-level user messaging:

1. **`status: "OK"`**:
   * Normal, ideal state.
   * Render normal results list with green match score badges (e.g. `88% Match`).

2. **`status: "GATES_RELAXED_FOR_LOW_BUDGET"`**:
   * Occurs when the budget is tight, so secondary filters (e.g. 16GB RAM) were relaxed to 8GB to find candidates.
   * **UI Action**: Display a blue/info notice at the top of the results:
     > *"We relaxed some strict secondary requirements to find the best value options within your budget."*

3. **`status: "BUDGET_TOO_LOW_FOR_CATEGORY"`**:
   * Occurs when the user budget is lower than any active laptop in that category (e.g., `12,000 EGP` for `gaming` or AAA Cyberpunk, where minimum price is ~40,600 EGP).
   * The API still returns the 3 closest, most affordable *valid* alternatives.
   * **UI Action**: Display a prominent amber banner:
     > *"Your budget of {budget_egp} EGP is below the entry price for {persona_label} in Egypt. Here are the 3 most affordable dedicated alternatives starting at {results[0].effective_price_egp} EGP."*

---

### 4.2 Rendering Bilingual Pros & Cons (1:1 Alignment)

* **Arabic UI Mode**: Render `pros_ar` (green checkmarks) and `cons_ar` (red warning icons).
* **English UI Mode**: Render `pros_en` and `cons_en`.
* **Guarantee**: `pros_en` and `pros_ar` always have identical item counts. `cons_en` and `cons_ar` always have identical item counts. No placeholder bullets or missing keys.

---

### 4.3 Visualizing the 5 Review Aspect Scores

Each laptop includes `aspect_scores` (0.0 to 100.0) generated from community consensus. Render these as either a **Radar Chart** or **5 Horizontal Progress Bars**:

| Aspect Key | Arabic Label | English Label | Description |
| :--- | :--- | :--- | :--- |
| `thermals_score` | التبريد والحرارة | Cooling & Thermals | Temperatures under stress tests |
| `acoustics_score` | هدوء المراوح | Quietness / Fan Acoustics | Fan noise on idle vs heavy load |
| `build_and_hinges_score` | جودة الشاسيه والمفصلات | Build & Hinge Durability | Flex, chassis materials, screen hinge strength |
| `keyboard_and_trackpad_score` | الكيبورد والتراك باد | Keyboard & Trackpad Feel | Key travel (mm), typing stability, tracking |
| `real_battery_and_reliability_score` | البطارية والاعتمادية | Real Battery & Reliability | Real-world battery drain and failure reports |
