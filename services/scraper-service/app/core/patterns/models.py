from collections.abc import Iterator
from typing import Any
from pydantic import BaseModel, Field


class StorePatternConfig(BaseModel):
    """Configuration profile defining DOM selectors and parsing rules for a store or brand."""

    store_key: str
    name: str

    # Containers where product specifications / description reside
    container_selectors: list[str] = Field(default_factory=list)

    # Selector for product stats list items (MPN, Model code, Stock status)
    stats_selector: str | None = None

    # Delimiters used to separate keys from values in text lines or list items
    delimiters: list[str] = Field(default_factory=lambda: [":", "—", "-"])

    # Whether to skip blocks that only contain an image without text
    skip_empty_image_blocks: bool = True

    # Minimum text character length for a block to be considered valid spec content
    min_block_text_length: int = 25

    # Selectors for promotional flyer images / screenshots
    flyer_image_selectors: list[str] = Field(
        default_factory=lambda: [
            ".product_blocks-default img",
            ".product-blocks-default img",
            ".product-blocks img",
            ".product_extra img",
            "#tab-description img",
            ".product-description img",
        ]
    )


class SpecExtractionResult(BaseModel):
    """Result of extracting specs and OCR-readiness metadata from a PDP."""

    specs: dict[str, str] = Field(default_factory=dict)
    raw_description: str | None = None
    mpn: str | None = None
    model_code: str | None = None
    price_val: float | None = None
    price_str: str | None = None

    # Spec Extraction Metadata & OCR Support
    has_text_specs: bool = True
    specs_extraction_source: str = "dom"  # "dom", "title_fallback", or "hybrid"
    specs_fallback_reason: str | None = None
    has_specs_image: bool = False
    specs_image_url: str | None = None

    def __iter__(self) -> Iterator[Any]:
        """Support legacy 6-tuple unpacking: (specs, raw_desc, mpn, model_code, price_val, price_str)."""
        return iter(
            (
                self.specs,
                self.raw_description,
                self.mpn,
                self.model_code,
                self.price_val,
                self.price_str,
            )
        )
