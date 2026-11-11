/**
 * TypeScript API Contracts for Laptop Recommender Frontend
 */

export type PersonaType =
  | 'gaming'
  | 'ai_and_game_dev'
  | 'programming'
  | 'content_creation'
  | 'student_and_office'
  | 'business_and_mobility'
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

/**
 * Optional 0-100 metric gates shared by catalog browsing and recommendations.
 * Aspect scores come from real-world review NLP; hardware scores from benchmarks.
 */
export interface MetricFilterParams {
  min_acoustics_score?: number;               // Real-world fan noise & quietness
  min_thermals_score?: number;                // Real-world cooling under stress
  min_battery_score?: number;                 // Real-world battery life & reliability
  min_build_score?: number;                   // Chassis & hinge durability
  min_keyboard_score?: number;                // Keyboard & typing comfort
  min_cpu_score?: number;                     // Hardware CPU compute
  min_gpu_score?: number;                     // Hardware GPU 3D graphics
  min_display_score?: number;                 // Display quality & colors
  min_value_score?: number;                   // Value for money
}

export type MetricFilterKey = keyof MetricFilterParams

export interface RecommendationRequest extends MetricFilterParams {
  budget_egp: number;                         // Maximum budget in EGP (Required)
  min_budget_egp?: number;                    // Optional minimum budget floor
  persona?: PersonaType;                      // Default: 'balanced'
  personas?: PersonaType[];                   // Multi-persona blending
  user_text_prompt?: string;                  // Arabic/English free-text
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

export interface CatalogQueryParams extends MetricFilterParams {
  search?: string;
  min_price?: number;
  max_price?: number;
  brand?: string;
  in_stock_only?: boolean;
  cursor?: string;
  direction?: 'next' | 'prev';
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
  metric_scores?: Record<string, number>;
}

export interface PageInfo {
  has_next_page: boolean;
  has_previous_page: boolean;
  start_cursor: string | null;
  end_cursor: string | null;
}

export interface CatalogListResponse {
  total: number;
  limit: number;
  page_info: PageInfo;
  items: CatalogListItem[];
}

export interface CpuSpecDetail {
  manufacturer: string;
  line?: string;
  model: string;
  series?: string;
  full_name?: string;
  cores: number;
  threads: number;
  clock_base_ghz?: number;
  clock_boost_ghz?: number;
  cache_mb?: number;
  base_power_w?: number;
  npu_tops?: number;
  microarchitecture?: string;
}

export interface GpuSpecDetail {
  manufacturer: string;
  model: string;
  variant?: string;
  vram_gb?: number;
  vram_type?: string;
  tdp_w?: number;
  integrated: boolean;
  ai_tops?: number;
  igpu_model?: string;
}

export interface MemorySpecDetail {
  capacity_gb: number;
  memory_type: string;
  speed_mhz?: number;
  slot_count?: number;
  max_supported_gb?: number;
  is_soldered: boolean;
  channels?: string;
}

export interface StorageSpecDetail {
  capacity_gb: number;
  storage_type: string;
  interface?: string;
  slot_count?: number;
}

export interface DisplaySpecDetail {
  size_inches: number;
  resolution: string;
  width: number;
  height: number;
  panel_type?: string;
  refresh_rate_hz: number;
  aspect_ratio?: string;
  brightness_nits?: number;
  color_gamut?: string;
  touchscreen: boolean;
  hdr?: boolean;
}

export interface PowerBatterySpecDetail {
  battery_capacity_wh?: number;
  battery_cells?: number;
  power_adapter_w?: number;
  fast_charging?: boolean;
  usb_c_pd_charging: boolean;
}

export interface PhysicalSpecDetail {
  weight_kg?: number;
  width_mm?: number;
  depth_mm?: number;
  height_mm?: number;
}

export interface BuildSecuritySpecDetail {
  has_backlit_keyboard: boolean;
  keyboard_backlight_type?: string;
  has_fingerprint: boolean;
  has_copilot_key: boolean;
  security_features: string[];
}

export interface AudioWebcamSpecDetail {
  speaker_count: number;
  audio_system?: string;
  webcam_resolution?: string;
  has_ir_camera: boolean;
  has_privacy_shutter: boolean;
}

export interface ConnectivityOsSpecDetail {
  wifi?: string;
  bluetooth?: string;
  has_ethernet: boolean;
  ethernet_speed?: string;
  has_card_reader: boolean;
  operating_system?: string;
  ports: string[];
}

export interface HardwareMetricsDetail {
  cpu_score: number;
  gpu_score: number;
  silicon_index?: number;
  power_therm_score: number;
  display_score: number;
  mobility_score: number;
  longevity_score: number;
  ergonomics_score: number;
  connectivity_score: number;
  community_nlp_score?: number;
  thermals_score?: number;
  acoustics_score?: number;
  build_and_hinges_score?: number;
  keyboard_and_trackpad_score?: number;
  real_battery_and_reliability_score?: number;
  value_score: number;
  effective_price_egp: number;
  estimated_battery_hours?: number;
  silicon_tier?: string;
  display_tier?: string;
  portability_tier?: string;
  upgradeability_tier?: string;
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
  base_color?: string;
  color?: string;
  form_factor: string;
  market_positioning?: string;
  release_year?: number;
  warranty?: string;
  warranty_years?: number;

  min_price_egp: number;
  max_price_egp?: number;
  previous_min_price_egp?: number;
  cheapest_store: string;
  cheapest_offer_url?: string;
  price_spread_egp?: number;
  stores_count: number;
  in_stock: boolean;
  available_stores: string[];
  prices_by_store: Record<string, number>;
  urls_by_store: Record<string, string>;
  offers: StoreOffer[];

  // 35+ Structured Hardware Dimensions
  cpu: CpuSpecDetail;
  gpu: GpuSpecDetail;
  memory: MemorySpecDetail;
  storage: StorageSpecDetail;
  display: DisplaySpecDetail;
  power_battery: PowerBatterySpecDetail;
  physical: PhysicalSpecDetail;
  build_security: BuildSecuritySpecDetail;
  audio_webcam: AudioWebcamSpecDetail;
  connectivity_os: ConnectivityOsSpecDetail;

  metrics?: HardwareMetricsDetail;

  // Community Review Intelligence & Explainability
  reviews_evidence_count: number;
  pros_en: string[];
  pros_ar: string[];
  cons_en: string[];
  cons_ar: string[];
  why_recommended_ar: string[];
  why_recommended_en: string[];
}

// =============================================================================
// Multi-Store Price History Telemetry
// =============================================================================

export interface PriceHistoryPoint {
  recorded_at: string;
  price_egp: number;
  in_stock: boolean;
  is_live_edge: boolean;
}

export interface StorePriceSeries {
  offer_id: string;
  store_key: string;
  store_name: string;
  product_url: string;
  current_price_egp: number;
  in_stock: boolean;
  is_cheapest: boolean;
  min_price_egp: number;
  max_price_egp: number;
  price_change_egp: number;
  price_change_pct: number;
  points: PriceHistoryPoint[];
}

export interface LaptopPriceHistoryResponse {
  laptop_id: string;
  canonical_id: string;
  currency: string;
  days_window: number | null;
  lowest_ever_price_egp: number;
  highest_ever_price_egp: number;
  lowest_ever_store: string;
  current_best_price_egp: number;
  series: StorePriceSeries[];
}
