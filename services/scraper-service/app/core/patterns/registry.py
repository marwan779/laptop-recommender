from app.core.patterns.models import StorePatternConfig


class PatternRegistry:
    """Registry maintaining DOM patterns and parsing rules for stores and brands."""

    _registry: dict[str, StorePatternConfig] = {}

    @classmethod
    def register(cls, config: StorePatternConfig) -> None:
        """Register or update a store pattern configuration."""
        cls._registry[config.store_key.lower()] = config

    @classmethod
    def get(cls, store_key: str) -> StorePatternConfig:
        """Retrieve the pattern configuration for a given store.

        Returns a default fallback configuration if not registered.
        """
        key = store_key.lower()
        if key in cls._registry:
            return cls._registry[key]

        # Generic default configuration
        return StorePatternConfig(
            store_key=key,
            name=store_key.title(),
            container_selectors=[
                "#tab-specification",
                ".specifications",
                "#tab-description",
                ".product-description",
                ".product-blocks .block-content",
            ],
            delimiters=[":", "—", "-"],
            skip_empty_image_blocks=True,
            min_block_text_length=20,
        )

    @classmethod
    def list_registered(cls) -> list[str]:
        return list(cls._registry.keys())


# =============================================================================
# Registered Profiles
# =============================================================================

# El Badr Group Pattern Profile
# Derived empirically from full-catalog DOM audit of 84 laptop PDPs:
#  - Pattern 1: AI / Markdown blocks (.qwen-markdown-*)
#  - Pattern 2: Standard HTML list blocks (ul li)
#  - Pattern 3: Promo banner first trap (skip_empty_image_blocks=True)
#  - Pattern 4: Flyer-only zero-text pages (flyer_image_selectors)
ELBADR_PATTERN = StorePatternConfig(
    store_key="elbadr",
    name="El Badr Group",
    container_selectors=[
        ".product_blocks-default .block-content",
        ".product-blocks-default .block-content",
        ".product_extra .block-content",
        "#tab-specification",
        "#tab-description",
    ],
    stats_selector=".product-stats li, ul.list-unstyled li",
    delimiters=[":", "—", "-"],
    skip_empty_image_blocks=True,
    min_block_text_length=25,
    flyer_image_selectors=[
        ".product_blocks-default .block-content img",
        ".product-blocks-default .block-content img",
        ".product_extra .block-content img",
        "#tab-description img",
        ".product-description img",
    ],
)

PatternRegistry.register(ELBADR_PATTERN)


# CompuMarts Pattern Profile
# Derived empirically from full-catalog DOM audit of 126 laptop PDPs:
#  - Pattern 1: HTML Specs Tables (table tr) inside .product-description / .rte (113 laptops)
#  - Pattern 2: Empty/Placeholder descriptions with title fallback (7 laptops)
#  - Pattern 3: Marketing flyer / screenshot banner with title fallback (2 laptops)
COMPUMARTS_PATTERN = StorePatternConfig(
    store_key="compumarts",
    name="CompuMarts",
    container_selectors=[
        ".product-details__block .product-description",
        ".product-details__block .rte",
        ".pdesc-wrap",
        ".dark-desc-wrapper",
        ".product-description",
        ".rte",
        "[data-product-description]",
        "table",
    ],
    stats_selector=None,
    delimiters=[":", "—", "–", "-"],
    skip_empty_image_blocks=True,
    min_block_text_length=15,
    flyer_image_selectors=[
        ".product-description img",
        ".product__description img",
        ".rte img",
        ".product-details img",
    ],
)

PatternRegistry.register(COMPUMARTS_PATTERN)
