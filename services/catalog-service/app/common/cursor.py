"""Opaque cursor (keyset) pagination helpers.

Cursors are URL-safe Base64 tokens wrapping the composite boundary tuple
``"{min_price_egp}:{id}"``. The price provides the business order while the id
provides a strictly unique tie-breaker so equal-priced laptops never shift or
duplicate across pages.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import math


class InvalidCursorError(ValueError):
    """Raised when a pagination cursor is malformed or tampered with."""


@dataclass(frozen=True, slots=True)
class Cursor:
    """Decoded keyset boundary tuple."""

    price: float
    item_id: str


def encode_cursor(price: float, item_id: str) -> str:
    """Encode a ``(price, id)`` boundary into an opaque URL-safe token."""
    raw = f"{float(price)}:{item_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: str) -> Cursor:
    """Decode and validate an opaque cursor token.

    Raises:
        InvalidCursorError: If the token is not valid URL-safe Base64, does not
            contain a ``price:id`` payload, or carries a non-finite price.
    """
    if not token or not token.strip():
        raise InvalidCursorError("Pagination cursor cannot be empty.")

    try:
        padded = token.strip() + "=" * (-len(token.strip()) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
        raise InvalidCursorError("Pagination cursor is not valid Base64.") from exc

    price_text, separator, item_id = raw.partition(":")
    if not separator or not item_id.strip():
        raise InvalidCursorError("Pagination cursor payload is malformed.")

    try:
        price = float(price_text)
    except (TypeError, ValueError) as exc:
        raise InvalidCursorError("Pagination cursor price is invalid.") from exc

    if not math.isfinite(price):
        raise InvalidCursorError("Pagination cursor price must be finite.")

    return Cursor(price=price, item_id=item_id.strip())


__all__ = ["Cursor", "InvalidCursorError", "decode_cursor", "encode_cursor"]
