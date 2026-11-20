"""Unit tests for GPU TGP evaluation domain policy."""

import pytest

from app.domain.gpu_power_policy import (
    TIER_DISCRETE_EXPLICIT_TGP,
    TIER_FULL_POWER_GPU,
    TIER_HEAVILY_CAPPED_GPU,
    TIER_INTEGRATED_SOC,
    TIER_MODERATELY_CAPPED_GPU,
    TIER_UNKNOWN_TGP_DGPU,
    evaluate_gpu_tgp,
    inject_gpu_tgp_warning,
)


def test_acer_nitro_v15_rtx_5050_75w_moderately_capped():
    """Case: Acer Nitro V 15 with RTX 5050 capped at 75W (vs 100W base / 115W max)."""
    eval_res = evaluate_gpu_tgp(
        gpu_model="GeForce RTX 5050",
        integrated=False,
        actual_tdp_w=75,
    )
    assert eval_res.tier == TIER_MODERATELY_CAPPED_GPU
    assert eval_res.native_base_max_w == 100
    assert eval_res.native_max_w == 115
    assert eval_res.tgp_utilization_pct == 65  # 75 / 115 = 65.2% -> 65%
    assert eval_res.warning_en is not None
    assert "75W" in eval_res.warning_en
    assert "115W" in eval_res.warning_en
    assert eval_res.warning_ar is not None
    assert "75W" in eval_res.warning_ar


def test_msi_cyborg_rtx_4050_45w_heavily_capped():
    """Case: Ultra-thin / budget laptop with RTX 4050 capped at 45W (vs 115W base / 140W max)."""
    eval_res = evaluate_gpu_tgp(
        gpu_model="GeForce RTX 4050",
        integrated=False,
        actual_tdp_w=45,
    )
    assert eval_res.tier == TIER_HEAVILY_CAPPED_GPU
    assert eval_res.native_base_max_w == 115
    assert eval_res.native_max_w == 140
    assert eval_res.tgp_utilization_pct == 32  # 45 / 140 = 32%
    assert eval_res.warning_en is not None
    assert "Heavily power-limited" in eval_res.warning_en


def test_full_power_rtx_4060_140w():
    """Case: Full-power gaming laptop with 140W RTX 4060."""
    eval_res = evaluate_gpu_tgp(
        gpu_model="GeForce RTX 4060",
        integrated=False,
        actual_tdp_w=140,
    )
    assert eval_res.tier == TIER_FULL_POWER_GPU
    assert eval_res.tgp_utilization_pct == 100
    assert eval_res.warning_en is None
    assert eval_res.warning_ar is None


def test_full_power_rtx_4060_105w():
    """Case: Standard gaming laptop running RTX 4060 at 105W (105 / 115 base = 91.3% -> full power)."""
    eval_res = evaluate_gpu_tgp(
        gpu_model="GeForce RTX 4060",
        integrated=False,
        actual_tdp_w=105,
    )
    assert eval_res.tier == TIER_FULL_POWER_GPU
    assert eval_res.warning_en is None


def test_integrated_gpu():
    """Case: Integrated Intel Arc or Radeon graphics."""
    eval_res = evaluate_gpu_tgp(
        gpu_model="Intel Arc 140V",
        integrated=True,
        actual_tdp_w=0,
    )
    assert eval_res.tier == TIER_INTEGRATED_SOC
    assert eval_res.native_max_w is None
    assert eval_res.tgp_utilization_pct is None
    assert eval_res.warning_en is None


def test_unknown_tgp_discrete_gpu():
    """Case: Discrete GPU where store/scraper did not extract TGP wattage."""
    eval_res = evaluate_gpu_tgp(
        gpu_model="GeForce RTX 5050",
        integrated=False,
        actual_tdp_w=None,
    )
    assert eval_res.tier == TIER_UNKNOWN_TGP_DGPU
    assert eval_res.native_max_w == 115
    assert eval_res.tgp_utilization_pct is None
    assert eval_res.warning_en is None


def test_discrete_explicit_tgp_unlisted_or_null_limits():
    """Case: Discrete GPU with explicit wattage but null limits in database (e.g. MX350 or legacy)."""
    eval_res = evaluate_gpu_tgp(
        gpu_model="GeForce GTX 1050",
        integrated=False,
        actual_tdp_w=50,
    )
    assert eval_res.tier == TIER_DISCRETE_EXPLICIT_TGP
    assert eval_res.warning_en is None


def test_inject_gpu_tgp_warning_idempotence():
    """Verify warning injection prepends cleanly and does not duplicate."""
    eval_res = evaluate_gpu_tgp("GeForce RTX 5050", False, 75)
    assert eval_res.warning_en is not None

    en_list, ar_list = inject_gpu_tgp_warning(
        cons_en=["Plastic chassis flex", "Loud fan under load"],
        cons_ar=["شاسيه بلاستيك", "صوت مراوح عالي"],
        evaluation=eval_res,
    )
    assert len(en_list) == 3
    assert en_list[0] == eval_res.warning_en
    assert len(ar_list) == 3
    assert ar_list[0] == eval_res.warning_ar

    # Second injection should be no-op (idempotent)
    en_list_2, ar_list_2 = inject_gpu_tgp_warning(en_list, ar_list, eval_res)
    assert len(en_list_2) == 3
    assert len(ar_list_2) == 3
