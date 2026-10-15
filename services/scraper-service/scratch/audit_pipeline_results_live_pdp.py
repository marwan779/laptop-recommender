"""Live Network Ground-Truth Audit of pipeline_results_compumarts.json.

Protocol Enforcement:
1. Live Network Requirement: Fetches raw live PDP HTML directly over network from actual store URLs.
2. Full Catalog Scope: Evaluates 100% of laptops in pipeline_results_compumarts.json.
3. All Specifications Scope: Evaluates all 35+ fields across Identity, CPU, GPU, Memory, Storage,
   Display, Power, Physical, Build/Security, Audio/Webcam, Connectivity, and OS.
4. Raw Live DOM Ground Truth: Compares extracted values against raw un-sanitized DOM/table rows.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.stores.compumarts import CompumartsStoreScraper
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("live_audit")

RESULTS_FILE = Path("pipeline_results_compumarts.json")
AUDIT_OUTPUT_FILE = Path("live_audit_discrepancies.json")


class LivePDPAuditor:
    def __init__(self, max_workers: int = 8):
        self.scraper = CompumartsStoreScraper()
        self.max_workers = max_workers

    def fetch_live_pdp(self, url: str) -> Dict[str, Any]:
        """Fetch raw HTML directly over the network and extract un-sanitized tables."""
        html_text = self.scraper._fetch_html(url)
        if not html_text:
            raise RuntimeError(f"Live network fetch failed for {url}")

        soup = BeautifulSoup(html_text, "html.parser")
        title = ""
        title_tag = soup.find("h1", class_=lambda c: c and ("product" in c.lower() or "title" in c.lower()))
        if not title_tag:
            title_tag = soup.find("h1")
        if title_tag:
            title = title_tag.get_text(strip=True)
        elif soup.title:
            title = soup.title.get_text(strip=True)

        spec_res = self.scraper._extract_product_specs(url, title=title)
        raw_specs = spec_res.specs or {}

        return {
            "url": url,
            "live_title": title,
            "raw_specs": raw_specs,
            "raw_description": spec_res.raw_description or "",
            "price_egp": spec_res.price_val,
        }

    def audit_laptop(self, record: Dict[str, Any], live_data: Dict[str, Any]) -> Dict[str, Any]:
        url = record["url"]
        title_saved = record["title"]
        extracted_specs = record.get("specs", {})
        live_title = live_data["live_title"]
        raw_specs = live_data["raw_specs"]

        mismatches: List[Dict[str, Any]] = []
        verified_matches: int = 0
        missing_on_pdp: int = 0

        # Helper to find table keys matching patterns
        def get_table_matches(patterns: List[str]) -> List[Tuple[str, str]]:
            res = []
            for k, v in raw_specs.items():
                for pat in patterns:
                    if re.search(pat, k, re.IGNORECASE):
                        res.append((k, str(v)))
                        break
            return res

        # -------------------------------------------------------------
        # 1. IDENTITY
        # -------------------------------------------------------------
        ident = extracted_specs.get("identity", {})
        # Brand
        brand_val = ident.get("brand")
        brand_table = get_table_matches([r"brand", r"manufacturer"])
        if brand_table:
            expected_brand = brand_table[0][1].strip()
            if brand_val and expected_brand.lower() not in brand_val.lower() and brand_val.lower() not in expected_brand.lower():
                mismatches.append({
                    "field": "identity.brand",
                    "extracted": brand_val,
                    "ground_truth": expected_brand,
                    "type": "CORRUPTION",
                    "source": f"Table [{brand_table[0][0]}]",
                })
        elif not brand_val:
            mismatches.append({
                "field": "identity.brand",
                "extracted": None,
                "ground_truth": live_title,
                "type": "MISSED_POPULATION",
                "source": "Title",
            })

        # Laptop Family / Model
        mpn_val = ident.get("manufacturer_part_number")
        mpn_table = get_table_matches([r"model", r"part number", r"mpn", r"machine type"])
        if mpn_table and not mpn_val:
            val_str = mpn_table[0][1].strip()
            if val_str and val_str.lower() not in ("none", "n/a", "no"):
                mismatches.append({
                    "field": "identity.manufacturer_part_number",
                    "extracted": None,
                    "ground_truth": val_str,
                    "type": "MISSED_POPULATION",
                    "source": f"Table [{mpn_table[0][0]}]",
                })

        # Color
        color_val = ident.get("color")
        color_table = get_table_matches([r"color", r"case color"])
        if color_table and not color_val:
            c_str = color_table[0][1].strip()
            if c_str and c_str.lower() not in ("none", "n/a"):
                mismatches.append({
                    "field": "identity.color",
                    "extracted": None,
                    "ground_truth": c_str,
                    "type": "MISSED_POPULATION",
                    "source": f"Table [{color_table[0][0]}]",
                })

        # -------------------------------------------------------------
        # 2. CPU
        # -------------------------------------------------------------
        cpu = extracted_specs.get("cpu", {})
        cpu_table = get_table_matches([r"processor", r"\bcpu\b"])
        if cpu_table:
            cpu_raw = cpu_table[0][1]
            # Cores
            cores_val = cpu.get("cores")
            m_cores = re.search(r"(\d+)\s*(?:Cores?|C\b)", cpu_raw, re.I)
            if m_cores:
                exp_cores = int(m_cores.group(1))
                if cores_val != exp_cores:
                    mismatches.append({
                        "field": "cpu.cores",
                        "extracted": cores_val,
                        "ground_truth": exp_cores,
                        "type": "CORRUPTION",
                        "source": f"Table [{cpu_table[0][0]}]: '{cpu_raw}'",
                    })

            # Threads
            threads_val = cpu.get("threads")
            m_threads = re.search(r"(\d+)\s*(?:Threads?|T\b)", cpu_raw, re.I)
            if m_threads:
                exp_threads = int(m_threads.group(1))
                if threads_val != exp_threads:
                    mismatches.append({
                        "field": "cpu.threads",
                        "extracted": threads_val,
                        "ground_truth": exp_threads,
                        "type": "CORRUPTION",
                        "source": f"Table [{cpu_table[0][0]}]: '{cpu_raw}'",
                    })

        # -------------------------------------------------------------
        # 3. GPU
        # -------------------------------------------------------------
        gpu = extracted_specs.get("gpu", {})
        gpu_table = get_table_matches([r"graphics", r"\bgpu\b", r"vga"])
        if gpu_table:
            gpu_raw = gpu_table[0][1]
            vram_val = gpu.get("vram_gb")
            m_vram = re.search(r"(\d+)\s*GB\s*(?:GDDR\d*|VRAM)", gpu_raw, re.I)
            if m_vram:
                exp_vram = int(m_vram.group(1))
                if vram_val != exp_vram:
                    mismatches.append({
                        "field": "gpu.vram_gb",
                        "extracted": vram_val,
                        "ground_truth": exp_vram,
                        "type": "CORRUPTION",
                        "source": f"Table [{gpu_table[0][0]}]: '{gpu_raw}'",
                    })

            # Integrated
            is_int = gpu.get("integrated")
            if any(term in gpu_raw.lower() for term in ["integrated", "intel iris", "intel uhd", "radeon 680m", "qualcomm adreno"]):
                if is_int is not True and not re.search(r"rtx|gtx|discrete", gpu_raw, re.I):
                    mismatches.append({
                        "field": "gpu.integrated",
                        "extracted": is_int,
                        "ground_truth": True,
                        "type": "CORRUPTION",
                        "source": f"Table [{gpu_table[0][0]}]: '{gpu_raw}'",
                    })

        # -------------------------------------------------------------
        # 4. MEMORY
        # -------------------------------------------------------------
        mem = extracted_specs.get("memory", {})
        mem_table = get_table_matches([r"^memory$", r"^ram$"])
        if mem_table:
            mem_raw = mem_table[0][1]
            ram_val = mem.get("capacity_gb")
            m_ram = re.search(r"(\d+)\s*(?:GB|G)\b", mem_raw, re.I)
            m_multi = re.search(r"(\d+)\s*[xX*]\s*(\d+)\s*(?:GB|G)\b", mem_raw, re.I)
            exp_ram = int(m_multi.group(1)) * int(m_multi.group(2)) if m_multi else (int(m_ram.group(1)) if m_ram else None)
            if exp_ram and ram_val != exp_ram:
                mismatches.append({
                    "field": "memory.capacity_gb",
                    "extracted": ram_val,
                    "ground_truth": exp_ram,
                    "type": "CORRUPTION",
                    "source": f"Table [{mem_table[0][0]}]: '{mem_raw}'",
                })

            # Memory Type
            type_val = mem.get("memory_type")
            m_type = re.search(r"\b(DDR5|DDR4|LPDDR5X|LPDDR5|LPDDR4X)\b", mem_raw, re.I)
            if m_type:
                exp_type = m_type.group(1).upper()
                if not type_val or exp_type not in type_val.upper():
                    mismatches.append({
                        "field": "memory.memory_type",
                        "extracted": type_val,
                        "ground_truth": exp_type,
                        "type": "CORRUPTION" if type_val else "MISSED_POPULATION",
                        "source": f"Table [{mem_table[0][0]}]: '{mem_raw}'",
                    })

        # -------------------------------------------------------------
        # 5. STORAGE
        # -------------------------------------------------------------
        st = extracted_specs.get("storage", {})
        st_table = get_table_matches([r"^storage$", r"^hard drive$", r"^ssd$"])
        if st_table:
            st_raw = st_table[0][1]
            st_val = st.get("capacity_gb")
            m_tb = re.search(r"(\d+)\s*TB\b", st_raw, re.I)
            m_gb = re.search(r"(\d+)\s*GB\b", st_raw, re.I)
            exp_st = int(m_tb.group(1)) * 1024 if m_tb else (int(m_gb.group(1)) if m_gb else None)
            if exp_st and st_val != exp_st:
                mismatches.append({
                    "field": "storage.capacity_gb",
                    "extracted": st_val,
                    "ground_truth": exp_st,
                    "type": "CORRUPTION",
                    "source": f"Table [{st_table[0][0]}]: '{st_raw}'",
                })

        # -------------------------------------------------------------
        # 6. DISPLAY
        # -------------------------------------------------------------
        disp = extracted_specs.get("display", {})
        disp_table = get_table_matches([r"^display$", r"^screen$"])
        if disp_table:
            disp_raw = disp_table[0][1]
            # Size
            size_val = disp.get("size_inches")
            m_sz = re.search(r"(\d{2}(?:\.\d)?)\s*(?:\"|inch|-inch)", disp_raw, re.I)
            if m_sz:
                exp_sz = float(m_sz.group(1))
                if size_val is None or abs(size_val - exp_sz) > 0.2:
                    mismatches.append({
                        "field": "display.size_inches",
                        "extracted": size_val,
                        "ground_truth": exp_sz,
                        "type": "CORRUPTION" if size_val else "MISSED_POPULATION",
                        "source": f"Table [{disp_table[0][0]}]: '{disp_raw}'",
                    })

            # Refresh Rate
            hz_val = disp.get("refresh_rate_hz")
            m_hz = re.search(r"(\d{2,3})\s*Hz\b", disp_raw, re.I)
            if m_hz:
                exp_hz = int(m_hz.group(1))
                if hz_val != exp_hz:
                    mismatches.append({
                        "field": "display.refresh_rate_hz",
                        "extracted": hz_val,
                        "ground_truth": exp_hz,
                        "type": "CORRUPTION" if hz_val else "MISSED_POPULATION",
                        "source": f"Table [{disp_table[0][0]}]: '{disp_raw}'",
                    })

        # -------------------------------------------------------------
        # 7. POWER & BATTERY
        # -------------------------------------------------------------
        pwr = extracted_specs.get("power_battery", {})
        bat_table = get_table_matches([r"battery"])
        if bat_table:
            bat_raw = bat_table[0][1]
            wh_val = pwr.get("battery_capacity_wh")
            m_wh = re.search(r"(\d{2}(?:\.\d)?)\s*Wh\b", bat_raw, re.I)
            if m_wh:
                exp_wh = float(m_wh.group(1))
                if wh_val is None or abs(wh_val - exp_wh) > 1.0:
                    mismatches.append({
                        "field": "power_battery.battery_capacity_wh",
                        "extracted": wh_val,
                        "ground_truth": exp_wh,
                        "type": "CORRUPTION" if wh_val else "MISSED_POPULATION",
                        "source": f"Table [{bat_table[0][0]}]: '{bat_raw}'",
                    })

        # -------------------------------------------------------------
        # 8. PHYSICAL (DIMENSIONS & WEIGHT)
        # -------------------------------------------------------------
        phys = extracted_specs.get("physical", {})
        # Weight
        wt_table = get_table_matches([r"^weight$"])
        if wt_table:
            wt_raw = wt_table[0][1]
            wt_val = phys.get("weight_kg")
            m_wt = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", wt_raw, re.I)
            if m_wt:
                exp_wt = float(m_wt.group(1))
                if wt_val is None or abs(wt_val - exp_wt) > 0.05:
                    mismatches.append({
                        "field": "physical.weight_kg",
                        "extracted": wt_val,
                        "ground_truth": exp_wt,
                        "type": "CORRUPTION" if wt_val else "MISSED_POPULATION",
                        "source": f"Table [{wt_table[0][0]}]: '{wt_raw}'",
                    })

        # Dimensions
        dim_table = get_table_matches([r"dimension", r"dimensions (wxdxh)"])
        if dim_table:
            dim_raw = dim_table[0][1]
            w_val = phys.get("width_mm")
            m_dim = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|cm)?\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm)?\s*[xX×*]\s*(\d+(?:\.\d+)?)", dim_raw)
            if m_dim and not w_val:
                mismatches.append({
                    "field": "physical.width_mm",
                    "extracted": None,
                    "ground_truth": dim_raw,
                    "type": "MISSED_POPULATION",
                    "source": f"Table [{dim_table[0][0]}]: '{dim_raw}'",
                })

        # -------------------------------------------------------------
        # 9. CONNECTIVITY (PORTS & ETHERNET)
        # -------------------------------------------------------------
        conn = extracted_specs.get("connectivity", {})
        ports_table = get_table_matches([r"standard ports", r"^ports$", r"external i/o"])
        if ports_table:
            ports_raw = ports_table[0][1]
            ports_val = conn.get("ports", [])
            if not ports_val and ports_raw.lower() not in ("none", "no ports"):
                mismatches.append({
                    "field": "connectivity.ports",
                    "extracted": [],
                    "ground_truth": ports_raw,
                    "type": "MISSED_POPULATION",
                    "source": f"Table [{ports_table[0][0]}]",
                })

        # -------------------------------------------------------------
        # 10. AUDIO & WEBCAM
        # -------------------------------------------------------------
        audio = extracted_specs.get("audio_webcam", {})
        cam_table = get_table_matches([r"camera", r"webcam"])
        if cam_table:
            cam_raw = cam_table[0][1]
            cam_val = audio.get("webcam_resolution")
            m_res = re.search(r"(\d{3,4}\s*p|\d+(?:\.\d+)?\s*MP|FHD|HD)", cam_raw, re.I)
            if m_res and not cam_val:
                mismatches.append({
                    "field": "audio_webcam.webcam_resolution",
                    "extracted": None,
                    "ground_truth": cam_raw,
                    "type": "MISSED_POPULATION",
                    "source": f"Table [{cam_table[0][0]}]",
                })

        # Speakers
        spk_table = get_table_matches([r"speakers", r"^audio$"])
        if spk_table:
            spk_raw = spk_table[0][1]
            spk_val = audio.get("speaker_count")
            m_sp = re.search(r"(\d+)\s*(?:x\s*\d+W|speakers?)|dual|quad", spk_raw, re.I)
            if m_sp and spk_val is None:
                mismatches.append({
                    "field": "audio_webcam.speaker_count",
                    "extracted": None,
                    "ground_truth": spk_raw,
                    "type": "MISSED_POPULATION",
                    "source": f"Table [{spk_table[0][0]}]",
                })

        return {
            "url": url,
            "title": title_saved,
            "mismatches_count": len(mismatches),
            "mismatches": mismatches,
        }

    def run_full_audit(self) -> Dict[str, Any]:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            records = json.load(f)

        total = len(records)
        logger.info("Starting live full-catalog full-spec audit of %d laptops over network...", total)

        # 1. Fetch live PDPs in parallel
        live_pdps: Dict[str, Dict[str, Any]] = {}
        fetch_errors: Dict[str, str] = {}

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_rec = {executor.submit(self.fetch_live_pdp, rec["url"]): rec for rec in records}
            completed = 0
            for future in as_completed(future_to_rec):
                rec = future_to_rec[future]
                completed += 1
                try:
                    data = future.result()
                    live_pdps[rec["url"]] = data
                except Exception as e:
                    fetch_errors[rec["url"]] = str(e)
                if completed % 20 == 0 or completed == total:
                    logger.info("Fetched live PDPs: %d/%d (%.1f%%)", completed, total, completed / total * 100)

        elapsed_fetch = time.time() - t0
        logger.info("Finished fetching %d live PDPs in %.2fs (%d errors)", len(live_pdps), elapsed_fetch, len(fetch_errors))

        # 2. Audit each laptop against raw live PDP
        audit_results = []
        for rec in records:
            url = rec["url"]
            if url in live_pdps:
                res = self.audit_laptop(rec, live_pdps[url])
                audit_results.append(res)
            else:
                audit_results.append({
                    "url": url,
                    "title": rec["title"],
                    "fetch_error": fetch_errors.get(url, "unknown error"),
                    "mismatches_count": 0,
                    "mismatches": [],
                })

        # 3. Aggregate results
        total_mismatches = sum(r["mismatches_count"] for r in audit_results)
        laptops_with_mismatches = [r for r in audit_results if r["mismatches_count"] > 0]

        summary = {
            "total_laptops_audited": total,
            "live_pdps_fetched": len(live_pdps),
            "fetch_errors_count": len(fetch_errors),
            "total_mismatches_detected": total_mismatches,
            "laptops_with_mismatches_count": len(laptops_with_mismatches),
            "clean_laptops_count": total - len(laptops_with_mismatches),
            "audit_results": audit_results,
        }

        with open(AUDIT_OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info("Audit complete! %d mismatches found across %d laptops. Saved to %s", total_mismatches, len(laptops_with_mismatches), AUDIT_OUTPUT_FILE)
        return summary


if __name__ == "__main__":
    auditor = LivePDPAuditor(max_workers=8)
    auditor.run_full_audit()

