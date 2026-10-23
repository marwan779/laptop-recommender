"""Generic OCR Extractor using RapidOCR (ONNX Runtime).

Provides lightweight, store-agnostic optical character recognition for e-commerce
product specification flyers, brochures, and screenshots.
"""

from __future__ import annotations

from io import BytesIO
import re
from typing import Any
import httpx
import numpy as np
from PIL import Image

from app.common.logger import get_logger

logger = get_logger("pipeline.ocr")


class GenericOCRExtractor:
    """Generic, lazy-loaded OCR extraction engine powered by RapidOCR."""

    _engine: Any | None = None

    BLACKLISTED_URL_KEYWORDS: tuple[str, ...] = (
        "logo",
        "star",
        "icon",
        "badge",
        "avatar",
        "payment",
        "review",
        "button",
        "cart",
        "trust",
        "arrow",
        "social",
        "favicon",
        "spinner",
        "banner-small",
    )

    VALID_IMAGE_EXTENSIONS: tuple[str, ...] = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    )

    MIN_IMAGE_BYTES: int = 25_000  # 25 KB
    MIN_IMAGE_WIDTH: int = 350
    MIN_IMAGE_HEIGHT: int = 250

    @classmethod
    def get_engine(cls) -> Any:
        """Lazy-load the RapidOCR engine on first invocation."""
        if cls._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR

                # Initialize RapidOCR with default English/Latin models
                cls._engine = RapidOCR()
                logger.info("RapidOCR ONNX engine initialized successfully.")
            except Exception as e:
                logger.error("Failed to initialize RapidOCR engine: %s", e)
                raise
        return cls._engine

    @classmethod
    def is_valid_flyer_url(cls, image_url: str) -> bool:
        """Check if an image URL points to a legitimate candidate spec flyer."""
        if not image_url or not isinstance(image_url, str):
            return False

        url_lower = image_url.lower()

        # Must have a valid web image extension
        if not any(ext in url_lower for ext in cls.VALID_IMAGE_EXTENSIONS):
            return False

        # Reject thumbnails, icons, payment logos, or star ratings
        if any(keyword in url_lower for keyword in cls.BLACKLISTED_URL_KEYWORDS):
            return False

        return True

    @classmethod
    def fetch_image_bytes(cls, image_url: str, timeout_sec: float = 3.0) -> bytes | None:
        """Download image bytes with a strict timeout and validation guards."""
        if not cls.is_valid_flyer_url(image_url):
            return None

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }

        try:
            with httpx.Client(timeout=timeout_sec, follow_redirects=True, headers=headers) as client:
                resp = client.get(image_url)
                if resp.status_code != 200:
                    logger.debug("Flyer image fetch returned HTTP %s for %s", resp.status_code, image_url)
                    return None

                content = resp.content
                if len(content) < cls.MIN_IMAGE_BYTES:
                    logger.debug(
                        "Flyer image rejected: size %d bytes < threshold %d bytes for %s",
                        len(content),
                        cls.MIN_IMAGE_BYTES,
                        image_url,
                    )
                    return None

                return content
        except Exception as e:
            logger.debug("Failed to fetch flyer image from %s: %s", image_url, e)
            return None

    @classmethod
    def cluster_and_sort_detections(cls, detections: list[Any]) -> list[str]:
        """Cluster OCR bounding boxes into horizontal lines sorted top-to-bottom, left-to-right."""
        if not detections:
            return []

        items = []
        for box, text, score in detections:
            text_clean = text.strip()
            if not text_clean:
                continue

            y_top = min(p[1] for p in box)
            y_bottom = max(p[1] for p in box)
            y_center = (y_top + y_bottom) / 2.0
            x_left = min(p[0] for p in box)
            height = max(8.0, y_bottom - y_top)

            try:
                score_val = float(score)
            except (ValueError, TypeError):
                score_val = 0.5

            items.append(
                {
                    "y_center": y_center,
                    "x_left": x_left,
                    "height": height,
                    "text": text_clean,
                    "score": score_val,
                }
            )

        if not items:
            return []

        # Sort primarily by vertical position
        items.sort(key=lambda it: it["y_center"])

        # Cluster boxes belonging to the same horizontal text line
        rows: list[list[dict[str, Any]]] = []
        for it in items:
            if not rows:
                rows.append([it])
                continue

            last_row = rows[-1]
            avg_y = sum(x["y_center"] for x in last_row) / len(last_row)
            avg_h = sum(x["height"] for x in last_row) / len(last_row)

            # If within 65% of the average line height, group onto the same row
            if abs(it["y_center"] - avg_y) < max(it["height"], avg_h) * 0.65:
                last_row.append(it)
            else:
                rows.append([it])

        # Synthesize lines from left to right
        lines: list[str] = []
        for row in rows:
            row.sort(key=lambda it: it["x_left"])
            if len(row) == 1:
                raw_line = row[0]["text"]
            else:
                first = row[0]["text"]
                second = " ".join(x["text"] for x in row[1:])
                # If first item looks like a key without colon, join with ': '
                if not any(first.endswith(d) for d in [":", "-", "—", "–"]):
                    raw_line = f"{first}: {second}"
                else:
                    raw_line = f"{first} {second}"
            cleaned_line = cls._sanitize_ocr_line(raw_line)
            if cleaned_line:
                lines.append(cleaned_line)

        return lines

    @classmethod
    def _sanitize_ocr_line(cls, line: str) -> str:
        line = line.strip()
        if not line:
            return ""
        # 1. Ensure space after colon if followed immediately by alphanumeric
        line = re.sub(r":([a-zA-Z0-9])", r": \g<1>", line)
        # 2. Separate numbers and capacity units from adjacent words (e.g. 32GBDDR5 -> 32GB DDR5)
        line = re.sub(r"(\d+\s*(?:GB|TB|MB))([a-zA-Z])", r"\g<1> \g<2>", line, flags=re.IGNORECASE)
        line = re.sub(r"\b(\d+)\s*G\s*B\b", r"\g<1>GB", line, flags=re.IGNORECASE)
        line = re.sub(r"\b(\d+)\s*T\s*B\b", r"\g<1>TB", line, flags=re.IGNORECASE)
        # 3. Separate DDR type from frequency (e.g. DDR55200MHz -> DDR5 5200MHz)
        line = re.sub(r"(DDR[345]|LPDDR[45]X?)(\d{4})", r"\g<1> \g<2>", line, flags=re.IGNORECASE)
        # 4. Fix PCIe misread as PCle and separate adjacent storage tokens
        line = re.sub(r"\bPCle\b", "PCIe", line)
        line = re.sub(r"(NVMe|PCIe|SATA)\s*(PCIe|SSD|HDD)", r"\g<1> \g<2>", line, flags=re.IGNORECASE)
        line = re.sub(r"(\d\.\d)\s*(SSD|HDD)", r"\g<1> \g<2>", line, flags=re.IGNORECASE)
        # 5. Fix common brand and GPU spacing issues (e.g. NVIDIAGeForceRTX40708GB -> NVIDIA GeForce RTX 4070 8GB)
        line = re.sub(r"(NVIDIA)\s*(GeForce)", r"\g<1> \g<2>", line, flags=re.IGNORECASE)
        line = re.sub(r"(GeForce)\s*(RTX|GTX|MX)", r"\g<1> \g<2>", line, flags=re.IGNORECASE)
        line = re.sub(r"(RTX|GTX|RX)\s*(\d{3,4})", r"\g<1> \g<2>", line, flags=re.IGNORECASE)
        line = re.sub(r"(\b\d{3,4})\s*(\d+\s*(?:GB|TB|MB)\b)", r"\g<1> \g<2>", line, flags=re.IGNORECASE)
        return line.strip()

    @classmethod
    def extract_lines_from_bytes(
        cls,
        image_bytes: bytes,
        min_confidence: float = 0.60,
    ) -> tuple[list[str], float]:
        """Run OCR on image bytes and return extracted lines along with average confidence."""
        try:
            img = Image.open(BytesIO(image_bytes)).convert("RGB")
            if img.width < cls.MIN_IMAGE_WIDTH or img.height < cls.MIN_IMAGE_HEIGHT:
                logger.debug(
                    "Image rejected due to dimensions %dx%d < threshold %dx%d",
                    img.width,
                    img.height,
                    cls.MIN_IMAGE_WIDTH,
                    cls.MIN_IMAGE_HEIGHT,
                )
                return [], 0.0

            engine = cls.get_engine()
            img_np = np.array(img)
            result, _ = engine(img_np)
            if not result:
                return [], 0.0

            filtered_detections = []
            scores = []
            for item in result:
                if len(item) >= 3:
                    box, text, score = item[0], item[1], item[2]
                    try:
                        s_val = float(score)
                    except (ValueError, TypeError):
                        s_val = 0.5
                    if s_val >= min_confidence and len(text.strip()) > 1:
                        filtered_detections.append((box, text, score))
                        scores.append(s_val)

            if not filtered_detections:
                return [], 0.0

            lines = cls.cluster_and_sort_detections(filtered_detections)
            avg_score = sum(scores) / len(scores) if scores else 0.0
            return lines, round(avg_score, 3)

        except Exception as e:
            logger.warning("OCR processing failed on image bytes: %s", e)
            return [], 0.0

    @classmethod
    def extract_lines_from_url(
        cls,
        image_url: str,
        timeout_sec: float = 3.0,
        min_confidence: float = 0.60,
    ) -> tuple[list[str], float]:
        """Fetch flyer image from URL and extract specification text lines."""
        content = cls.fetch_image_bytes(image_url, timeout_sec=timeout_sec)
        if not content:
            return [], 0.0
        return cls.extract_lines_from_bytes(content, min_confidence=min_confidence)
