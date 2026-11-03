#!/usr/bin/env python3
"""Standalone Patch Script: Applies the final 100% verification fixes to unified_catalog_latest.json

1. Merges the 8 duplicate multi-store laptop pairs (reducing 304 -> 295 unique laptops, increasing multi-store to 54).
2. Fixes the 11 misparsed/missing power_adapter_w values.
3. Fixes the 4 single-record spec discrepancies (Acer Nitro DDR4, Dell Pro i7-1355U, Zenbook non-touch, Vivobook boost clock).
4. Caps defaulted GPU TGP on low-wattage chassis (120W/135W/150W adapters).
5. Populates all 34 missing laptop_family fields and clarifies generic laptop_model names for YouTube/Reddit review lookup.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys


def apply_fixes(input_path: str | Path, output_path: str | Path) -> None:
    with open(input_path, encoding="utf-8") as f:
        cat = json.load(f)

    laps = copy.deepcopy(cat["laptops"])
    lap_map = {l["canonical_id"]: l for l in laps}

    # 1. Merge the 8 duplicate groups (9 secondary records)
    merges = [
        ("laptop_asus_rog_strix_g614phrv161w", "laptop_asus_rog_strix_90nr0kx7m001j0"),
        ("laptop_lenovo_loq_83dv01hsed", "laptop_lenovo_83dv01hsed_199274705176"),
        ("laptop_asus_tuf_gaming_90nr0mc1m008a0", "laptop_asus_tuf_a16fa608pmrv659w"),
        ("laptop_asus_tuf_gaming_a16_90nr0ks1m00df0", "laptop_asus_tuf_gaming_a16fa608uhitu657w"),
        ("laptop_asus_tuf_gaming_a16_90nr0ks1m00df0", "laptop_asus_tuf_gaming_90nr0ks1m005p0"),
        ("laptop_asus_vivobook_16_x1607aamb155w", "laptop_asus_vivobook_16x1607aamb155w"),
        ("laptop_acer_nitro_v_nhqxdem003", "laptop_acer_nitro_v16sanv16s7176pu"),
        ("laptop_gigabyte_gaming_a16_gaminga16cthi3eg893sd", "laptop_gigabyte_gaming_a16_i7_13620h_rtx5050"),
        ("laptop_dell_alienware_oan1625000801mino5", "laptop_generic_16_aurora_ac1620_16auroraac1620506032gb"),
    ]

    removed_ids = set()
    for primary_id, secondary_id in merges:
        if primary_id in lap_map and secondary_id in lap_map:
            p = lap_map[primary_id]
            s = lap_map[secondary_id]
            existing_urls = {o["product_url"] for o in p["offers"]}
            for o in s["offers"]:
                if o["product_url"] not in existing_urls:
                    p["offers"].append(o)
                    existing_urls.add(o["product_url"])
            valid_offers = [
                o
                for o in p["offers"]
                if o.get("is_valid_price") and o.get("in_stock") and (o.get("price_egp") or 0) >= 5000
            ]
            if valid_offers:
                prices_by_store = {}
                for o in valid_offers:
                    sk = o["store_key"]
                    if sk not in prices_by_store or o["price_egp"] < prices_by_store[sk]:
                        prices_by_store[sk] = o["price_egp"]
                p["prices_by_store"] = prices_by_store
                p["available_stores"] = list(prices_by_store.keys())
                p["stores_count"] = len(p["available_stores"])
                p["min_price_egp"] = min(prices_by_store.values())
                p["max_price_egp"] = max(o["price_egp"] for o in valid_offers)
                p["cheapest_store"] = min(prices_by_store, key=prices_by_store.get)
                p["price_spread_egp"] = round(p["max_price_egp"] - p["min_price_egp"], 2)
            removed_ids.add(secondary_id)

    laps = [l for l in laps if l["canonical_id"] not in removed_ids]
    lap_map = {l["canonical_id"]: l for l in laps}

    # 2. Fix the 11 wrong/missing power_adapter_w values
    adapter_fixes = {
        "laptop_msi_raider_9s7182462689": 330.0,
        "laptop_asus_rog_strix_scar_90nr0ld1m00710": 330.0,
        "laptop_hp_victus_15_15fa1035ne": 200.0,
        "laptop_lenovo_loq_83dv00uudp": 230.0,
        "laptop_acer_nitro_nhdacem003": 135.0,
        "laptop_acer_nitro_nhdagem004": 135.0,
        "laptop_acer_nitro_nl1671g53a0": 135.0,
        "laptop_asus_vivobook_90nb10n2m02t30": 90.0,
        "laptop_asus_vivobook_go_e1504fabq5855w": 45.0,
        "laptop_hp_2e9j0ea_2e9j0ea": 45.0,
        "laptop_lenovo_thinkpad_621m7s1nd00": 65.0,
    }
    for cid, w in adapter_fixes.items():
        if cid in lap_map:
            lap_map[cid]["specs"]["power_battery"]["power_adapter_w"] = w

    # 3. Fix the 4 single-record hardware discrepancies
    if "laptop_acer_nitro_v_nhqz9em002" in lap_map:
        lap_map["laptop_acer_nitro_v_nhqz9em002"]["specs"]["memory"]["memory_type"] = "DDR4"
        lap_map["laptop_acer_nitro_v_nhqz9em002"]["specs"]["memory"]["speed"] = "3200 MHz"
    if "laptop_dell_pro_15_5v7dg94" in lap_map:
        lap_map["laptop_dell_pro_15_5v7dg94"]["specs"]["cpu"]["model"] = "Core i7-1355U"
        lap_map["laptop_dell_pro_15_5v7dg94"]["specs"]["cpu"]["full_name"] = "Intel Core i7-1355U"
        lap_map["laptop_dell_pro_15_5v7dg94"]["specs"]["cpu"]["line"] = "Core i7"
        lap_map["laptop_dell_pro_15_5v7dg94"]["specs"]["cpu"]["clock_boost_ghz"] = 5.0
    if "laptop_asus_zenbook_90nb14w2m009u0" in lap_map:
        lap_map["laptop_asus_zenbook_90nb14w2m009u0"]["specs"]["display"]["touchscreen"] = False
    if "laptop_asus_vivobook_90nb14r2m00270" in lap_map:
        lap_map["laptop_asus_vivobook_90nb14r2m00270"]["specs"]["cpu"]["clock_boost_ghz"] = 3.8

    # 4. Cap defaulted GPU TGP on low-wattage chassis
    for l in laps:
        s = l["specs"]
        if s["gpu"]["integrated"]:
            continue
        t_low = (l["title"] + " " + (l.get("laptop_family") or "")).lower()
        ad = s["power_battery"].get("power_adapter_w") or 180
        tdp = s["gpu"].get("tdp_w") or 0
        if ad <= 120 and tdp > 50:
            s["gpu"]["tdp_w"] = 45 if ("msi" in t_low) else 50
        elif any(k in t_low for k in ["loq essential", "15iax9e", "15arp10e", "nitro lite", "nl16"]) and tdp > 65:
            s["gpu"]["tdp_w"] = 65
        elif ad <= 135 and tdp > 75:
            s["gpu"]["tdp_w"] = 75
        elif ad <= 150 and tdp > 85:
            s["gpu"]["tdp_w"] = 85

    # 5. Populate missing laptop_family and clarify generic laptop_model
    for l in laps:
        fam = l.get("laptop_family") or l["specs"]["identity"].get("laptop_family")
        t_low = l["title"].lower()
        if not fam:
            if "alienware" in t_low or "aurora" in t_low:
                fam = "Alienware"
            elif "aorus" in t_low or "master 16" in t_low:
                fam = "Aorus"
            elif "dell pro" in t_low:
                fam = "Dell Pro"
            elif "latitude" in t_low or "3510" in t_low:
                fam = "Latitude"
            elif "vostro" in t_low:
                fam = "Vostro"
            elif "inspiron" in t_low:
                fam = "Inspiron"
            elif "g15" in t_low:
                fam = "G15"
            elif "strix scar" in t_low:
                fam = "Rog Strix Scar"
            elif "rog strix" in t_low:
                fam = "Rog Strix"
            elif "zephyrus" in t_low:
                fam = "Rog Zephyrus"
            elif "tuf" in t_low or "fx608" in t_low or "fa608" in t_low or "fa506" in t_low:
                fam = "Tuf Gaming"
            elif "vivobook" in t_low or "e203" in t_low:
                fam = "Vivobook"
            elif "zenbook" in t_low:
                fam = "Zenbook"
            elif "expertbook" in t_low:
                fam = "Expertbook"
            elif "legion" in t_low:
                fam = "Legion"
            elif "loq" in t_low:
                fam = "Loq"
            elif "ideapad" in t_low or "gaming 3" in t_low:
                fam = "Ideapad"
            elif "thinkpad" in t_low:
                fam = "Thinkpad"
            elif "victus" in t_low:
                fam = "Victus"
            elif "omen" in t_low:
                fam = "Omen"
            elif "probook" in t_low:
                fam = "Probook"
            elif (
                "250 g" in t_low
                or "255 g" in t_low
                or "15-fd" in t_low
                or "15-fc" in t_low
                or "gw0054" in t_low
            ):
                fam = "HP Essential"
            elif "g6x" in t_low or "g6 " in t_low or "g5 " in t_low:
                fam = "Gigabyte G-Series"
            elif "gaming a16" in t_low or "ga6" in t_low:
                fam = "Gaming A16"
            elif "aero" in t_low:
                fam = "Aero"
            elif "nitro" in t_low:
                fam = "Nitro"
            elif "predator" in t_low:
                fam = "Predator"
            elif "aspire" in t_low:
                fam = "Aspire"
            elif "travelmate" in t_low:
                fam = "Travelmate"
            else:
                fam = l.get("brand", "Laptop")
        l["laptop_family"] = fam
        l["specs"]["identity"]["laptop_family"] = fam

        mod = str(l.get("laptop_model") or "")
        if len(mod) <= 4 or mod.lower() in ["loq", "tuf", "aero", "envy", "hp", "g10", "v16"]:
            t_clean = l["title"].split(" - ")[0].split(" – ")[0].split(" — ")[0].strip()
            l["laptop_model"] = t_clean[:60]
            l["specs"]["identity"]["laptop_model"] = t_clean[:60]

    cat["laptops"] = laps
    cat["total_unique_laptops"] = len(laps)
    cat["multi_store_laptops_count"] = sum(1 for l in laps if l.get("stores_count", 0) >= 2)
    cat["overlap_rate_pct"] = round(cat["multi_store_laptops_count"] / len(laps) * 100, 2)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cat, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(laps)} laptops ({cat['multi_store_laptops_count']} multi-store) to {output_path}")


if __name__ == "__main__":
    in_file = sys.argv[1] if len(sys.argv) > 1 else "unified_catalog_latest.json"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "unified_catalog_final_v6.json"
    apply_fixes(in_file, out_file)
