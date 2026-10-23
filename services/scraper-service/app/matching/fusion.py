"""Specification Fusion Engine.

Performs hierarchical, non-destructive merging of 35+ hardware fields
across multiple retailer listings to produce a unified master spec sheet.
"""

from __future__ import annotations

import copy
import re
from typing import Any


def clean_title(title: str) -> str:
    """Strip common retailer promotional noise from product titles."""
    noise_patterns = [
        r"[-–|]?\s*(?:Special\s*Offer|Best\s*Price|Sale|Promo|Deal|In\s*Stock|Free\s*Shipping).*",
        r"\(\s*Brand\s*New\s*\)",
        r"[-–|]?\s*Egypt.*$",
    ]
    cleaned = title.strip()
    for pattern in noise_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def pick_best_title(offers: list[dict[str, Any]]) -> str:
    """Select the cleanest, most descriptive title among store offers."""
    candidates = []
    for o in offers:
        raw_t = o.get("title") or ""
        c_t = clean_title(raw_t)
        if len(c_t) >= 10:
            candidates.append(c_t)

    if not candidates:
        return offers[0].get("title", "Unknown Laptop") if offers else "Unknown Laptop"

    # Prefer title with moderate length (60-90 chars) that includes model and specs
    candidates.sort(key=lambda t: (bool(re.search(r"RTX|Core|Ryzen", t)), len(t)), reverse=True)
    return candidates[0]


def is_more_specific_string(new_val: str, old_val: str) -> bool:
    """Return True if new_val is meaningfully more descriptive than old_val."""
    new_clean = new_val.strip()
    old_clean = old_val.strip()

    # If old is generic placeholder
    if old_clean.lower() in {"yes", "true", "standard", "integrated", "hd", "fhd"}:
        if len(new_clean) > len(old_clean):
            return True

    # If new has significantly more detail (e.g. "1080p FHD with Privacy Shutter" vs "FHD Webcam")
    if len(new_clean) > len(old_clean) + 4:
        # Check if old is a substring or new contains numbers/specs
        if old_clean.lower() in new_clean.lower() or any(char.isdigit() for char in new_clean):
            return True

    return False


def merge_spec_value(base_v: Any, incoming_v: Any) -> Any:
    """Merge two specification values according to precedence rules."""
    # 1. Non-null beats null/empty
    if base_v is None or base_v == "" or base_v == []:
        return copy.deepcopy(incoming_v)
    if incoming_v is None or incoming_v == "" or incoming_v == []:
        return base_v

    # 2. Recursive dictionary merge
    if isinstance(base_v, dict) and isinstance(incoming_v, dict):
        merged_dict = copy.deepcopy(base_v)
        for k, v in incoming_v.items():
            if k not in merged_dict:
                merged_dict[k] = copy.deepcopy(v)
            else:
                merged_dict[k] = merge_spec_value(merged_dict[k], v)
        return merged_dict

    # 3. List merge (e.g. ports, security features) with deduplication
    if isinstance(base_v, list) and isinstance(incoming_v, list):
        merged_list = list(base_v)
        existing_str_set = {str(x).strip().lower() for x in base_v}
        for item in incoming_v:
            norm_item = str(item).strip().lower()
            if norm_item and norm_item not in existing_str_set:
                merged_list.append(item)
                existing_str_set.add(norm_item)
        return merged_list

    # 4. String specificity comparison
    if isinstance(base_v, str) and isinstance(incoming_v, str):
        if is_more_specific_string(incoming_v, base_v):
            return incoming_v
        return base_v

    # 5. Numerical / Boolean values: keep existing validated base value
    return base_v


def merge_specifications(
    base_specs: dict[str, Any],
    incoming_specs: dict[str, Any],
) -> dict[str, Any]:
    """Merge an incoming store's specs dictionary into the canonical spec sheet."""
    result = copy.deepcopy(base_specs)
    for category, fields in incoming_specs.items():
        if category not in result or result[category] is None:
            result[category] = copy.deepcopy(fields)
        elif isinstance(fields, dict) and isinstance(result[category], dict):
            for field_name, field_val in fields.items():
                curr_val = result[category].get(field_name)
                result[category][field_name] = merge_spec_value(curr_val, field_val)
        else:
            result[category] = merge_spec_value(result[category], fields)
    return result
