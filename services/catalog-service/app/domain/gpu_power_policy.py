"""Domain Policy for GPU TGP (Total Graphics Power) Utilization and Power-Capping.

Pure domain module: zero database, framework, or network dependencies.
Evaluates actual laptop GPU wattage against manufacturer reference limits (NVIDIA / AMD)
loaded from `data/gpu_benchmarks.json`.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

# Domain Tier Constants (stored in LaptopMetrics.silicon_tier <= 50 chars)
TIER_INTEGRATED_SOC = "INTEGRATED_SOC"
TIER_FULL_POWER_GPU = "FULL_POWER_GPU"
TIER_MODERATELY_CAPPED_GPU = "MODERATELY_CAPPED_GPU"
TIER_HEAVILY_CAPPED_GPU = "HEAVILY_CAPPED_GPU"
TIER_UNKNOWN_TGP_DGPU = "UNKNOWN_TGP_DGPU"
TIER_DISCRETE_EXPLICIT_TGP = "DISCRETE_EXPLICIT_TGP"


@dataclass(frozen=True)
class GpuTgpEvaluation:
    """Evaluation result of laptop GPU TGP against native hardware limits."""

    tier: str
    native_base_max_w: int | None
    native_max_w: int | None
    tgp_utilization_pct: int | None
    warning_en: str | None
    warning_ar: str | None


_DATA_LOADED = False
_PATTERNS: list[tuple[str, dict[str, Any]]] = []
_MODEL_EXACT_MAP: dict[str, dict[str, Any]] = {}


def _clean_str(val: str) -> str:
    """Strip all non-alphanumeric characters and lowercase for fuzzy token matching."""
    return re.sub(r"[^a-z0-9]", "", val.lower())


def _ensure_data_loaded() -> None:
    """Load and index gpu_benchmarks.json once into in-memory pattern matching structures."""
    global _DATA_LOADED, _PATTERNS, _MODEL_EXACT_MAP
    if _DATA_LOADED:
        return

    data_file = Path(__file__).resolve().parent.parent.parent / "data" / "gpu_benchmarks.json"
    if not data_file.exists():
        # Fallback for environments where data might be relative to cwd
        data_file = Path("data/gpu_benchmarks.json").resolve()

    if data_file.exists():
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            patterns: list[tuple[str, dict[str, Any]]] = []
            exact_map: dict[str, dict[str, Any]] = {}

            for _key, item in raw_data.items():
                if not isinstance(item, dict):
                    continue
                model = str(item.get("model") or "").strip()
                match_patterns = item.get("match_patterns") or []

                if model:
                    exact_map[_clean_str(model)] = item

                for pat in match_patterns + [model]:
                    cleaned_pat = _clean_str(str(pat))
                    if cleaned_pat:
                        patterns.append((cleaned_pat, item))

            # Sort patterns by length descending so more specific patterns (e.g. 'rtx5070ti') match before 'rtx5070'
            patterns.sort(key=lambda x: len(x[0]), reverse=True)
            _PATTERNS = patterns
            _MODEL_EXACT_MAP = exact_map
        except Exception:
            _PATTERNS = []
            _MODEL_EXACT_MAP = {}

    _DATA_LOADED = True


def find_gpu_spec(gpu_model: str | None) -> dict[str, Any] | None:
    """Find native GPU specification entry from gpu_benchmarks.json."""
    if not gpu_model:
        return None

    _ensure_data_loaded()
    cleaned_query = _clean_str(gpu_model)
    if not cleaned_query:
        return None

    # 1. Exact match
    if cleaned_query in _MODEL_EXACT_MAP:
        return _MODEL_EXACT_MAP[cleaned_query]

    # 2. Substring pattern match (longest pattern first)
    for pat, item in _PATTERNS:
        if pat in cleaned_query or cleaned_query in pat:
            return item

    return None


def evaluate_gpu_tgp(
    gpu_model: str | None,
    integrated: bool,
    actual_tdp_w: float | int | None,
) -> GpuTgpEvaluation:
    """Evaluate discrete GPU TGP against native NVIDIA / AMD reference limits.

    Cases handled:
    1. Integrated GPU (Iris Xe, Radeon iGPU, Apple SoC) -> INTEGRATED_SOC, no warning.
    2. Unknown / missing TGP on discrete GPU -> UNKNOWN_TGP_DGPU, no false warning or praise.
    3. Discrete GPU with no reference limits in JSON -> DISCRETE_EXPLICIT_TGP, no ratio.
    4. actual_tgp >= 90% of base_max_w -> FULL_POWER_GPU, no warning.
    5. 70% <= actual_tgp / base_max_w < 90% -> MODERATELY_CAPPED_GPU with honest warning.
    6. actual_tgp < 70% of base_max_w -> HEAVILY_CAPPED_GPU with strong warning.
    """
    # Case 1: Integrated GPU
    if integrated:
        return GpuTgpEvaluation(
            tier=TIER_INTEGRATED_SOC,
            native_base_max_w=None,
            native_max_w=None,
            tgp_utilization_pct=None,
            warning_en=None,
            warning_ar=None,
        )

    model_clean = str(gpu_model or "").lower()
    if any(igpu_term in model_clean for igpu_term in ["intel uhd", "intel hd", "iris", "radeon 6", "radeon 780m", "radeon 8"]):
        # Secondary safety check for integrated GPUs not marked as integrated
        return GpuTgpEvaluation(
            tier=TIER_INTEGRATED_SOC,
            native_base_max_w=None,
            native_max_w=None,
            tgp_utilization_pct=None,
            warning_en=None,
            warning_ar=None,
        )

    # Clean numeric actual TGP
    valid_tgp: float | None = None
    if actual_tdp_w is not None:
        try:
            val = float(actual_tdp_w)
            if val > 0:
                valid_tgp = val
        except (ValueError, TypeError):
            valid_tgp = None

    spec = find_gpu_spec(gpu_model)
    tdp_limits = (spec or {}).get("tdp_limits") if isinstance(spec, dict) else None

    base_max: int | None = None
    max_w: int | None = None

    if isinstance(tdp_limits, dict):
        raw_base = tdp_limits.get("base_max_w")
        raw_max = tdp_limits.get("max_w")
        base_max = int(raw_base) if raw_base is not None else None
        max_w = int(raw_max) if raw_max is not None else None

    # Case 2: Discrete GPU with unknown / zero TGP
    if valid_tgp is None:
        return GpuTgpEvaluation(
            tier=TIER_UNKNOWN_TGP_DGPU,
            native_base_max_w=base_max,
            native_max_w=max_w,
            tgp_utilization_pct=None,
            warning_en=None,
            warning_ar=None,
        )

    # Case 3: Discrete GPU without reference limits in database (e.g. legacy MX or unlisted)
    ref_base = base_max if base_max is not None else max_w
    ref_ceiling = max_w if max_w is not None else base_max

    if ref_base is None or ref_base <= 0 or ref_ceiling is None or ref_ceiling <= 0:
        return GpuTgpEvaluation(
            tier=TIER_DISCRETE_EXPLICIT_TGP,
            native_base_max_w=None,
            native_max_w=None,
            tgp_utilization_pct=None,
            warning_en=None,
            warning_ar=None,
        )

    # Compute utilization against max ceiling (for display percentage e.g. 75W / 115W = 65%)
    utilization_pct = min(100, round((valid_tgp / ref_ceiling) * 100))

    # Evaluate throttling ratio against base_max_w (avoids penalizing cards that only skip dynamic boost)
    ratio_to_base = valid_tgp / ref_base
    int_actual = int(round(valid_tgp))

    # Case 4: Full Power GPU (>= 90% of base max TGP)
    if ratio_to_base >= 0.90:
        return GpuTgpEvaluation(
            tier=TIER_FULL_POWER_GPU,
            native_base_max_w=base_max,
            native_max_w=max_w,
            tgp_utilization_pct=utilization_pct,
            warning_en=None,
            warning_ar=None,
        )

    # Case 5: Moderately Capped GPU (70% <= ratio < 90%)
    if ratio_to_base >= 0.70:
        return GpuTgpEvaluation(
            tier=TIER_MODERATELY_CAPPED_GPU,
            native_base_max_w=base_max,
            native_max_w=max_w,
            tgp_utilization_pct=utilization_pct,
            warning_en=(
                f"GPU power capped at {int_actual}W (vs {ref_ceiling}W max) — "
                f"~10–20% lower gaming FPS than full-power models."
            ),
            warning_ar=(
                f"طاقة كارت الشاشة مقيدة عند {int_actual}W (من أصل {ref_ceiling}W كحد أقصى) — "
                f"أداء أقل في الألعاب بنسبة 10-20% عن النسخ كاملة الطاقة."
            ),
        )

    # Case 6: Heavily Capped GPU (< 70% of base max TGP, e.g. 45W)
    return GpuTgpEvaluation(
        tier=TIER_HEAVILY_CAPPED_GPU,
        native_base_max_w=base_max,
        native_max_w=max_w,
        tgp_utilization_pct=utilization_pct,
        warning_en=(
            f"Heavily power-limited GPU ({int_actual}W vs {ref_ceiling}W max) — "
            f"expect ~25–40% lower 3D performance."
        ),
        warning_ar=(
            f"طاقة كارت الشاشة محدودة بشكل كبير عند {int_actual}W (من أصل {ref_ceiling}W كحد أقصى) — "
            f"أداء أضعف بنسبة 25-40% في الألعاب والرندر."
        ),
    )


def inject_gpu_tgp_warning(
    cons_en: list[str] | None,
    cons_ar: list[str] | None,
    evaluation: GpuTgpEvaluation,
) -> tuple[list[str], list[str]]:
    """Prepend GPU TGP cap warning to cons lists if evaluation has an active warning.

    Idempotent: will not duplicate warning if already present in the list.
    """
    clean_en = list(cons_en or [])
    clean_ar = list(cons_ar or [])

    if not evaluation.warning_en or not evaluation.warning_ar:
        return clean_en, clean_ar

    has_warning_en = any("GPU power" in c or "power-limited GPU" in c for c in clean_en)
    has_warning_ar = any("كارت الشاشة" in c and ("مقيدة" in c or "محدودة" in c) for c in clean_ar)

    if not has_warning_en:
        clean_en.insert(0, evaluation.warning_en)
    if not has_warning_ar:
        clean_ar.insert(0, evaluation.warning_ar)

    return clean_en, clean_ar
