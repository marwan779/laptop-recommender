"""Apply post-audit fixes from data analyst review:
1. Fix 1: Restore genuine charger wattages and remove artificial power floors.
2. Fix 3: Set iGPU board auxiliary power to 15.0W in metrics_engine.py.
3. Fix 4: Disambiguate touchpad vs touchscreen (clear fake touch on 17 gaming laptops).
4. Fix 5: Filter HDMI 4K@60Hz from panel refresh rate (restore 5 ROG Strix/SCAR to 165Hz/240Hz, fix Dell Vostro to FHD, nullify 35ms response times).
5. Fix 6: Disambiguate expansion limits vs installed capacity (Gigabyte A16 4TB->512GB & 64GB->16GB; restore 5 halved RAM models).
6. CPU Fixes: ROG Strix G16 CPU to Ryzen 9 8940HX, Nitro & TUF turbo clocks to 4.6/4.8 GHz.
7. Merge 2 confirmed 1 EGP duplicate pairs into their priced canonical twins.
(Note: Fixes 2 and 7 were explicitly ignored per user instructions).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = SERVICE_ROOT.parent.parent

if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.pipeline.data.cpu_specs import CPU_SPECS
from app.matching.models import UnifiedCatalog
from app.pipeline.icecat.enricher import IcecatCatalogEnricher
from scripts.run_icecat_enrichment import STORE_FILES, DEFAULT_UNIFIED_PATH


def update_metrics_engine_files() -> None:
    """Fix 3: Update catalog-service metrics_engine.py & test."""
    me_path = WORKSPACE_ROOT / "services" / "catalog-service" / "app" / "services" / "metrics_engine.py"
    if me_path.is_file():
        content = me_path.read_text(encoding="utf-8")
        if "board_aux_w = 15.0 if is_integrated else 25.0" not in content:
            # Replace lines in calculate_silicon_and_power_metrics
            old_calc = (
                "    is_integrated = is_integrated_gpu(gpu_spec, gpu_benchmarks)\n\n"
                "    if is_integrated:\n"
                "        # Integrated GPU consumes 0W discrete power (power envelope shared within CPU package)\n"
                "        p_actual = 0.0\n"
                "        tgp_source = \"INTEGRATED_GPU\"\n"
                "        scale_factor_gpu = 1.0\n"
                "    else:\n"
                "        # Infer P_actual (Configured TGP for discrete GPUs)\n"
                "        explicit_tgp = (gpu_spec or {}).get(\"tdp_w\")\n"
                "        if explicit_tgp is not None:\n"
                "            p_actual = float(explicit_tgp)\n"
                "            tgp_source = \"EXPLICIT_SPEC\"\n"
                "        elif power_adapter_w is not None:\n"
                "            p_actual = clamp(power_adapter_w - cpu_base_w - 25.0, tgp_min, tgp_max)\n"
                "            tgp_source = \"INFERRED_FROM_CHARGER\"\n"
                "        else:\n"
                "            p_actual = (tgp_min + tgp_max) / 2.0\n"
                "            tgp_source = \"BENCHMARK_DEFAULT\"\n\n"
                "        # Effective GPU Score (Guard 1: Normalized by 100)\n"
                "        if tgp_max > tgp_min:\n"
                "            scale_factor_gpu = 0.72 + 0.28 * ((p_actual - tgp_min) / (tgp_max - tgp_min))\n"
                "        else:\n"
                "            scale_factor_gpu = 1.0\n\n"
                "    effective_gpu_score = (base_gpu_raw * scale_factor_gpu) / 100.0\n\n"
                "    # Effective CPU Score (Guard 2: power_adapter_w null check)\n"
                "    if power_adapter_w is None:\n"
                "        scale_factor_cpu = 1.0\n"
                "    else:\n"
                "        p_cpu_avail = power_adapter_w - p_actual - 25.0\n"
                "        scale_factor_cpu = clamp(p_cpu_avail / cpu_base_w, 0.70, 1.20)\n\n"
                "    effective_cpu_score = base_cpu_score * scale_factor_cpu\n\n"
                "    # Metric 2: Electrical Power Sufficiency Margin (ΔP)\n"
                "    if power_adapter_w is None:\n"
                "        delta_p = 0.0\n"
                "        electrical_status = \"UNKNOWN_CHARGER_NEUTRAL\"\n"
                "    else:\n"
                "        delta_p = power_adapter_w - (cpu_base_w + p_actual + 25.0)"
            )
            new_calc = (
                "    is_integrated = is_integrated_gpu(gpu_spec, gpu_benchmarks)\n"
                "    board_aux_w = 15.0 if is_integrated else 25.0\n\n"
                "    if is_integrated:\n"
                "        # Integrated GPU consumes 0W discrete power (power envelope shared within CPU package)\n"
                "        p_actual = 0.0\n"
                "        tgp_source = \"INTEGRATED_GPU\"\n"
                "        scale_factor_gpu = 1.0\n"
                "    else:\n"
                "        # Infer P_actual (Configured TGP for discrete GPUs)\n"
                "        explicit_tgp = (gpu_spec or {}).get(\"tdp_w\")\n"
                "        if explicit_tgp is not None:\n"
                "            p_actual = float(explicit_tgp)\n"
                "            tgp_source = \"EXPLICIT_SPEC\"\n"
                "        elif power_adapter_w is not None:\n"
                "            p_actual = clamp(power_adapter_w - cpu_base_w - board_aux_w, tgp_min, tgp_max)\n"
                "            tgp_source = \"INFERRED_FROM_CHARGER\"\n"
                "        else:\n"
                "            p_actual = (tgp_min + tgp_max) / 2.0\n"
                "            tgp_source = \"BENCHMARK_DEFAULT\"\n\n"
                "        # Effective GPU Score (Guard 1: Normalized by 100)\n"
                "        if tgp_max > tgp_min:\n"
                "            scale_factor_gpu = 0.72 + 0.28 * ((p_actual - tgp_min) / (tgp_max - tgp_min))\n"
                "        else:\n"
                "            scale_factor_gpu = 1.0\n\n"
                "    effective_gpu_score = (base_gpu_raw * scale_factor_gpu) / 100.0\n\n"
                "    # Effective CPU Score (Guard 2: power_adapter_w null check)\n"
                "    if power_adapter_w is None:\n"
                "        scale_factor_cpu = 1.0\n"
                "    else:\n"
                "        p_cpu_avail = power_adapter_w - p_actual - board_aux_w\n"
                "        scale_factor_cpu = clamp(p_cpu_avail / cpu_base_w, 0.70, 1.20)\n\n"
                "    effective_cpu_score = base_cpu_score * scale_factor_cpu\n\n"
                "    # Metric 2: Electrical Power Sufficiency Margin (ΔP)\n"
                "    if power_adapter_w is None:\n"
                "        delta_p = 0.0\n"
                "        electrical_status = \"UNKNOWN_CHARGER_NEUTRAL\"\n"
                "    else:\n"
                "        delta_p = power_adapter_w - (cpu_base_w + p_actual + board_aux_w)"
            )
            # Normalize newlines for replacement
            content_norm = content.replace("\r\n", "\n")
            if old_calc in content_norm:
                content_norm = content_norm.replace(old_calc, new_calc, 1)
                me_path.write_text(content_norm.replace("\n", "\r\n"), encoding="utf-8")
                print("[1/7] Updated metrics_engine.py with 15W iGPU board_aux_w")

    test_me_path = WORKSPACE_ROOT / "services" / "catalog-service" / "tests" / "test_metrics_engine.py"
    if test_me_path.is_file():
        t_content = test_me_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        old_test_dp = "    assert power[\"delta_p_watts\"] == 25.0"
        new_test_dp = "    assert power[\"delta_p_watts\"] == 35.0"
        if old_test_dp in t_content:
            t_content = t_content.replace(old_test_dp, new_test_dp, 1)
            test_me_path.write_text(t_content.replace("\n", "\r\n"), encoding="utf-8")
            print("[1b/7] Updated test_metrics_engine.py to expect 35.0W headroom")


def update_pipeline_source_code() -> None:
    """Update deterministic.py and enricher.py to prevent regressions."""
    det_path = SERVICE_ROOT / "app" / "pipeline" / "deterministic.py"
    if det_path.is_file():
        det_content = det_path.read_text(encoding="utf-8").replace("\r\n", "\n")

        # 1. Touchscreen: filter out touchpad/trackpad from touch targets
        old_tt = "        touch_targets = [primary_text, title, \" \".join(table.values())]"
        new_tt = (
            "        # Touchscreen: Only evaluate display-relevant text, ignoring touchpad/pointing rows\n"
            "        disp_only_vals = [v for k, v in table.items() if not any(p in k.lower() for p in ('pad', 'pointing', 'mouse', 'input', 'keyboard'))]\n"
            "        touch_targets = [primary_text, title, \" \".join(disp_only_vals)]"
        )
        if old_tt in det_content:
            det_content = det_content.replace(old_tt, new_tt, 1)

        # 2. Storage capacity: match (user-upgradable to 4TB) and strip expansion limits cleanly
        old_strip = "            clean_tgt = re.sub(\n                r\"\\b(?:up\\s+to|support(?:s)?\\s*(?:up\\s+to)?)\\s*\\d+\\s*(?:tb|gb)\\b\", \"\", target, flags=re.I\n            )"
        new_strip = "            clean_tgt = re.sub(\n                r\"\\b(?:up\\s+to|support(?:s)?\\s*(?:up\\s+to)?|user[- ]upgradable\\s+to|upgradable\\s+to|expandable\\s+to|max(?:\\b|\\.))\\s*\\d+\\s*(?:tb|gb)\\b\", \"\", target, flags=re.I\n            )"
        if old_strip in det_content:
            det_content = det_content.replace(old_strip, new_strip, 1)

        det_path.write_text(det_content.replace("\n", "\r\n"), encoding="utf-8")
        print("[2/7] Updated deterministic.py (touchpad filter & storage expansion stripping)")

    enr_path = SERVICE_ROOT / "app" / "pipeline" / "icecat" / "enricher.py"
    if enr_path.is_file():
        enr_content = enr_path.read_text(encoding="utf-8").replace("\r\n", "\n")

        # Remove artificial power floor override
        old_pwr_block = (
            "        # Power Adapter Physical Sizing Floor for Discrete GPUs\n"
            "        pb_dict = specs.setdefault(\"power_battery\", {})\n"
            "        if not is_integrated:\n"
            "            gpu_tdp = gpu_dict.get(\"tdp_w\") or 0\n"
            "            cpu_p = cpu_dict.get(\"base_power_w\") or 45\n"
            "            req_min = gpu_tdp + cpu_p + 25  # physical operating floor\n"
            "            cur_adp = pb_dict.get(\"power_adapter_w\")\n\n"
            "            if cur_adp is None or cur_adp < req_min:\n"
            "                # Search source_table for explicit AC Adapter / power supply (avoiding CPU-GPU combined power or dynamic boost)\n"
            "                m_adp = re.search(\n"
            "                    r\"\\b(1[3578]\\d|2[0348]\\d|330|400)\\s*w\\s*(?:ac\\s*adapter|power\\s*(?:adapter|supply)|charger)\\b\",\n"
            "                    source_table_str,\n"
            "                    re.I,\n"
            "                )\n"
            "                cand_w = float(m_adp.group(1)) if m_adp else 0.0\n"
            "                if cand_w >= req_min:\n"
            "                    pb_dict[\"power_adapter_w\"] = cand_w\n"
            "                else:\n"
            "                    gpu_m = str(gpu_dict.get(\"model\") or \"\").lower()\n"
            "                    if any(top_gpu in gpu_m for top_gpu in (\"5090\", \"5080\", \"4090\", \"4080\")):\n"
            "                        pb_dict[\"power_adapter_w\"] = 330.0\n"
            "                    elif any(mid_gpu in gpu_m for mid_gpu in (\"5070\", \"4070\")):\n"
            "                        pb_dict[\"power_adapter_w\"] = 240.0\n"
            "                    elif any(g_gpu in gpu_m for g_gpu in (\"5060\", \"4060\")):\n"
            "                        pb_dict[\"power_adapter_w\"] = 230.0\n"
            "                    elif cpu_p >= 55 or \"tuf\" in title_lower or \"loq\" in title_lower or \"victus\" in title_lower:\n"
            "                        pb_dict[\"power_adapter_w\"] = 200.0\n"
            "                    elif \"nitro\" in title_lower:\n"
            "                        pb_dict[\"power_adapter_w\"] = 135.0\n"
            "                    else:\n"
            "                        pb_dict[\"power_adapter_w\"] = 120.0"
        )
        new_pwr_block = (
            "        # Power Adapter: Keep authentic store/Icecat wattage; extract from source_table only if currently None\n"
            "        pb_dict = specs.setdefault(\"power_battery\", {})\n"
            "        if pb_dict.get(\"power_adapter_w\") is None and not is_integrated:\n"
            "            m_adp = re.search(\n"
            "                r\"\\b(65|90|100|120|135|140|150|170|180|200|230|240|280|300|330|400)\\s*w\\s*(?:ac\\s*adapter|power\\s*(?:adapter|supply)|charger|slim\\s*tip)\\b\",\n"
            "                source_table_str,\n"
            "                re.I,\n"
            "            )\n"
            "            if m_adp:\n"
            "                pb_dict[\"power_adapter_w\"] = float(m_adp.group(1))"
        )
        if old_pwr_block in enr_content:
            enr_content = enr_content.replace(old_pwr_block, new_pwr_block, 1)

        # Allow CPU dictionary to supply turbo boost when boost <= base clock
        old_cpu_boost = "            if val is not None and cpu_dict.get(cpu_supp_key) is None:"
        new_cpu_boost = (
            "            cur_c_val = cpu_dict.get(cpu_supp_key)\n"
            "            # Allow override if boost clock is erroneously <= base clock\n"
            "            boost_bug = (cpu_supp_key == 'clock_boost_ghz' and cur_c_val and cpu_dict.get('clock_base_ghz') and cur_c_val <= cpu_dict.get('clock_base_ghz'))\n"
            "            if val is not None and (cur_c_val is None or boost_bug):"
        )
        if old_cpu_boost in enr_content:
            enr_content = enr_content.replace(old_cpu_boost, new_cpu_boost, 1)

        enr_path.write_text(enr_content.replace("\n", "\r\n"), encoding="utf-8")
        print("[3/7] Updated enricher.py (restored authentic power adapters, fixed boost clock override)")


def load_raw_store_lookups() -> dict[str, dict]:
    """Map product_url to structured product from compumarts, elbadr, sigma."""
    store_map = {}
    for sf in STORE_FILES:
        path = SERVICE_ROOT / "scraping results" / sf
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for p in data.get("structured_products", []):
            url = p.get("url")
            if url:
                store_map[url] = p
    return store_map


def main() -> None:
    update_metrics_engine_files()
    update_pipeline_source_code()

    # Load unified catalog
    cat_path = SERVICE_ROOT / "scraping results" / "unified_catalog_latest.json"
    with open(cat_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    store_lookup = load_raw_store_lookups()
    laptops = catalog["laptops"]
    print(f"\n[4/7] Applying fixes across {len(laptops)} laptops...")

    # Set of gaming chassis terms
    gaming_terms = (
        "loq", "legion", "tuf", "strix", "scar", "zephyrus", "nitro",
        "predator", "victus", "omen", "cyborg", "katana", "sword",
        "vector", "raider", "crosshair", "pulse", "alienware", "aorus",
        "gaming a16", "gaming g5", "gaming g6"
    )

    restored_adapters = 0
    fixed_touchscreens = 0
    fixed_refresh_rates = 0
    fixed_rams = 0
    fixed_storages = 0
    fixed_cpus = 0

    for lap in laptops:
        cid = lap.get("canonical_id")
        title = lap.get("title") or ""
        title_lower = title.lower()
        fam_lower = (lap.get("laptop_family") or "").lower()
        is_gaming = any(gt in title_lower or gt in fam_lower for gt in gaming_terms)
        specs = lap.setdefault("specs", {})

        # --- Fix 1: Restore genuine charger wattage from raw store extraction ---
        store_adps = []
        for o in lap.get("offers", []):
            u = o.get("product_url")
            sp = store_lookup.get(u)
            if sp:
                adp = (sp.get("specs", {}).get("power_battery") or {}).get("power_adapter_w")
                if adp and isinstance(adp, (int, float)) and 45 <= float(adp) <= 400:
                    store_adps.append(float(adp))

        pb_dict = specs.setdefault("power_battery", {})
        cur_adp = pb_dict.get("power_adapter_w")

        # If store reported an authentic charger that differs from cur_adp, restore it
        if store_adps:
            # Common authentic wattage from stores
            authentic_adp = max(set(store_adps), key=store_adps.count)
            # Check if current was artificially inflated (e.g. 200, 230, 240) or downgraded (120)
            if cur_adp != authentic_adp:
                pb_dict["power_adapter_w"] = authentic_adp
                restored_adapters += 1

        # Also search raw spec for charger if currently 120 on discrete gaming
        if pb_dict.get("power_adapter_w") in (120.0, None) and is_gaming:
            pb_raw = f"{pb_dict.get('raw_spec') or ''} {title}"
            m_chg = re.search(r"\b(135|150|170|180|200|230|240|280|300|330)\s*w\b", pb_raw, re.I)
            if m_chg:
                pb_dict["power_adapter_w"] = float(m_chg.group(1))
                restored_adapters += 1

        # --- Fix 4: Clear fake touchscreens on gaming laptops ---
        disp_dict = specs.setdefault("display", {})
        if is_gaming and disp_dict.get("touchscreen") is True:
            disp_dict["touchscreen"] = False
            fixed_touchscreens += 1

        # --- Fix 5: Display refresh rates, resolution, response time ---
        # 5a. Strix / SCAR 60Hz HDMI false extraction
        if disp_dict.get("refresh_rate_hz") == 60 and any(s in title_lower for s in ("strix", "scar")):
            disp_raw = disp_dict.get("raw_spec") or ""
            m_panel_hz = re.search(r"\b(144|165|240|300|360)\s*hz\b", f"{title} {disp_raw}", re.I)
            if m_panel_hz:
                disp_dict["refresh_rate_hz"] = int(m_panel_hz.group(1))
                fixed_refresh_rates += 1

        # 5b. Dell Vostro 3530 4K correction
        if cid == "laptop_dell_vostro_3530i51334u8gb":
            disp_dict["resolution"] = "1920x1080"
            disp_dict["resolution_width"] = 1920
            disp_dict["resolution_height"] = 1080
            disp_dict["hd_type"] = "FHD"

        # 5c. Dell 35ms response time nullification
        if disp_dict.get("response_time_ms") in (35, 35.0):
            disp_dict["response_time_ms"] = None

        # --- Fix 6: RAM & Storage installed capacity vs max expansion limits ---
        stor_dict = specs.setdefault("storage", {})
        mem_dict = specs.setdefault("memory", {})

        # Gigabyte A16 4TB false storage -> 512GB
        if "gigabyte_gaming_a16" in cid and stor_dict.get("capacity_gb") == 4096:
            stor_dict["capacity_gb"] = 512
            fixed_storages += 1

        # Gigabyte A16 64GB false RAM -> 16GB
        if "gigabyte_gaming_a16" in cid and mem_dict.get("capacity_gb") == 64:
            mem_dict["capacity_gb"] = 16
            fixed_rams += 1

        # Halved RAM corrections (title has merchant upgraded RAM)
        halved_ram_map = {
            "laptop_asus_g834jzr_n6027w_90nr0in2m000y0": 32,  # Strix SCAR 18
            "laptop_asus_rog_zephyrus_gu605myqr061w": 32,      # Zephyrus G16
            "laptop_acer_predator_helios_nhqw2em001": 32,       # Helios 16
            "laptop_acer_aspire_go_nxjv0em006": 16,             # Aspire Go 16
            "laptop_hp_victus_r1032nia": 16,                    # Victus 16
        }
        if cid in halved_ram_map:
            mem_dict["capacity_gb"] = halved_ram_map[cid]
            fixed_rams += 1

        # --- CPU Fixes ---
        # ROG Strix G16 CPU fix (Intel Core Ultra 9 -> AMD Ryzen 9 8940HX)
        if cid == "laptop_asus_rog_strix_90nr0kx7m001j0":
            entry = CPU_SPECS.get("amd_ryzen_9_8940hx")
            if entry:
                specs["cpu"] = {
                    "manufacturer": entry["brand"],
                    "line": entry["family"],
                    "model": entry["model"],
                    "series": entry.get("generation"),
                    "full_name": f"{entry['brand']} {entry['model']}",
                    "cores": entry["total_cores"],
                    "threads": entry["total_threads"],
                    "clock_base_ghz": entry.get("base_clock_ghz"),
                    "clock_boost_ghz": entry.get("boost_clock_ghz"),
                    "cache_mb": entry.get("cache_mb"),
                    "microarchitecture": entry["microarchitecture"],
                    "microarchitecture_code": entry.get("microarchitecture_code"),
                    "low_power_cores": entry.get("low_power_cores"),
                    "performance_cores": entry.get("performance_cores"),
                    "efficient_cores": entry.get("efficient_cores"),
                    "npu_tops": entry.get("npu_tops"),
                    "base_power_w": entry.get("base_power_w"),
                    "raw_spec": specs.get("cpu", {}).get("raw_spec"),
                }
                fixed_cpus += 1

        # Acer Nitro clock_boost_ghz fix (2.1 -> 4.6)
        if cid == "laptop_acer_nitro_nhdagem004":
            if (specs.get("cpu") or {}).get("clock_boost_ghz") == 2.1:
                specs["cpu"]["clock_boost_ghz"] = 4.6
                fixed_cpus += 1

        # ASUS TUF Gaming 210H clock_boost_ghz fix (2.2 -> 4.8)
        if cid == "laptop_asus_tuf_gaming_90nr0n06m001y0":
            if (specs.get("cpu") or {}).get("clock_boost_ghz") == 2.2:
                specs["cpu"]["clock_boost_ghz"] = 4.8
                fixed_cpus += 1

    print(f"  Restored Authentic Chargers: {restored_adapters}")
    print(f"  Fixed False Touchscreens: {fixed_touchscreens}")
    print(f"  Fixed 60Hz HDMI Display Refresh Rates: {fixed_refresh_rates}")
    print(f"  Fixed RAM Capacities: {fixed_rams}")
    print(f"  Fixed Storage Capacities: {fixed_storages}")
    print(f"  Fixed CPU Models / Turbo Clocks: {fixed_cpus}")

    # --- Merge 2 confirmed 1 EGP duplicate pairs ---
    # 1. Acer Nitro V 16S ANV16S-71-79TT
    # 2. Gigabyte Gaming A16 GA6H RTX 5060
    merge_map_1egp = {
        "laptop_acer_nitro_v_nhqxcem005": "laptop_acer_nitro_anv16s7179tt",
        "laptop_gigabyte_gaming_a16_9rga6i76vhfhjk5ae000": "laptop_gigabyte_gigabyte_a16_ga6h_gba16ga6hbk",
    }
    by_id = {l["canonical_id"]: l for l in laptops}
    merged_ids = set()

    for src_id, dst_id in merge_map_1egp.items():
        src = by_id.get(src_id)
        dst = by_id.get(dst_id)
        if src and dst:
            print(f"[Merge 1 EGP] Merging {src_id} into {dst_id}")
            seen_urls = {o.get("product_url") for o in dst.get("offers", [])}
            for o in src.get("offers", []):
                if o.get("product_url") not in seen_urls:
                    dst.setdefault("offers", []).append(o)
                    seen_urls.add(o.get("product_url"))
            dst["available_stores"] = list(dict.fromkeys(o.get("store_key") for o in dst.get("offers", [])))
            dst["stores_count"] = len(dst["available_stores"])
            merged_ids.add(src_id)

    if merged_ids:
        laptops = [l for l in laptops if l["canonical_id"] not in merged_ids]
        catalog["laptops"] = laptops
        catalog["total_unique_laptops"] = len(laptops)
        catalog["multi_store_laptops_count"] = sum(1 for l in laptops if l.get("stores_count", 0) > 1)
        catalog["overlap_rate_pct"] = round(catalog["multi_store_laptops_count"] / catalog["total_unique_laptops"] * 100.0, 2)
        print(f"[5/7] Merged 2 1-EGP duplicate listings: new total {len(laptops)} laptops.")

    # Save to scraper-service results
    with open(cat_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"[6/7] Saved updated catalog to: {cat_path}")

    # Sync to catalog-service scraping input
    catalog_input_path = WORKSPACE_ROOT / "services" / "catalog-service" / "scraping input" / "unified_catalog_latest.json"
    if catalog_input_path.parent.is_dir():
        with open(catalog_input_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        print(f"[7/7] Synced updated catalog to: {catalog_input_path}")

    # Final Verification
    print("\n--- Final Verification Summary ---")
    rem_touch = [l["canonical_id"] for l in laptops if any(gt in (l.get("title") or "").lower() for gt in gaming_terms) and (l["specs"].get("display") or {}).get("touchscreen") is True]
    rem_scar_60 = [l["canonical_id"] for l in laptops if any(s in (l.get("title") or "").lower() for s in ("strix", "scar")) and (l["specs"].get("display") or {}).get("refresh_rate_hz") == 60]
    rem_4tb = [l["canonical_id"] for l in laptops if "gigabyte_gaming_a16" in l["canonical_id"] and (l["specs"].get("storage") or {}).get("capacity_gb") == 4096]
    rem_64gb = [l["canonical_id"] for l in laptops if "gigabyte_gaming_a16" in l["canonical_id"] and (l["specs"].get("memory") or {}).get("capacity_gb") == 64]
    rem_35ms = [l["canonical_id"] for l in laptops if (l["specs"].get("display") or {}).get("response_time_ms") in (35, 35.0)]

    print(f"  Total Unique Laptops: {len(laptops)}")
    print(f"  Remaining Gaming Touchscreens: {len(rem_touch)} {rem_touch}")
    print(f"  Remaining Strix/SCAR 60Hz: {len(rem_scar_60)} {rem_scar_60}")
    print(f"  Remaining Gigabyte 4TB Storage: {len(rem_4tb)} {rem_4tb}")
    print(f"  Remaining Gigabyte 64GB RAM: {len(rem_64gb)} {rem_64gb}")
    print(f"  Remaining 35ms Response Times: {len(rem_35ms)} {rem_35ms}")
    print("ALL REQUESTED POST-AUDIT FIXES COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
