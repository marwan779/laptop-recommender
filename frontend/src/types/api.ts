/**
 * TypeScript API Contracts for Laptop Recommender Frontend
 */

export type PersonaType =
  | 'gaming'
  | 'software_engineering'
  | 'content_creation'
  | 'data_science'
  | 'business_mobility'
  | 'student_budget'
  | 'balanced';

export type RecommendationStatus =
  | 'OK'                              // Ideal candidates found within budget
  | 'GATES_RELAXED_FOR_LOW_BUDGET'     // Strict hardware gates relaxed to find budget matches
  | 'BUDGET_TOO_LOW_FOR_CATEGORY';     // Budget is below category entry price; returning closest alternatives

export interface ReviewAspectScores {
  thermals_score: number;                     // 0.0 - 100.0 (Cooling under stress)
  acoustics_score: number;                    // 0.0 - 100.0 (Fan noise)
  build_and_hinges_score: number;             // 0.0 - 100.0 (Chassis flex & hinge durability)
  keyboard_and_trackpad_score: number;        // 0.0 - 100.0 (Key travel & trackpad precision)
  real_battery_and_reliability_score: number; // 0.0 - 100.0 (Real battery life & longevity)
}

export interface TopsisInputs {
  cpu_score: number;
  gpu_score: number;
  power_therm_score: number;
  display_score: number;
  mobility_score: number;
  longevity_score: number;
  ergonomics_score: number;
  connectivity_score: number;
  community_nlp_score: number;
  effective_price_egp: number;
  value_score: number;
  in_stock_active: boolean;
}

export interface StoreOffer {
  store_key: string;             // 'compumarts' | 'elbadr' | 'sigma' | 'btech'
  store_name: string;            // 'Compumarts' | 'El Badr Group'
  price_egp: number;             // Price in Egyptian Pounds
  product_url: string;           // Direct store PDP link
  in_stock: boolean;             // Live availability
  is_cheapest: boolean;          // True if this is the lowest price among stores
  last_checked_at?: string;      // ISO datetime
}

export interface RecommendationRequest {
  budget_egp: number;                         // Maximum budget in EGP (Required)
  min_budget_egp?: number;                    // Optional minimum budget floor
  persona?: PersonaType;                      // Default: 'balanced'
  personas?: PersonaType[];                   // Multi-persona blending
  user_text_prompt?: string;                  // Arabic/English free-text: "عايز لاب يشغل Cyberpunk على Ultra"
  min_ram_gb?: number;                        // e.g. 16
  min_storage_gb?: number;                    // e.g. 512
  require_dgpu?: boolean;                     // true = forces discrete GPU
  brand_filter?: string[];                    // ['Lenovo', 'ASUS', 'HP', 'Dell', 'Apple']
  custom_weights?: Record<string, number>;    // Direct weight overrides for any of the 10 criteria
  top_k?: number;                             // Default: 10
}

export interface RankedLaptop {
  rank: number;
  canonical_id: string;
  brand: string;
  laptop_family: string;
  laptop_model: string;
  title: string;
  thumbnail_url: string;
  topsis_match_score: number;                 // 0.0 - 100.0 Relative Closeness
  effective_price_egp: number;
  cheapest_store: string;
  cheapest_offer_url: string;
  available_stores: string[];
  prices_by_store: Record<string, number>;
  urls_by_store: Record<string, string>;
  offers: StoreOffer[];

  // Explainability (Bilingual Why Recommended)
  why_recommended_ar: string[];
  why_recommended_en: string[];

  // 1:1 Aligned Community Review Intelligence
  pros_ar: string[];
  pros_en: string[];
  cons_ar: string[];
  cons_en: string[];
  reviews_evidence_count: number;
  aspect_scores: ReviewAspectScores;

  // Raw 10-Criteria Scores
  topsis_inputs: TopsisInputs;
}

export interface RecommendationResponse {
  persona: PersonaType;
  persona_label_ar: string;
  persona_label_en: string;
  status: RecommendationStatus;
  gates_relaxed_for_low_budget: boolean;
  total_candidates_before_floor: number;
  total_candidates_after_gates_and_floor: number;
  applied_budget_window_egp: [number, number];
  parsed_text_prompt: {
    extracted_filters: Record<string, any>;
    weight_boosts: Record<string, number>;
  };
  effective_weights: Record<string, number>;
  results: RankedLaptop[];
}

export interface CatalogQueryParams {
  min_price?: number;
  max_price?: number;
  brand?: string;
  in_stock_only?: boolean;
  offset?: number;
  limit?: number;
}

export interface CatalogListItem {
  id: string;
  canonical_id: string;
  mpn?: string;
  brand: string;
  laptop_family?: string;
  laptop_model: string;
  title: string;
  thumbnail_url: string;
  min_price_egp: number;
  cheapest_store: string;
  in_stock: boolean;
  stores_count: number;
  ram_capacity_gb: number;
  storage_capacity_gb: number;
  gpu_model: string;
  cpu_model: string;
  display_size_inches: number;
  community_nlp_score: number;
  value_score: number;
  has_reviews: boolean;
  reviews_evidence_count: number;
  pros_ar: string[];
  pros_en: string[];
  cons_ar: string[];
  cons_en: string[];
}

export interface CatalogListResponse {
  total: number;
  offset: number;
  limit: number;
  items: CatalogListItem[];
}

export interface FullLaptopDetailResponse {
  id: string;
  canonical_id: string;
  mpn?: string;
  brand: string;
  laptop_family?: string;
  laptop_model: string;
  title: string;
  thumbnail_url: string;
  form_factor: string;
  min_price_egp: number;
  max_price_egp: number;
  cheapest_store: string;
  cheapest_offer_url?: string;
  available_stores: string[];
  prices_by_store: Record<string, number>;
  urls_by_store: Record<string, string>;
  offers: StoreOffer[];

  cpu: {
    manufacturer?: string;
    line?: string;
    model?: string;
    series?: string;
    full_name: string;
    cores: number;
    threads: number;
    clock_base_ghz?: number;
    clock_boost_ghz?: number;
  };
  gpu: {
    manufacturer: string;
    model: string;
    vram_gb?: number;
    tdp_w?: number;
    integrated: boolean;
  };
  memory: {
    capacity_gb: number;
    memory_type: string;
    speed_mhz?: number;
    slot_count?: number;
    is_soldered: boolean;
  };
  storage: {
    capacity_gb: number;
    storage_type: string;
    slot_count?: number;
  };
  display: {
    size_inches: number;
    resolution: string;
    panel_type?: string;
    refresh_rate_hz: number;
    touchscreen: boolean;
  };
  power_battery: {
    battery_capacity_wh?: number;
    power_adapter_w?: number;
    usb_c_pd_charging: boolean;
  };
  physical: {
    weight_kg?: number;
  };

  reviews_evidence_count: number;
  pros_en: string[];
  pros_ar: string[];
  cons_en: string[];
  cons_ar: string[];
  why_recommended_ar: string[];
  why_recommended_en: string[];
}
