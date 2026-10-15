import json
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from pipeline.deterministic import DeterministicExtractor, CANONICAL_BRANDS, CANONICAL_FAMILIES
from pipeline.sanitizer import TextSanitizer
from pipeline.physical_validator import PhysicalValidator
from pipeline.schema import empty_laptop_specifications, ExtractionEnvelope
from scratch.test_router_prototype import TableKeyRouter

# Let's test an updated DeterministicExtractor that uses TableKeyRouter
class RoutedDeterministicExtractor(DeterministicExtractor):
    def __init__(self, alias_dict_path: Optional[Path] = None):
        super().__init__()
        self.router = TableKeyRouter(alias_dict_path)

    def extract(
        self,
        title: str,
        sanitized_table: Dict[str, str],
        sanitized_sections: Dict[str, str],
        cpu_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], List[ExtractionEnvelope]]:
        specs = empty_laptop_specifications()
        envelopes: List[ExtractionEnvelope] = []

        # Route table using alias dictionary
        routed = self.router.route_table(sanitized_table)

        display_sec = self._find_section_context(["display", "screen"], sanitized_sections, sanitized_table)
        gpu_sec = self._find_section_context(["graphics", "gpu", "vga", "video"], sanitized_sections, sanitized_table)
        mem_sec = self._find_section_context(["memory", "ram"], sanitized_sections, sanitized_table)
        storage_sec = self._find_section_context(["storage", "ssd", "hard drive", "hdd"], sanitized_sections, sanitized_table)
        power_sec = self._find_section_context(["battery", "power", "adapter"], sanitized_sections, sanitized_table)
        physical_sec = self._find_section_context(["dimension", "weight", "physical"], sanitized_sections, sanitized_table)
        conn_sec = self._find_section_context(["connectivity", "network", "port", "wireless"], sanitized_sections, sanitized_table)
        audio_sec = self._find_section_context(["audio", "sound", "speaker", "webcam", "camera", "microphone"], sanitized_sections, sanitized_table)
        sec_sec = self._find_section_context(["security", "keyboard", "touchpad", "pointing", "fingerprint"], sanitized_sections, sanitized_table)

        # 1. Identity
        self._extract_identity(title, sanitized_table, specs, envelopes)

        # 2. GPU
        self._extract_gpu(title, sanitized_table, gpu_sec, specs, envelopes, cpu_context)

        # 3. Memory
        self._extract_memory_routed(title, sanitized_table, routed, mem_sec, specs, envelopes, cpu_context)

        # 4. Storage
        self._extract_storage_routed(title, sanitized_table, routed, storage_sec, specs, envelopes)

        # 5. Display
        self._extract_display(title, sanitized_table, display_sec, specs, envelopes)

        # 6. Power & Battery
        self._extract_power(sanitized_table, power_sec, specs, envelopes, cpu_context)

        # 7. Physical
        self._extract_physical_routed(title, sanitized_table, routed, physical_sec, specs, envelopes)

        # 8. Connectivity
        self._extract_connectivity_routed(sanitized_table, routed, conn_sec, specs)

        # 9. Operating System
        self._extract_operating_system(sanitized_table, conn_sec, specs)

        # 10. Build & Security
        self._extract_build_security_routed(title, sanitized_table, routed, sec_sec, specs, envelopes)

        # 11. Audio & Webcam
        self._extract_audio_webcam_routed(sanitized_table, routed, audio_sec, specs, envelopes)

        return specs, envelopes

    def _extract_storage_routed(
        self,
        title: str,
        table: Dict[str, str],
        routed: Dict[str, List[Tuple[str, str]]],
        context: str,
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
    ) -> None:
        storage_rows = routed.get("storage", [])
        storage_text = " ".join(v for _, v in storage_rows).strip()

        if not storage_text:
            for k, v in table.items():
                kl = k.lower()
                if any(s in kl for s in ["storage", "ssd", "hdd", "disk", "hard drive"]) and not any(bad in kl for bad in ["max", "support", "slot", "expansion", "upgrade"]):
                    storage_text += f" {v}"

        primary_text = f"{storage_text} {context}".strip()
        search_targets = [primary_text, title] if primary_text else [title]

        for target in search_targets:
            tb_match = re.search(r"\b([1-4])\s*tb\b", target, re.IGNORECASE)
            if tb_match:
                specs["storage"]["capacity_gb"] = int(tb_match.group(1)) * 1024
                specs["storage"]["storage_type"] = "SSD"
                break

            gb_match = re.search(r"\b(128|256|512)\s*gb\s*(?:ssd|nvme|pcie|emmc)?\b", target, re.IGNORECASE)
            if gb_match:
                specs["storage"]["capacity_gb"] = int(gb_match.group(1))
                specs["storage"]["storage_type"] = "SSD"
                break

        slot_rows = routed.get("storage_slots", [])
        if slot_rows:
            slot_text = " ".join(v for _, v in slot_rows)
            m_sc = re.search(r"\b(\d+)\s*(?:x|slots?)\b|two\s+m\.2", slot_text, re.IGNORECASE)
            if m_sc:
                specs["storage"]["slot_count"] = 2 if "two" in slot_text.lower() else int(m_sc.group(1) or 2)

        if not specs["storage"]["capacity_gb"]:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="storage.capacity_gb",
                    field_description="Primary storage capacity in GB",
                    raw_context=context or primary_text or title,
                    failure_reason="missing_key",
                    expected_type="int",
                    section_name="Storage",
                )
            )

    def _extract_memory_routed(
        self,
        title: str,
        table: Dict[str, str],
        routed: Dict[str, List[Tuple[str, str]]],
        context: str,
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
        cpu_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        mem_rows = routed.get("memory", [])
        mem_text = " ".join(v for _, v in mem_rows).strip()

        if not mem_text:
            for k, v in table.items():
                kl = k.lower()
                if ("ram" in kl or "memory" in kl) and not any(bad in kl for bad in ["graphic", "graphics", "gpu", "vga", "video", "dedicated", "optane", "cache", "rom", "max", "support"]):
                    mem_text += f" {v}"

        primary_text = f"{mem_text} {context}".strip()
        search_targets = [primary_text, title] if primary_text else [title]

        cap_val = None
        for _, v in mem_rows:
            # 1. Multi-DIMM check first! (e.g. 2x 16GB -> 32GB)
            m_dimm = re.search(r"\b(\d+)\s*x\s*(\d+)\s*(?:gb|g)\b", v, re.IGNORECASE)
            if m_dimm:
                count = int(m_dimm.group(1))
                mod_size = int(m_dimm.group(2))
                cand = count * mod_size if count > 1 else mod_size
                valid, cap_clean, _ = PhysicalValidator.validate_memory_capacity(cand, cpu_context)
                if valid:
                    cap_val = cap_clean
                    break

            # 2. Direct leading capacity
            m_direct = re.search(r"^\s*(\d+)\s*(?:gb|g)\b", v, re.IGNORECASE)
            if m_direct:
                cand = int(m_direct.group(1))
                valid, cap_clean, _ = PhysicalValidator.validate_memory_capacity(cand, cpu_context)
                if valid:
                    cap_val = cap_clean
                    break

        if not cap_val:
            for target in search_targets:
                m_dimm = re.search(r"\b(\d+)\s*x\s*(\d+)\s*(?:gb|g)\b", target, re.IGNORECASE)
                if m_dimm:
                    count = int(m_dimm.group(1))
                    mod_size = int(m_dimm.group(2))
                    cand = count * mod_size if count > 1 else mod_size
                    valid, cap_clean, _ = PhysicalValidator.validate_memory_capacity(cand, cpu_context)
                    if valid:
                        cap_val = cap_clean
                        break

                m_ram = re.search(
                    r"\b(\d+)\s*(?:gb|g)\s*(?:\(\s*\d+\s*x\s*\d+\s*(?:gb|g)?\s*\)|(?:ddr[45]|lpddr[45]x?|sodimm|so-dimm|ram|memory|unified))\b",
                    target,
                    re.IGNORECASE,
                )
                if m_ram:
                    cand = int(m_ram.group(1))
                    valid, cap_clean, _ = PhysicalValidator.validate_memory_capacity(cand, cpu_context)
                    if valid:
                        cap_val = cap_clean
                        break

                m_gen = re.search(
                    r"(?<!rtx\s\d{4}\s)(?<!gtx\s\d{4}\s)(?<!rtx\s\d{4}\sti\s)(?<!gtx\s\d{4}\sti\s)\b(\d+)\s*(?:gb|g)\b(?!\s*ssd|\s*hdd|\s*emmc|\s*vram|\s*gddr)",
                    target,
                    re.IGNORECASE,
                )
                if m_gen:
                    cand = int(m_gen.group(1))
                    valid, cap_clean, _ = PhysicalValidator.validate_memory_capacity(cand, cpu_context)
                    if valid:
                        cap_val = cap_clean
                        break

        if cap_val:
            specs["memory"]["capacity_gb"] = cap_val
        else:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="memory.capacity_gb",
                    field_description="RAM capacity in GB",
                    raw_context=context or primary_text or title,
                    failure_reason="missing_key",
                    expected_type="int",
                    cpu_context=cpu_context,
                    section_name="Memory",
                )
            )

        type_targets = [v for _, v in routed.get("memory_type", [])] + search_targets
        for target in type_targets:
            type_match = re.search(r"\b(lpddr5x|lpddr5|lpddr4x|lpddr4|ddr5|ddr4|unified memory)\b", target, re.IGNORECASE)
            if type_match:
                ram_type = type_match.group(1)
                valid, type_clean, _ = PhysicalValidator.validate_memory_type(ram_type, cpu_context)
                if valid:
                    specs["memory"]["memory_type"] = type_clean
                    break

        speed_targets = [v for _, v in routed.get("memory_speed", [])] + [primary_text]
        for target in speed_targets:
            spd_match = re.search(r"\b([4-8]\d{3})\s*(?:mhz|mt/s)\b", target, re.IGNORECASE)
            if spd_match:
                specs["memory"]["speed"] = f"{spd_match.group(1)} MHz"
                break

        slot_rows = routed.get("memory_slots", [])
        if slot_rows:
            slot_text = " ".join(v for _, v in slot_rows)
            m_sl = re.search(r"\b(\d+)\s*(?:sodimm|so-dimm|slots?)\b|two\s+(?:ddr\d|sodimm)", slot_text, re.IGNORECASE)
            if m_sl:
                specs["memory"]["slot_count"] = 2 if "two" in slot_text.lower() else int(m_sl.group(1) or 2)
            elif "soldered" in slot_text.lower():
                specs["memory"]["slot_count"] = 0

        max_mem_rows = routed.get("max_memory", [])
        if max_mem_rows:
            max_text = " ".join(v for _, v in max_mem_rows)
            m_max = re.search(r"\bup\s+to\s*[:\s]*(\d+)\s*(?:gb|g)\b", max_text, re.IGNORECASE)
            if m_max:
                specs["memory"]["max_supported_gb"] = int(m_max.group(1))

    def _extract_connectivity_routed(
        self,
        table: Dict[str, str],
        routed: Dict[str, List[Tuple[str, str]]],
        context: str,
        specs: Dict[str, Any],
    ) -> None:
        full_search = f"{' '.join(table.values())} {context}"

        if re.search(r"\bwi-?fi\s*7\b", full_search, re.IGNORECASE):
            specs["connectivity"]["wifi"] = "Wi-Fi 7"
        elif re.search(r"\bwi-?fi\s*6e\b", full_search, re.IGNORECASE):
            specs["connectivity"]["wifi"] = "Wi-Fi 6E"
        elif re.search(r"\bwi-?fi\s*6\b", full_search, re.IGNORECASE):
            specs["connectivity"]["wifi"] = "Wi-Fi 6"

        bt_match = re.search(r"\bbluetooth\s*(?:v?|version)?\s*(5\.[0-4]|4\.[0-2])\b", full_search, re.IGNORECASE)
        if bt_match:
            specs["connectivity"]["bluetooth"] = f"Bluetooth {bt_match.group(1)}"
        elif re.search(r"\bbt\s*(5\.[0-4]|4\.[0-2])\b", full_search, re.IGNORECASE):
            m_bt = re.search(r"\bbt\s*(5\.[0-4]|4\.[0-2])\b", full_search, re.IGNORECASE)
            specs["connectivity"]["bluetooth"] = f"Bluetooth {m_bt.group(1)}"

        # Ports
        port_rows = routed.get("ports", [])
        ports_list = [v for _, v in port_rows]
        if not ports_list:
            for k, v in table.items():
                kl = k.lower()
                if any(p in kl for p in ["standard ports", "external i/o", "ports", "i/o ports"]):
                    ports_list.append(v)

        if ports_list:
            cleaned_ports = []
            for ports_entry in ports_list:
                if ";" in ports_entry:
                    raw_items = [p.strip() for p in ports_entry.split(";") if p.strip()]
                else:
                    raw_items = [p.strip() for p in re.split(r",\s*(?![^()]*\))", ports_entry) if p.strip()]

                for item in raw_items:
                    p_clean = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", " ", item)
                    p_clean = re.sub(r"\s+", " ", p_clean).strip()
                    if not p_clean or p_clean.lower() in ("none", "n/a", "no", "0"):
                        continue
                    if any(bad in p_clean.lower() for bad in ["all the ports you need", "built to dominate", "connect with ease"]):
                        continue
                    cleaned_ports.append(p_clean)

            if cleaned_ports:
                specs["connectivity"]["ports"] = cleaned_ports

        # Ethernet
        for k, v in table.items():
            kl = k.lower()
            if any(term in kl for term in ["ethernet", "lan", "rj-45", "rj45"]):
                vs = str(v).strip()
                if not any(bad in vs.lower() for bad in ["none", "n/a", "no", "without"]):
                    specs["connectivity"]["ethernet"] = vs
                    break

        if not specs["connectivity"]["ethernet"] and specs["connectivity"]["ports"]:
            for p in specs["connectivity"]["ports"]:
                if re.search(r"\b(rj-?45|ethernet|lan)\b", p, re.IGNORECASE):
                    specs["connectivity"]["ethernet"] = p
                    break

    def _extract_physical_routed(
        self,
        title: str,
        table: Dict[str, str],
        routed: Dict[str, List[Tuple[str, str]]],
        context: str,
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
    ) -> None:
        dim_rows = routed.get("dimensions", [])
        weight_rows = routed.get("weight", [])
        color_rows = routed.get("color", [])

        dim_text = " ".join(v for _, v in dim_rows).strip()
        weight_text = " ".join(v for _, v in weight_rows).strip()
        color_text = " ".join(v for _, v in color_rows).strip()

        if not dim_text or not weight_text or not color_text:
            for k, v in table.items():
                kl = k.lower()
                if not dim_text and any(p in kl for p in ["dimension", "dimensions (wxdxh)", "size"]) and "package" not in kl:
                    dim_text += f" {v}"
                if not weight_text and "weight" in kl and "package" not in kl:
                    weight_text += f" {v}"
                if not color_text and any(p in kl for p in ["color", "case color", "product color"]):
                    color_text += f" {v}"

        full_search = f"{weight_text} {context}"
        wt_match = re.search(r"\b([0-4]\.\d{1,2})\s*kg\b", full_search, re.IGNORECASE)
        if wt_match:
            valid, clean_wt, _ = PhysicalValidator.validate_weight(wt_match.group(1))
            if valid:
                specs["physical"]["weight_kg"] = clean_wt
            else:
                envelopes.append(
                    ExtractionEnvelope(
                        field_path="physical.weight_kg",
                        field_description="Laptop weight in kilograms",
                        raw_context=context or full_search,
                        failure_reason="validation_failed",
                        expected_type="float",
                        section_name="Dimensions & Weight",
                    )
                )

        search_dim = f"{dim_text} {context}"
        w, d, h = self._parse_dimensions_text(search_dim)
        if w and d and h:
            valid, nw, nd, nh, _ = PhysicalValidator.normalize_dimensions(w, d, h)
            if valid:
                specs["physical"]["width_mm"] = nw
                specs["physical"]["depth_mm"] = nd
                specs["physical"]["height_mm"] = nh

        if color_text.strip():
            c_clean = re.sub(r"\(.*?\)", "", color_text).strip()
            c_clean = re.sub(r"\s+", " ", c_clean).strip()
            if c_clean and not any(bad in c_clean.lower() for bad in ["none", "n/a", "no color"]):
                specs["identity"]["color"] = c_clean

        if not specs["identity"]["color"] and title:
            m_col = re.search(
                r"\b(Luna Grey|Mica Silver|Eclipse Gray|Phantom Black|Platinum Silver|Storm Grey|Dark Shadow Gray|Carbon Black|Abyssal Black|Mecha Gray|Natural Silver|Platinum|Black|Silver|Gray|Grey|White|Blue)\b",
                title,
                re.IGNORECASE,
            )
            if m_col:
                specs["identity"]["color"] = m_col.group(1).strip()

    def _extract_build_security_routed(
        self,
        title: str,
        table: Dict[str, str],
        routed: Dict[str, List[Tuple[str, str]]],
        context: str,
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
    ) -> None:
        kb_rows = routed.get("keyboard", [])
        sec_rows = routed.get("security", [])
        pad_rows = routed.get("pointing_device", [])

        # Backlit keyboard
        kb_text = " ".join(v for _, v in kb_rows)
        if kb_text:
            if re.search(r"\b(?:backlit|backlight|rgb|white\s+backlit)\b", kb_text, re.IGNORECASE):
                specs["build_security"]["has_backlit_keyboard"] = True
            elif re.search(r"\b(?:non-backlit|no backlight)\b", kb_text, re.IGNORECASE):
                specs["build_security"]["has_backlit_keyboard"] = False

        if specs["build_security"]["has_backlit_keyboard"] is None and title:
            if re.search(r"\b(?:backlit|backlight|rgb\s+backlit|rgb\s+keyboard)\b", title, re.IGNORECASE):
                specs["build_security"]["has_backlit_keyboard"] = True

        # Fingerprint reader
        sec_text = " ".join(v for _, v in sec_rows)
        for _, vs in sec_rows:
            if re.search(r"\b(?:no\s+fingerprint|without\s+fingerprint)\b", vs, re.IGNORECASE) or vs.strip().lower() in ("no", "none", "n/a"):
                specs["build_security"]["has_fingerprint"] = False
                break
            elif re.search(r"\bfingerprint\b", vs, re.IGNORECASE):
                specs["build_security"]["has_fingerprint"] = True
                break

        # Pointing device
        if pad_rows:
            pad_val = pad_rows[0][1]
            clean_pad = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", " ", pad_val).strip()
            if clean_pad and clean_pad.lower() not in ("none", "n/a"):
                specs["build_security"]["pointing_device"] = clean_pad

        # Security features
        sec_list = []
        for _, vs in sec_rows:
            clean_sec = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", " ", vs).strip()
            if clean_sec and clean_sec.lower() not in ("none", "n/a"):
                sec_list.append(clean_sec)
        if sec_list:
            specs["build_security"]["security_features"] = sec_list

    def _extract_audio_webcam_routed(
        self,
        table: Dict[str, str],
        routed: Dict[str, List[Tuple[str, str]]],
        context: str,
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
    ) -> None:
        cam_rows = routed.get("camera", [])
        audio_rows = routed.get("audio", [])

        # Webcam
        for _, vs in cam_rows:
            m_num = re.search(r"\b(\d{3,4}\s*p|\d+(?:\.\d+)?\s*(?:MP|M\b))\b", vs, re.IGNORECASE)
            if m_num:
                specs["audio_webcam"]["webcam_resolution"] = m_num.group(1).strip()
                break
            m_named = re.search(r"\b(FHD|QHD|UHD|4K|HD)\b", vs, re.IGNORECASE)
            if m_named:
                named_map = {"HD": "720p", "FHD": "1080p", "QHD": "1440p", "UHD": "2160p", "4K": "2160p"}
                specs["audio_webcam"]["webcam_resolution"] = named_map.get(m_named.group(1).upper(), m_named.group(1).upper())
                break

        # Microphone & Speakers
        for _, vs in audio_rows:
            if not specs["audio_webcam"]["microphone"] and re.search(r"\b(?:mic|microphone|array)\b", vs, re.IGNORECASE):
                specs["audio_webcam"]["microphone"] = vs.strip()
            if specs["audio_webcam"]["speaker_count"] is None:
                m_sp = re.search(r"(\d+)\s*(?:x\s*\d+(?:\.\d+)?\s*W|\s*speakers?)", vs, re.IGNORECASE)
                if m_sp:
                    specs["audio_webcam"]["speaker_count"] = int(m_sp.group(1))
                elif re.search(r"\b(?:dual|stereo|two|2x)\b", vs, re.IGNORECASE):
                    specs["audio_webcam"]["speaker_count"] = 2
                elif re.search(r"\b(?:quad|four|4x)\b", vs, re.IGNORECASE):
                    specs["audio_webcam"]["speaker_count"] = 4


if __name__ == "__main__":
    extractor = RoutedDeterministicExtractor()
    sanitizer = TextSanitizer()
    catalog_path = Path("tests/fixtures/compumarts_138_raw_catalog.json")
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    products = catalog["products"]
    t0 = time.time()
    field_counts = {
        "brand": 0, "gpu_model": 0, "ram": 0, "storage": 0, "display": 0,
        "os": 0, "ports": 0, "weight": 0, "dimensions": 0, "webcam": 0,
        "backlit_kb": 0, "speakers": 0
    }

    # Tracking storage fixes
    storage_512_count = 0
    ram_32_count = 0

    for p in products:
        table = {r["label"]: r["value"] for r in p.get("spec_rows", [])}
        clean_table = sanitizer.sanitize_table(table)
        title = sanitizer.clean_text(p["title"])
        specs, envelopes = extractor.extract(title=title, sanitized_table=clean_table, sanitized_sections={})

        if specs["identity"]["brand"]: field_counts["brand"] += 1
        if specs["gpu"]["model"]: field_counts["gpu_model"] += 1
        if specs["memory"]["capacity_gb"]: field_counts["ram"] += 1
        if specs["storage"]["capacity_gb"]: field_counts["storage"] += 1
        if specs["display"]["size_inches"]: field_counts["display"] += 1
        if specs["operating_system"]["name"]: field_counts["os"] += 1
        if specs["connectivity"]["ports"]: field_counts["ports"] += 1
        if specs["physical"]["weight_kg"]: field_counts["weight"] += 1
        if specs["physical"]["width_mm"]: field_counts["dimensions"] += 1
        if specs["audio_webcam"]["webcam_resolution"]: field_counts["webcam"] += 1
        if specs["build_security"]["has_backlit_keyboard"] is not None: field_counts["backlit_kb"] += 1
        if specs["audio_webcam"]["speaker_count"]: field_counts["speakers"] += 1

        if specs["storage"]["capacity_gb"] == 512:
            storage_512_count += 1
        if specs["memory"]["capacity_gb"] == 32:
            ram_32_count += 1

    elapsed = time.time() - t0
    print(f"Processed {len(products)} laptops in {elapsed:.3f}s")
    for k, v in field_counts.items():
        print(f"  {k:15}: {v}/{len(products)} ({v/len(products)*100:.1f}%)")
    print(f"\nStorage 512GB laptops detected: {storage_512_count}")
    print(f"RAM 32GB laptops detected: {ram_32_count}")

