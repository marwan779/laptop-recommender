import re


class ModelNormalizer:
    """Normalizes and extracts laptop model tokens, SKUs, and MPNs.

    Handles tokens like:
      - Full SKU: 'S3407CA-LY065W', 'S3407AA-SF117W', 'H7606WW-SE926W', 'FA507NVR-LP007W'
      - Sub-model: 'S3407CA', 'S3407AA', 'S5452MA', 'H7607BA', 'H7606WW'
      - Base model: 'S3407', 'S5452', 'H7607', 'H7606', 'FA507', 'UX3405'
    """

    # Matches full configuration SKU: 1-4 letters, 3-5 digits, 1-4 letters, hyphen, 4-8 chars
    FULL_SKU_REGEX = re.compile(
        r"\b([A-Za-z]{1,4}\d{3,5}[A-Za-z0-9]{1,4}-[A-Za-z0-9]{4,8})\b",
        re.IGNORECASE,
    )

    # Matches sub-model series: 1-4 letters, 3-5 digits, 1-4 letters (no hyphen)
    SUB_MODEL_REGEX = re.compile(
        r"\b([A-Za-z]{1,4}\d{3,5}[A-Za-z]{1,4})\b",
        re.IGNORECASE,
    )

    # Matches base chassis model: 1-4 letters, 3-5 digits
    BASE_MODEL_REGEX = re.compile(
        r"\b([A-Za-z]{1,4}\d{3,5})\b",
        re.IGNORECASE,
    )

    # Matches chassis prefix from sub-model or SKU (e.g. 'S3407' from 'S3407CA')
    CHASSIS_PREFIX_REGEX = re.compile(
        r"^([A-Za-z]{1,4}\d{3,5})",
        re.IGNORECASE,
    )

    # Matches Manufacturer Part Numbers (e.g. 90NB16J1-M00410, 90NB1991-M00F40)
    MPN_REGEX = re.compile(
        r"\b(90[A-Za-z0-9]{6,8}-[A-Za-z0-9]{4,8})\b",
        re.IGNORECASE,
    )

    # Eastern Arabic numerals mapping to Western Arabic numerals
    ARABIC_NUMERALS_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

    @classmethod
    def normalize_arabic_numerals(cls, text: str | None) -> str:
        """Convert Eastern Arabic numerals (٠-٩) to standard ASCII digits (0-9)."""
        if not text:
            return ""
        return text.translate(cls.ARABIC_NUMERALS_MAP)

    @classmethod
    def clean_noisy_title(cls, title: str | None) -> str:
        """Strip common marketing buzzwords and clean up whitespace."""
        if not title:
            return ""
        clean = cls.normalize_arabic_numerals(title)
        # Strip marketing noise
        noise_patterns = [
            r"\b(brand\s*new|special\s*offer|best\s*seller|hot\s*deal)\b",
            r"(ضمان\s*محلي|توصيل\s*مجاني|عرض\s*خاص|أفضل\s*سعر|جديد)",
        ]
        for pattern in noise_patterns:
            clean = re.sub(pattern, " ", clean, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", clean).strip()

    @classmethod
    def normalize_token(cls, token: str | None) -> str:
        """Strip hyphens, spaces, and lowercase for comparison."""
        if not token:
            return ""
        return re.sub(r"[\s\-_]+", "", token).lower()

    @classmethod
    def normalize_mpn(cls, mpn: str | None) -> str | None:
        """Normalize Manufacturer Part Number for exact comparison."""
        if not mpn:
            return None
        match = cls.MPN_REGEX.search(mpn)
        if match:
            return match.group(1).upper()
        clean = re.sub(r"[\s_]+", "", mpn).upper()
        if clean.startswith("90") and len(clean) >= 12:
            return clean
        return None

    @classmethod
    def extract_base_model(cls, text: str | None) -> str | None:
        """Extract the root chassis model (e.g., 'S3407' from 'S3407CA-LY065W' or text)."""
        if not text:
            return None
        # Try full SKU first
        match_sku = cls.FULL_SKU_REGEX.search(text)
        if match_sku:
            token = match_sku.group(1)
            prefix = token.split("-")[0]
            m = cls.CHASSIS_PREFIX_REGEX.match(prefix)
            if m:
                return m.group(1).upper()

        # Try sub-model
        match_sub = cls.SUB_MODEL_REGEX.search(text)
        if match_sub:
            token = match_sub.group(1)
            m = cls.CHASSIS_PREFIX_REGEX.match(token)
            if m:
                return m.group(1).upper()

        # Try base model
        match_bm = cls.BASE_MODEL_REGEX.search(text)
        if match_bm:
            return match_bm.group(1).upper()

        return None

    @classmethod
    def extract_model_tokens(cls, text: str | None) -> dict[str, str | None]:
        """Extract all model-related tokens from text.

        Returns dict with:
          - 'full_sku': e.g. 'S3407CA-LY065W'
          - 'sub_model': e.g. 'S3407CA'
          - 'base_model': e.g. 'S3407'
          - 'mpn': e.g. '90NB16J1-M00410'
        """
        result: dict[str, str | None] = {
            "full_sku": None,
            "sub_model": None,
            "base_model": None,
            "mpn": None,
        }
        if not text:
            return result

        result["mpn"] = cls.normalize_mpn(text)

        # Full SKU
        match_sku = cls.FULL_SKU_REGEX.search(text)
        if match_sku:
            sku = match_sku.group(1).upper()
            result["full_sku"] = sku
            # Derive sub-model and base model from full SKU
            prefix = sku.split("-")[0]
            result["sub_model"] = prefix
            bm = cls.CHASSIS_PREFIX_REGEX.match(prefix)
            if bm:
                result["base_model"] = bm.group(1).upper()
            return result

        # Sub-model (without hyphen)
        for match in cls.SUB_MODEL_REGEX.finditer(text):
            token = match.group(1).upper()
            # Ensure it has both letters and digits and is >= 5 chars
            if any(c.isalpha() for c in token) and any(c.isdigit() for c in token) and len(token) >= 5:
                result["sub_model"] = token
                bm = cls.CHASSIS_PREFIX_REGEX.match(token)
                if bm:
                    result["base_model"] = bm.group(1).upper()
                return result

        # Base model
        bm = cls.BASE_MODEL_REGEX.search(text)
        if bm:
            token = bm.group(1).upper()
            if any(c.isalpha() for c in token) and any(c.isdigit() for c in token):
                result["base_model"] = token

        return result
