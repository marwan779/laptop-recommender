import re
from typing import NamedTuple

from app.matching.normalizer import ModelNormalizer
from app.schemas.laptop import ConfigurationItem, MatchMethod, MatchStatus, ModelFamily, RetailerProduct


class MatchResult(NamedTuple):
    status: MatchStatus
    method: MatchMethod
    confidence: float
    reason: str
    target_model: str
    candidate_title: str

    @property
    def is_accepted(self) -> bool:
        return self.status in (MatchStatus.EXACT, MatchStatus.PROBABLE)


class CommonMatchingEngine:
    """Dedicated identity and verification engine.

    Strictly separates candidate generation from verified matching.
    Enforces mandatory hard rejection rules and prioritizes MPN > Full SKU > Sub-model > Specs.
    """

    @classmethod
    def evaluate(
        cls,
        target_config: ConfigurationItem,
        target_family: ModelFamily,
        candidate: RetailerProduct,
    ) -> MatchResult:
        """Evaluate whether a retailer product candidate matches the target official configuration."""
        target_model = target_config.model.strip().upper()
        target_series = (target_config.model_series or "").strip().upper()
        target_base = (target_config.base_model or target_family.base_model or "").strip().upper()
        target_mpn = ModelNormalizer.normalize_mpn(target_config.mpn)

        # Extract all tokens from the candidate (title, model_code, retailer_sku, mpn)
        combined_candidate_text = f"{candidate.title} {candidate.model_code or ''} {candidate.retailer_sku or ''} {candidate.mpn or ''}"
        candidate_tokens = ModelNormalizer.extract_model_tokens(combined_candidate_text)
        candidate_base = (candidate.base_model or candidate_tokens.get("base_model") or "").strip().upper()
        candidate_sub = (candidate.sub_model or candidate_tokens.get("sub_model") or "").strip().upper()
        candidate_sku = (candidate.model_code or candidate_tokens.get("full_sku") or "").strip().upper()
        candidate_mpn = ModelNormalizer.normalize_mpn(candidate.mpn or candidate_tokens.get("mpn"))

        candidate_title_lower = candidate.title.lower()

        # =====================================================================
        # 1. HARD REJECTION RULE: Conflicting Base Model
        # =====================================================================
        if target_base and candidate_base and target_base != candidate_base:
            reason = f"Conflicting base model: target={target_base} vs candidate={candidate_base}"
            cls._log_decision("REJECTED", reason, target_config.model, candidate)
            return MatchResult(
                status=MatchStatus.REJECTED,
                method=MatchMethod.NONE,
                confidence=0.0,
                reason=reason,
                target_model=target_model,
                candidate_title=candidate.title,
            )

        # Extra check: if candidate title contains an explicit conflicting base model token
        if target_base:
            # Look for 4-5 digit model tokens in candidate title
            found_candidate_models = re.findall(r"\b([A-Za-z]{1,4}\d{3,5})\b", candidate.title)
            conflicting = [
                m.upper()
                for m in found_candidate_models
                if m.upper() != target_base and any(c.isdigit() for c in m) and len(m) >= 4
            ]
            if conflicting and target_base not in [m.upper() for m in found_candidate_models]:
                reason = f"Conflicting model code in title: target={target_base} vs candidate={conflicting[0]}"
                cls._log_decision("REJECTED", reason, target_config.model, candidate)
                return MatchResult(
                    status=MatchStatus.REJECTED,
                    method=MatchMethod.NONE,
                    confidence=0.0,
                    reason=reason,
                    target_model=target_model,
                    candidate_title=candidate.title,
                )

        # =====================================================================
        # 2. HARD REJECTION RULE: Conflicting Sub-model Series / Full SKU
        # =====================================================================
        if target_series and candidate_sub and target_series != candidate_sub:
            reason = f"Conflicting sub-model series: target={target_series} vs candidate={candidate_sub}"
            cls._log_decision("REJECTED", reason, target_config.model, candidate)
            return MatchResult(
                status=MatchStatus.REJECTED,
                method=MatchMethod.NONE,
                confidence=0.0,
                reason=reason,
                target_model=target_model,
                candidate_title=candidate.title,
            )

        # If both have explicit full SKUs with hyphens, and they conflict
        if "-" in target_model and candidate_sku and "-" in candidate_sku:
            norm_target_sku = ModelNormalizer.normalize_token(target_model)
            norm_candidate_sku = ModelNormalizer.normalize_token(candidate_sku)
            if norm_target_sku != norm_candidate_sku:
                reason = f"Conflicting full SKU: target={target_model} vs candidate={candidate_sku}"
                cls._log_decision("REJECTED", reason, target_config.model, candidate)
                return MatchResult(
                    status=MatchStatus.REJECTED,
                    method=MatchMethod.NONE,
                    confidence=0.0,
                    reason=reason,
                    target_model=target_model,
                    candidate_title=candidate.title,
                )

        # =====================================================================
        # 3. PRIORITY A: Exact Manufacturer Part Number (MPN) Match
        # =====================================================================
        if target_mpn and candidate_mpn:
            if target_mpn == candidate_mpn:
                reason = f"Exact MPN match: {target_mpn}"
                cls._log_decision("EXACT", reason, target_config.model, candidate, method="MPN")
                return MatchResult(
                    status=MatchStatus.EXACT,
                    method=MatchMethod.MPN,
                    confidence=1.0,
                    reason=reason,
                    target_model=target_model,
                    candidate_title=candidate.title,
                )
            else:
                reason = f"Conflicting MPN: target={target_mpn} vs candidate={candidate_mpn}"
                cls._log_decision("REJECTED", reason, target_config.model, candidate)
                return MatchResult(
                    status=MatchStatus.REJECTED,
                    method=MatchMethod.NONE,
                    confidence=0.0,
                    reason=reason,
                    target_model=target_model,
                    candidate_title=candidate.title,
                )

        # =====================================================================
        # 4. PRIORITY B: Exact Full Configuration SKU Match
        # =====================================================================
        if "-" in target_model:
            # Target is a full SKU like 'S3407CA-LY065W'
            norm_target = ModelNormalizer.normalize_token(target_model)
            # Check candidate_sku or bounded search in title
            if candidate_sku and ModelNormalizer.normalize_token(candidate_sku) == norm_target:
                reason = f"Exact full SKU match: {target_model}"
                cls._log_decision("EXACT", reason, target_config.model, candidate, method="FULL_SKU")
                return MatchResult(
                    status=MatchStatus.EXACT,
                    method=MatchMethod.FULL_SKU,
                    confidence=0.98,
                    reason=reason,
                    target_model=target_model,
                    candidate_title=candidate.title,
                )

            # Check bounded pattern in title (e.g. S3407CA-LY065W in title)
            target_pattern = re.compile(rf"\b{re.escape(target_model)}\b", re.IGNORECASE)
            if target_pattern.search(combined_candidate_text):
                reason = f"Full SKU found in retailer title/details: {target_model}"
                cls._log_decision("EXACT", reason, target_config.model, candidate, method="FULL_SKU")
                return MatchResult(
                    status=MatchStatus.EXACT,
                    method=MatchMethod.FULL_SKU,
                    confidence=0.98,
                    reason=reason,
                    target_model=target_model,
                    candidate_title=candidate.title,
                )

        # =====================================================================
        # 5. PRIORITY C: Exact Sub-model Series Match
        # =====================================================================
        # If target has a sub-model series like 'S3407CA' or target itself is 'S5452MA'
        effective_series = target_series or (target_model if "-" not in target_model else None)
        if effective_series and len(effective_series) >= 5:
            norm_series = ModelNormalizer.normalize_token(effective_series)
            if candidate_sub and ModelNormalizer.normalize_token(candidate_sub) == norm_series:
                # If target has a specific full SKU with hyphen and candidate only gives sub-model:
                if "-" in target_model:
                    status = MatchStatus.PROBABLE
                    confidence = 0.85
                    reason = f"Sub-model series match ({effective_series}) without candidate suffix"
                else:
                    status = MatchStatus.EXACT
                    confidence = 0.95
                    reason = f"Exact sub-model series match: {effective_series}"

                cls._log_decision(status.value, reason, target_config.model, candidate, method="SUB_MODEL_SERIES")
                return MatchResult(
                    status=status,
                    method=MatchMethod.SUB_MODEL_SERIES,
                    confidence=confidence,
                    reason=reason,
                    target_model=target_model,
                    candidate_title=candidate.title,
                )

        # =====================================================================
        # 6. PRIORITY D: Base Model + Fingerprint Verification
        # =====================================================================
        if target_base and candidate_base and target_base == candidate_base:
            # Candidate matches base model (e.g. S3407) and has no conflicting sub-model
            # Verify if CPU / screen size matches official specs
            cpu_match = cls._check_cpu_alignment(target_config.official_specs, candidate)
            if cpu_match:
                reason = f"Base model ({target_base}) matches with aligned processor specifications"
                cls._log_decision("PROBABLE", reason, target_config.model, candidate, method="BASE_MODEL_SPECS")
                return MatchResult(
                    status=MatchStatus.PROBABLE,
                    method=MatchMethod.BASE_MODEL_SPECS,
                    confidence=0.80,
                    reason=reason,
                    target_model=target_model,
                    candidate_title=candidate.title,
                )
            else:
                reason = f"Base model ({target_base}) matches but specs are insufficient to confirm exact SKU"
                cls._log_decision("UNKNOWN", reason, target_config.model, candidate)
                return MatchResult(
                    status=MatchStatus.UNKNOWN,
                    method=MatchMethod.BASE_MODEL_SPECS,
                    confidence=0.50,
                    reason=reason,
                    target_model=target_model,
                    candidate_title=candidate.title,
                )

        # =====================================================================
        # 7. HARD REJECTION RULE: Generic Family Name Alone is UNKNOWN
        # =====================================================================
        reason = "Generic family name or search hit without matching model code, SKU, MPN, or specs"
        cls._log_decision("UNKNOWN", reason, target_config.model, candidate)
        return MatchResult(
            status=MatchStatus.UNKNOWN,
            method=MatchMethod.NONE,
            confidence=0.0,
            reason=reason,
            target_model=target_model,
            candidate_title=candidate.title,
        )

    @classmethod
    def _check_cpu_alignment(cls, official_specs: dict[str, str], candidate: RetailerProduct) -> bool:
        """Check if CPU tiers align between official specs and retailer title/specs."""
        official_cpu = official_specs.get("Processor", "").lower()
        candidate_text = f"{candidate.title} {candidate.specs.get('Processor', '')} {candidate.specs.get('CPU', '')}".lower()

        cpu_tiers = ["ultra 9", "ultra 7", "ultra 5", "core i9", "core i7", "core i5", "core i3", "ryzen 9", "ryzen 7", "ryzen 5"]
        for tier in cpu_tiers:
            if tier in official_cpu and tier in candidate_text:
                return True
        return False

    @classmethod
    def _log_decision(
        cls,
        status: str,
        reason: str,
        target_model: str,
        candidate: RetailerProduct,
        method: str = "NONE",
    ) -> None:
        """Log decision with context for transparent debugging."""
        store = candidate.store_name
        title_snippet = candidate.title[:65]
        if status in ("EXACT", "PROBABLE"):
            print(f"[{store}] Candidate: '{title_snippet}'")
            print(f"  └─► [MATCH: {status}] method={method} target={target_model} | {reason}")
        else:
            print(f"[{store}] Candidate: '{title_snippet}'")
            print(f"  └─► [MATCH: {status}] target={target_model} | {reason}")
