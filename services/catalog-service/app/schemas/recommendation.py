"""Pydantic v2 schemas for the TOPSIS recommendation endpoint."""

from datetime import datetime
from typing import Any
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from app.domain.recommender.personas import PersonaType


class RecommendationRequest(BaseModel):
    """Input payload for multi-criteria TOPSIS laptop recommendation."""

    model_config = ConfigDict(populate_by_name=True)

    budget_egp: float = Field(
        ...,
        validation_alias=AliasChoices("budget_egp", "max_budget_egp", "budget"),
        gt=0,
        description="Maximum budget in Egyptian Pounds (EGP). Required.",
        examples=[70000.0],
    )
    persona: PersonaType = Field(
        ...,
        description="Target user persona (gaming, programming, ai_and_game_dev, content_creation, student_and_office, business_and_mobility, balanced). Required.",
        examples=[PersonaType.GAMING],
    )
    personas: list[PersonaType] | None = Field(
        default=None,
        description="Optional list of personas to blend criteria weights across.",
        examples=[[PersonaType.GAMING, PersonaType.PROGRAMMING]],
    )
    min_budget_egp: float | None = Field(
        default=None,
        gt=0,
        description="Optional minimum budget floor in EGP.",
        examples=[40000.0],
    )
    user_text_prompt: str | None = Field(
        default=None,
        description="Optional free-text requirement in Arabic or English (e.g. 'عايز بطارية قوية وشاشة اوليد').",
        examples=["عايز شاشة اوليد وبطارية تعيش كتير"],
    )
    min_ram_gb: int | None = Field(
        default=None,
        ge=4,
        le=128,
        description="Minimum RAM capacity in GB.",
        examples=[16],
    )
    min_storage_gb: int | None = Field(
        default=None,
        ge=128,
        le=8192,
        description="Minimum SSD capacity in GB.",
        examples=[512],
    )
    require_dgpu: bool | None = Field(
        default=None,
        description="Explicit requirement for dedicated graphics (True) or integrated (False).",
    )
    brand_filter: list[str] | None = Field(
        default=None,
        description="Filter by specific manufacturer brands (e.g. ['ASUS', 'Lenovo', 'Dell']).",
        examples=[["ASUS", "Lenovo"]],
    )
    min_acoustics_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional minimum real-world acoustics/fan-noise score (0-100).",
    )
    min_thermals_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional minimum real-world thermals/cooling score (0-100).",
    )
    min_battery_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional minimum real-world battery/reliability score (0-100).",
    )
    min_build_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional minimum chassis build/hinge durability score (0-100).",
    )
    min_keyboard_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional minimum keyboard/trackpad score (0-100).",
    )
    min_cpu_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional minimum hardware CPU benchmark score (0-100).",
    )
    min_gpu_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional minimum hardware GPU benchmark score (0-100).",
    )
    min_display_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional minimum display quality/color score (0-100).",
    )
    min_value_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional minimum value-for-money score (0-100).",
    )
    custom_weights: dict[str, float] | None = Field(
        default=None,
        description="Manual criteria weight overrides from UI sliders.",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of top ranked recommendations to return.",
    )

    @model_validator(mode="before")
    @classmethod
    def populate_persona_if_list_provided(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "persona" not in data and "personas" in data and data["personas"]:
                data["persona"] = data["personas"][0]
        return data


class StoreOfferResponse(BaseModel):
    """Store-specific listing details and direct purchase URL."""

    store_key: str = Field(..., description="Store unique identifier (e.g. compumarts, sigma, elbadr, 2b).")
    store_name: str = Field(..., description="Store display name.")
    price_egp: float = Field(..., description="Price in EGP at this retailer.")
    product_url: str = Field(..., description="Direct purchase link to the product on the retailer's store.")
    in_stock: bool = Field(True, description="Stock availability status at this store.")
    is_cheapest: bool = Field(False, description="True if this offer is the current lowest price.")
    last_checked_at: datetime | str | None = Field(
        None,
        description="Timestamp of when the price and availability were last verified.",
    )


class RankedLaptopResponse(BaseModel):
    """Structured details of a single ranked recommendation."""

    rank: int = Field(..., description="1-based rank position.")
    canonical_id: str
    brand: str
    laptop_family: str | None = None
    laptop_model: str | None = None
    title: str
    thumbnail_url: str | None = None
    topsis_match_score: float = Field(..., description="Relative closeness match percentage (0.0 - 100.0).")
    effective_price_egp: float = Field(..., description="Best current market price in EGP.")
    cheapest_store: str = Field(..., description="Store offering the lowest price.")
    cheapest_offer_url: str | None = Field(
        None,
        description="Direct clickable link to buy the laptop from the cheapest store.",
    )
    available_stores: list[str] = Field(default_factory=list, description="Stores with active stock.")
    prices_by_store: dict[str, float] = Field(default_factory=dict, description="Price breakdown per retailer.")
    urls_by_store: dict[str, str] = Field(
        default_factory=dict, description="Map of retailer store to direct product URL."
    )
    offers: list[StoreOfferResponse] = Field(
        default_factory=list,
        description="List of all retail offers with prices, stock status, and direct URLs.",
    )
    why_recommended_ar: list[str] = Field(default_factory=list, description="Arabic explanation badges.")
    why_recommended_en: list[str] = Field(default_factory=list, description="English explanation badges.")
    pros_en: list[str] = Field(default_factory=list, description="English community review pros.")
    pros_ar: list[str] = Field(default_factory=list, description="Arabic community review pros.")
    cons_en: list[str] = Field(default_factory=list, description="English community review cons.")
    cons_ar: list[str] = Field(default_factory=list, description="Arabic community review cons.")
    reviews_evidence_count: int = Field(
        default=0,
        description="Number of community review sources analyzed for this chassis.",
    )
    aspect_scores: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "5 real-world NLP aspect scores (thermals, acoustics, build_and_hinges, "
            "keyboard_and_trackpad, real_battery_and_reliability)."
        ),
    )
    topsis_inputs: dict[str, Any] = Field(default_factory=dict, description="Raw normalized 10-criteria input scores.")


class RecommendationResponse(BaseModel):
    """Complete response payload for the recommendation endpoint."""

    persona: str = Field(..., description="Evaluated primary persona.")
    persona_label_ar: str
    persona_label_en: str
    gates_relaxed_for_low_budget: bool = Field(
        ...,
        description="True if strict implicit persona gates were relaxed due to budget constraints.",
    )
    total_candidates_before_floor: int = Field(
        ...,
        description="Total eligible in-stock laptops under max budget.",
    )
    total_candidates_after_gates_and_floor: int = Field(
        ...,
        description="Candidate count evaluated in the final TOPSIS matrix.",
    )
    applied_budget_window_egp: list[float] = Field(
        ...,
        description="Effective [min_budget, max_budget] range evaluated.",
    )
    parsed_text_prompt: dict[str, Any] = Field(
        default_factory=dict,
        description="Hardware filters and weight boosts extracted from free-text prompt.",
    )
    effective_weights: dict[str, float] = Field(
        ...,
        description="Final normalized criteria weights used in the TOPSIS run.",
    )
    results: list[RankedLaptopResponse] = Field(
        default_factory=list,
        description="Top-K ranked laptops in descending order of match score.",
    )
    status: str = Field(
        default="OK",
        description=(
            "Recommendation execution status: OK, GATES_RELAXED_FOR_LOW_BUDGET, or BUDGET_TOO_LOW_FOR_CATEGORY."
        ),
    )
