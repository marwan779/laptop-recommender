"""Layer 4: Deterministic Extractor Layer.

Extracts hardware specifications using dictionary tables and precision regex.
Any field that is missing, ambiguous, or fails physical validation is packaged
into an ExtractionEnvelope (using Section-Level context per Option B)
to be processed by the AI fallback layer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.pipeline.gpu_anchor import GPUAnchorExtractor
from app.pipeline.physical_validator import PhysicalValidator
from app.pipeline.schema import ExtractionEnvelope, empty_laptop_specifications

CANONICAL_BRANDS = {
    "asus": "ASUS",
    "acer": "Acer",
    "dell": "Dell",
    "hp": "HP",
    "lenovo": "Lenovo",
    "msi": "MSI",
    "gigabyte": "Gigabyte",
    "apple": "Apple",
    "razer": "Razer",
    "samsung": "Samsung",
    "huawei": "Huawei",
    "microsoft": "Microsoft",
}

CANONICAL_FAMILIES: dict[str, list[str]] = {
    "HP": [
        "Victus",
        "Omen Transcend",
        "Omen",
        "Pavilion Plus",
        "Pavilion Aero",
        "Pavilion",
        "Envy x360",
        "Envy",
        "Spectre x360",
        "Spectre",
        "ProBook",
        "EliteBook",
        "ZBook",
        "Essential",
        "250",
        "255",
        "15s",
        "14s",
        "15-fd",
        "15-fc",
        "15-da",
        "15-dw",
        "14-ep",
    ],
    "Lenovo": [
        "Legion Pro",
        "Legion Slim",
        "Legion",
        "LOQ Essential",
        "LOQ",
        "IdeaPad Pro",
        "IdeaPad Slim",
        "IdeaPad Gaming",
        "IdeaPad Flex",
        "IdeaPad",
        "ThinkPad P",
        "ThinkPad X",
        "ThinkPad T",
        "ThinkPad E",
        "ThinkPad L",
        "ThinkPad",
        "ThinkBook",
        "Yoga Slim",
        "Yoga Pro",
        "Yoga",
        "Slim",
        "V15",
        "V14",
    ],
    "Dell": [
        "Alienware",
        "XPS",
        "Inspiron 16 Plus",
        "Inspiron",
        "Vostro",
        "Latitude",
        "Precision",
        "G15",
        "G16",
        "Pro 15",
    ],
    "ASUS": [
        "ROG Strix SCAR",
        "ROG Strix",
        "ROG Zephyrus Duo",
        "ROG Zephyrus",
        "ROG Flow",
        "ROG Ally",
        "ROG",
        "TUF Gaming",
        "TUF",
        "Zenbook Pro",
        "Zenbook Duo",
        "Zenbook S",
        "Zenbook",
        "Vivobook Pro",
        "Vivobook S",
        "Vivobook Go",
        "Vivobook",
        "ExpertBook",
        "ProArt",
        "V16",
    ],
    "Acer": [
        "Predator Triton",
        "Predator Helios Neo",
        "Predator Helios",
        "Predator",
        "Nitro V",
        "Nitro",
        "Swift Go",
        "Swift X",
        "Swift",
        "Aspire Vero",
        "Aspire Go",
        "Aspire",
        "Spin",
        "TravelMate",
        "Extensa",
    ],
    "MSI": [
        "Titan",
        "Raider",
        "Stealth",
        "Vector",
        "Crosshair",
        "Pulse",
        "Katana",
        "Sword",
        "Cyborg",
        "Thin",
        "Bravo",
        "Prestige",
        "Modern",
        "Creator",
        "Claw",
    ],
    "Gigabyte": ["AERO", "Aorus", "Gaming A16", "G5", "G6"],
    "Apple": ["MacBook Pro", "MacBook Air", "MacBook"],
    "Huawei": ["MateBook X Pro", "MateBook X", "MateBook D", "MateBook"],
    "Microsoft": ["Surface Laptop Studio", "Surface Laptop", "Surface Pro"],
}


class TableKeyRouter:
    """Generic Multi-Store Specification Table Router.

    Routes raw retailer specification labels (across CompuMarts, B.Tech, 2B,
    Sigma, Elbadr, Amazon, etc.) into canonical hardware categories using
    specs_alias_dict.json, bilingual Arabic mappings, and explicit domain rules.
    Eliminates table key collisions and regex guesswork.
    """

    EXPLICIT_OVERRIDES = {
        # Bilingual & Arabic Store Overrides (B.Tech, 2B, Sigma, Noon, Amazon.eg)
        "المعالج": "cpu",
        "معالج": "cpu",
        "نوع المعالج": "cpu",
        "موديل المعالج": "cpu",
        "سرعة المعالج": "cpu",
        "كارت الشاشة": "gpu",
        "بطاقة الرسومات": "gpu",
        "كارت شاشة": "gpu",
        "معالج الرسومات": "gpu",
        "موديل كارت الشاشة": "gpu",
        "ذاكرة كارت الشاشة": "gpu_vram",
        "سعة كارت الشاشة": "gpu_vram",
        "الذاكرة": "memory",
        "ذاكرة الرام": "memory",
        "سعة الرام": "memory",
        "رام": "memory",
        "الذاكرة العشوائية": "memory",
        "سعة الذاكرة العشوائية": "memory",
        "اقصى سعة للذاكرة": "max_memory",
        "أقصى سعة للذاكرة": "max_memory",
        "منافذ الذاكرة": "memory_slots",
        "عدد منافذ الذاكرة": "memory_slots",
        "سعة التخزين": "storage",
        "وحدة التخزين": "storage",
        "القرص الصلب": "storage",
        "سعة القرص الصلب": "storage",
        "نوع التخزين": "storage_interface",
        "نوع القرص الصلب": "storage_interface",
        "منافذ التخزين": "storage_slots",
        "اقصى سعة تخزين": "max_storage",
        "الشاشة": "display",
        "حجم الشاشة": "display",
        "دقة الشاشة": "display",
        "نوع الشاشة": "display",
        "معدل التحديث": "display_refresh_rate",
        "سطوع الشاشة": "display_brightness",
        "شاشة لمس": "display_touchscreen",
        "البطارية": "power",
        "سعة البطارية": "power",
        "الشاحن": "power",
        "قدرة الشاحن": "power",
        "الوزن": "weight",
        "الابعاد": "dimensions",
        "الأبعاد": "dimensions",
        "اللون": "color",
        "المنافذ": "ports",
        "الاتصال": "connectivity",
        "واي فاي": "connectivity",
        "بلوتوث": "connectivity",
        "نظام التشغيل": "os",
        "الكاميرا": "camera",
        "كاميرا الويب": "camera",
        "الصوت": "audio",
        "السماعات": "audio",
        "لوحة المفاتيح": "keyboard",
        "بصمة الاصبع": "security",
        "بصمة الإصبع": "security",
        "قارئ البصمة": "security",
        # Lifecycle / Dates
        "end of support": "lifecycle",
        # Form Factor
        "form factor": "form_factor",
        # Storage primary vs expansion/slots/support/interface/form factor
        "storage expansion": "storage_slots",
        "storage capability": "storage_slots",
        "storage slot": "storage_slots",
        "storage slots": "storage_slots",
        "m.2 slots": "storage_slots",
        "m.2 ssd support list": "storage_slots",
        "supported ssd": "max_storage",
        "expansion slot": "storage_slots",
        "expansion slots": "storage_slots",
        "expansion slot (includes used)": "storage_slots",
        "expansion slot(includes used)": "storage_slots",
        "max storage support": "max_storage",
        "maximum storage": "max_storage",
        "maximum storage support": "max_storage",
        "storage support": "max_storage",
        "additional storage support": "max_storage",
        "storage type": "storage_interface",
        "ssd type": "storage_interface",
        "solid state drive interface": "storage_interface",
        "hard drive interface": "storage_interface",
        "hard drive type": "storage_interface",
        "ssd form factor": "storage_form_factor",
        # Memory primary vs max / slots
        "memory capacity": "memory",
        "ram, memory capacity, gb": "memory",
        "ram, number of slots": "memory_slots",
        "ram slots": "memory_slots",
        "memory slots": "memory_slots",
        "memory slot": "memory_slots",
        "channel support": "memory",
        "ram info": "memory",
        "ram memory": "memory",
        "ram memory installed": "memory",
        "installed memory": "memory",
        "dimm memory": "memory",
        "max memory": "max_memory",
        "maximum memory": "max_memory",
        "maximum memory supported": "max_memory",
        "maximum supported system memory": "max_memory",
        "max total system memory": "max_memory",
        "ram, maximum capacity, gb": "max_memory",
        "memory card supported": "card_reader",
        # Dimensions vs package vs portability/weight
        "package dimensions": "package_dimensions",
        "package size (w x d x h), mm": "package_dimensions",
        "portability": "weight",
        # Camera & Audio
        "camera & audio": "camera_and_audio",
        # Ports & Card Reader
        "connectivity": "connectivity_and_ports",
        "additional i/o": "ports",
        "additional io": "ports",
        "additional ports": "ports",
        "card reader": "card_reader",
        "memory card reader": "card_reader",
        # Display specific overrides
        "brightness": "display_brightness",
        "display brightness": "display_brightness",
        "peak brightness": "display_brightness",
        "screen, brightness, cd/m2": "display_brightness",
        "color gamut": "display_gamut",
        "colour gamut": "display_gamut",
        "color accuracy": "display_gamut",
        "color calibration": "display_gamut",
        "color coverage": "display_gamut",
        "color range": "display_gamut",
        "rgb colour space": "display_gamut",
        "pantone": "display_gamut",
        "color depth": "display_surface",
        "response time": "display_response_time",
        "response time (g2g)": "display_response_time",
        "surface": "display_surface",
        "surface treatment": "display_surface",
        "hdr support": "display_hdr",
        "support dolby vision hdr": "display_hdr",
        "color & hdr": "display_hdr",
        # Product Color overrides (prevent leaking into materials or display)
        "bottom case color": "color",
        "chassis color": "color",
        "design & color": "color",
        "lcd cover color": "color",
        "top case color": "color",
        "bottom case-color": "color",
        "lcd cover-color": "color",
        "top case-color": "color",
        # GPU Boost & Power overrides
        "gpu boost clock": "gpu_boost",
        "gpu power": "gpu_power",
        "gpu power / clock": "gpu_power",
        "gpu tgp": "gpu_power",
        "graphic wattage": "gpu_power",
        "graphics card tgp": "gpu_power",
        "graphics power (tgp)": "gpu_power",
        "graphics tgp": "gpu_power",
        "maximum graphics power (tgp)": "gpu_power",
        # AI Performance & NPU overrides
        "ai tops": "ai_performance",
        "ai performance": "ai_performance",
        # Keyboard & Stylus overrides
        "numeric keypad": "keyboard",
        "stylus support": "stylus",
        "pen": "stylus",
        # Warranty & Condition overrides
        "warranty": "warranty",
        "base warranty": "warranty",
        "manufacturer warranty": "warranty",
        "condition": "condition",
        "condition grade": "condition",
        # Cloud & Packaging overrides
        "cloud service": "unrouted",
        "weight in packaging": "package_dimensions",
        "weight in packaging, kg": "package_dimensions",
        "packaging weight": "package_dimensions",
        "package weight": "package_dimensions",
        # Security overrides
        "build level": "security",
        # Multi-Store & Section-Scoped Disambiguation Overrides (ElBadr, CompuMarts, etc.)
        # GPU / Graphics
        "graphics > memory": "gpu_vram",
        "graphics memory": "gpu_vram",
        "graphics > vram": "gpu_vram",
        "graphics vram": "gpu_vram",
        "graphics > power": "gpu_power",
        "graphics power": "gpu_power",
        "graphics > gpu": "gpu",
        "graphics > discrete gpu": "gpu",
        "graphics > integrated gpu": "gpu",
        "discrete gpu": "gpu",
        "integrated gpu": "gpu",
        "graphics card (gpu)": "gpu",
        "graphics card": "gpu",
        "graphics (gpu)": "gpu",
        "tgp (thermal design power)": "gpu_power",
        "rog boost": "gpu_boost",
        # Memory / RAM
        "system memory (ram)": "memory",
        "memory > memory": "memory",
        "memory > installed": "memory",
        "memory > type": "memory_type",
        "memory type": "memory_type",
        "memory > speed": "memory_speed",
        "memory speed": "memory_speed",
        "memory > slots": "memory_slots",
        "memory > max supported": "max_memory",
        "memory > expandable to": "max_memory",
        "max capacity": "max_memory",
        # Storage
        "storage > capacity": "storage",
        "storage > primary drive": "storage",
        "primary drive": "storage",
        "storage > expansion slots": "storage_slots",
        "storage > slots": "storage_slots",
        # Power & Battery
        "battery > capacity": "power",
        "battery & power > capacity": "power",
        "power & battery > capacity": "power",
        "power supply": "power",
        # Display
        "display > size": "display",
        "display > type": "display",
        "display > panel type": "display",
        "display > resolution": "display",
        "display > refresh rate": "display_refresh_rate",
        "display > peak brightness": "display_brightness",
        "display > color gamut": "display_gamut",
        "display > contrast ratio": "display",
        "display > response time": "display_response_time",
        "display > screen finish": "display_surface",
        "display > touchscreen": "display",
        "srgb": "display_gamut",
        "g-sync": "display",
        "sync tech": "display",
        # CPU
        "processor (cpu)": "cpu",
        "processor > model": "cpu",
        "processor > cpu": "cpu",
        "base clock": "cpu",
        "boost clock": "cpu",
        "max boost clock": "cpu",
        "clock speed": "cpu",
        "clock speeds": "cpu",
        "core/thread count": "cpu",
        "cores & threads": "cpu",
        "cores/threads": "cpu",
        "threads": "cpu",
        "p-core max frequency": "cpu",
        "e-core max frequency": "cpu",
        # AI Engine & Performance
        "ai acceleration": "ai_npu",
        "system ai accelerator": "ai_npu",
        "system ai chip": "ai_npu",
        "system ai controller": "ai_npu",
        "performance & hardware > ai performance": "ai_performance",
        "performance specifications > ai performance": "ai_performance",
        # Dimensions
        "dimensions (w x d x h)": "dimensions",
        "dimensions (h x w x d)": "dimensions",
        "laptop dimensions (w x d x h)": "dimensions",
        # Security
        "tpm security": "security",
        "hardware security": "security",
        "biometric login": "security",
        "windows hello": "security",
        # Camera
        "audio & inputs > webcam": "camera",
        "audio & multimedia > webcam": "camera",
        "camera & security > webcam": "camera",
        "keyboard & input > webcam": "camera",
        "design & build specifications > webcam": "camera",
        "security & multimedia > webcam": "camera",
        # Audio
        "audio & input > microphone": "audio",
        "audio & inputs > microphone": "audio",
        "audio & multimedia > microphone": "audio",
        "audio > microphone": "audio",
        "built-in array microphone": "audio",
        "ai noise-canceling technology": "audio",
        "audio & input > speakers": "audio",
        "audio & inputs > speakers": "audio",
        "audio & multimedia > speakers": "audio",
        "audio > speakers": "audio",
        "smart amp technology": "audio",
        "dolby atmos": "audio",
        "security & multimedia > audio": "audio",
        "audio & inputs > audio": "audio",
        "audio & multimedia > audio": "audio",
        "audio & input devices > audio": "audio",
        # Connectivity & Ports
        "wi-fi 7 (802.11be 2x2)": "connectivity",
        "wired networking": "connectivity",
        "gigabit ethernet (rj-45)": "ports",
        "left side ports": "ports",
        "right side ports": "ports",
        "rear side": "ports",
        "ports/slots/buttons": "ports",
        "usb-a 3.2 gen 1": "ports",
        "usb4": "ports",
        "headphone / mic combo": "ports",
        "audio jacks": "ports",
        "connectivity & i/o ports > audio": "ports",
        "connectivity & ports > audio": "ports",
        "connectivity & i/o ports > wireless": "connectivity",
        "connectivity & ports > wireless": "connectivity",
    }

    CANONICAL_FIELD_TO_BUCKET = {
        # Storage
        "Storage": "storage",
        "Storage Capacity": "storage",
        "Maximum Storage Support": "max_storage",
        "Storage Slots": "storage_slots",
        "Storage Interface": "storage_interface",
        "Optical Drive": "storage",
        # Memory
        "Memory (RAM)": "memory",
        "Maximum Memory": "max_memory",
        "Memory Slots": "memory_slots",
        "Memory Speed": "memory_speed",
        "Memory Technology / Type": "memory_type",
        # Ports & Connectivity
        "Ports / I/O": "ports",
        "Connectivity / Ports": "ports",
        "Network Connectivity": "connectivity",
        "Wireless Connectivity": "connectivity",
        "Bluetooth": "connectivity",
        "Card Reader": "card_reader",
        "Docking Support": "ports",
        # Camera & Audio
        "Camera / Webcam": "camera",
        "Camera & Audio": "camera_and_audio",
        "Audio": "audio",
        "Microphone": "audio",
        # Physical
        "Dimensions": "dimensions",
        "Weight": "weight",
        "Product Color": "color",
        "Build / Materials": "materials",
        # Display
        "Display": "display",
        "Display Size": "display",
        "Display Resolution": "display",
        "Display Refresh Rate": "display",
        "Display Aspect Ratio": "display",
        "Touchscreen": "display",
        "Display Brightness": "display_brightness",
        "Display Color Gamut / Accuracy": "display_gamut",
        "Display Color / HDR": "display_hdr",
        "Display Color Depth": "display_surface",
        "Display Contrast Ratio": "display",
        "Display Response Time": "display_response_time",
        "Display Screen-to-Body Ratio": "display",
        "Display Viewing Angle": "display",
        "Display Mounting / Compatibility": "display",
        "Display Features": "display",
        "Display Technology / Features": "display_surface",
        # GPU
        "Graphics (GPU)": "gpu",
        "GPU Memory": "gpu_vram",
        "GPU Power": "gpu_power",
        "GPU Speed / Clock": "gpu_boost",
        "GPU Vendor": "gpu",
        "Integrated Graphics": "gpu",
        # CPU
        "Processor": "cpu",
        "Processor Brand": "cpu",
        "Processor Cores / Threads": "cpu",
        "Processor Speed / Clock": "cpu",
        "Processor Cache": "cpu",
        "Chipset / Platform": "cpu",
        "AI Engine / NPU": "ai_npu",
        "AI Features": "ai_features",
        "AI Performance": "ai_performance",
        # Power
        "Battery": "power",
        "Power / Power Supply": "power",
        "Power Adapter / Charging": "power",
        "System Power / Performance": "power",
        # OS
        "Operating System": "os",
        "Bundled Software": "os",
        # Build & Security
        "Security": "security",
        "Keyboard": "keyboard",
        "Keyboard / Pointing Device": "keyboard",
        "Touchpad / Pointing Device": "pointing_device",
        "Pen / Stylus Support": "stylus",
        # Brand / Model / Identity
        "Brand": "brand",
        "Model / Product Name": "model",
        "Product Identifier": "model",
        "Product Category / Use": "identity",
        "Product Condition": "condition",
        "Product Features": "identity",
        "Product Lifecycle / Dates": "lifecycle",
        "Warranty / Support": "warranty",
        "Included Accessories / Package": "identity",
    }

    PARENT_DOMAINS: dict[str, str] = {
        "display_brightness": "display",
        "display_gamut": "display",
        "display_response_time": "display",
        "display_surface": "display",
        "display_hdr": "display",
        "memory_speed": "memory",
        "memory_type": "memory",
        "gpu_vram": "gpu",
        "gpu_power": "gpu",
        "gpu_boost": "gpu",
        "ai_npu": "cpu",
        "ai_features": "cpu",
        "ai_performance": "cpu",
        "materials": "physical",
        "dimensions": "physical",
        "weight": "physical",
        "card_reader": "connectivity",
        "ports": "connectivity",
        "warranty": "identity",
        "condition": "identity",
        "brand": "identity",
        "model": "identity",
        "color": "identity",
        "stylus": "identity",
        "lifecycle": "unrouted",
        "form_factor": "unrouted",
    }

    def __init__(
        self,
        alias_dict_path: Path | None = None,
        store_overlay_path: Path | None = None,
    ) -> None:
        if alias_dict_path is None:
            base_dir = Path(__file__).resolve().parent / "data"
            candidate = base_dir / "specs_alias_dict.json"
            if not candidate.exists():
                candidate = base_dir / "compumarts_alias_dict.json"
            alias_dict_path = candidate

        self.label_to_bucket: dict[str, str] = {}
        self._load_alias_dict(alias_dict_path)

        if store_overlay_path:
            self._load_alias_dict(store_overlay_path)

        # Apply explicit overrides (highest precedence)
        for k, b in self.EXPLICIT_OVERRIDES.items():
            self.label_to_bucket[self._normalize_key(k)] = b

    def _load_alias_dict(self, path: Path | None) -> None:
        if not path or not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            observed = data.get("observed_labels", {})
            for raw_lbl, meta in observed.items():
                canon_field = meta.get("canonical_field", "")
                bucket = self.CANONICAL_FIELD_TO_BUCKET.get(canon_field)
                if bucket:
                    norm_k = self._normalize_key(raw_lbl)
                    self.label_to_bucket[norm_k] = bucket
        except Exception:
            pass

    @staticmethod
    def _normalize_key(k: str) -> str:
        k = k.strip().lower()
        k = re.sub(r"[:\s\t\r\n]+", " ", k).strip()
        k = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", "", k).strip()
        # Normalize Arabic characters
        k = re.sub(r"[إأآا]", "ا", k)
        k = re.sub(r"ة", "ه", k)
        k = re.sub(r"[\u064b-\u065f]", "", k)  # Tashkeel
        return k

    @classmethod
    def parse_unstructured_specs(cls, raw_data: list[str] | str | dict[str, Any]) -> dict[str, str]:
        """Convert semi-structured bullets, key-value lines, or raw text into a key-value spec table.

        Supports formats like:
          - ["RAM: 16 GB", "Storage: 1TB SSD"]
          - "• Screen: 15.6 inch\n• CPU: AMD Ryzen 7"
          - Key - Value or Key: Value
        """
        if isinstance(raw_data, dict):
            return {str(k).strip(): str(v).strip() for k, v in raw_data.items() if str(k).strip()}

        result: dict[str, str] = {}
        if isinstance(raw_data, str):
            lines = raw_data.splitlines()
        elif isinstance(raw_data, list):
            lines = [str(item) for item in raw_data]
        else:
            return result

        delimiters_pattern = re.compile(r"[:\t\u2013\u2014\-]")
        bullet_prefix_pattern = re.compile(r"^[\s•\-\*\u2022\u25aa\u25cf\u25cb\u25b6#\d\.\)]+")

        for line in lines:
            cleaned_line = bullet_prefix_pattern.sub("", line).strip()
            if not cleaned_line:
                continue

            match = delimiters_pattern.search(cleaned_line)
            if match:
                k = cleaned_line[: match.start()].strip()
                v = cleaned_line[match.end() :].strip()
                if k and v and len(k) <= 60:
                    result[k] = v

        return result

    def route_key(self, raw_key: str) -> str:
        """Route a single table row key to a canonical bucket."""
        norm = self._normalize_key(raw_key)

        # High priority heuristics: packaging weight should not leak into weight bucket
        if any(term in norm for term in ["package weight", "packaging weight", "weight in packaging"]):
            return "package_dimensions"
        if any(term in norm for term in ["cloud service", "dropbox", "cloud storage"]):
            return "unrouted"

        if norm in self.label_to_bucket:
            return self.label_to_bucket[norm]

        # Heuristic fallback for previously unseen keys
        # 1. Guard against promotional marketing slogans / sentences masquerading as spec keys
        if raw_key.strip().endswith((".", "!")) and len(norm.split()) >= 3:
            return "unrouted"

        if any(term in norm for term in ["max storage", "maximum storage", "storage support", "storage capability"]):
            return "max_storage"
        if any(term in norm for term in ["storage slot", "m.2 slot", "expansion slot"]):
            return "storage_slots"
        if re.search(r"\b(?:storage|ssd|hdd|hard\s+disk|hard\s+drive|rom)\b", norm):
            return "storage"
        if any(term in norm for term in ["graphics memory", "video memory", "gpu memory", "vram", "gddr"]):
            return "gpu_vram"
        if any(term in norm for term in ["gpu power", "graphics power", "tgp"]) or (
            re.search(r"\bpower\b", norm) and re.search(r"\b(?:gpu|rtx|gtx|graphics|geforce|radeon)\b", norm)
        ):
            return "gpu_power"
        if any(term in norm for term in ["max memory", "maximum memory", "max ram"]):
            return "max_memory"
        if any(term in norm for term in ["memory slot", "ram slot"]):
            return "memory_slots"
        if re.search(r"\b(?:graphic|graphics|gpu|vga|video)\b", norm):
            return "gpu"
        if re.search(r"\b(?:ram|memory)\b", norm):
            return "memory"
        if re.search(r"\b(?:cpu|processor)\b", norm):
            return "cpu"
        if re.search(r"\b(?:battery|adapter|charging|charger)\b", norm) or (
            re.search(r"\bpower\b", norm) and not re.search(r"\b(?:gpu|rtx|gtx|graphics|geforce|radeon)\b", norm)
        ):
            return "power"
        if re.search(r"\b(?:operating\s+system|os)\b", norm):
            return "os"
        if re.search(
            r"\b(?:display|screen|resolution|refresh\s+rate|panel|aspect\s+ratio|touchscreen|oled|amoled|ips)\b", norm
        ):
            return "display"
        if re.search(r"\bdimensions?\b", norm) or "(w x d x h)" in norm or "(h x w x d)" in norm:
            return "dimensions"
        if any(
            term in norm
            for term in [
                "usb",
                "hdmi",
                "thunderbolt",
                "rj-45",
                "rj45",
                "ethernet port",
                "combo audio jack",
                "headphone",
                "audio jacks",
            ]
        ):
            return "ports"
        if re.search(r"\b(?:webcam|camera)\b", norm):
            return "camera"
        if any(term in norm for term in ["microphone", "speakers", "nahimic", "smart amp"]):
            return "audio"
        if any(term in norm for term in ["tpm", "biometric", "fingerprint", "windows hello", "kensington"]):
            return "security"
        if any(term in norm for term in ["wi-fi", "wifi", "bluetooth", "wireless", "wired networking"]):
            return "connectivity"
        if any(term in norm for term in ["card reader", "microsd", "sd card"]):
            return "card_reader"

        return "unrouted"

    def route_table(self, table: dict[str, str]) -> dict[str, list[tuple[str, str]]]:
        """Route all rows in a table to canonical buckets."""
        routed: dict[str, list[tuple[str, str]]] = {}
        for k, v in table.items():
            bucket = self.route_key(k)
            # 1. Store in the exact O(1) specific bucket
            routed.setdefault(bucket, []).append((k, v))

            # 2. If it belongs to a parent domain, also index under the parent
            parent = self.PARENT_DOMAINS.get(bucket)
            if parent and parent != bucket:
                routed.setdefault(parent, []).append((k, v))

            # 3. Dual-routed special cases
            if bucket == "connectivity_and_ports":
                routed.setdefault("connectivity", []).append((k, v))
                if any(w in v.lower() for w in ["port", "usb", "hdmi", "thunderbolt", "jack", "lan", "rj45", "rj-45"]):
                    routed.setdefault("ports", []).append((k, v))
            elif bucket == "camera_and_audio":
                routed.setdefault("camera", []).append((k, v))
                routed.setdefault("audio", []).append((k, v))
        return routed


class DeterministicExtractor:
    """Extracts specs deterministically and creates envelopes for unresolved fields."""

    def __init__(
        self,
        alias_dict_path: Path | None = None,
        store_overlay_path: Path | None = None,
        gpu_anchor: GPUAnchorExtractor | None = None,
    ) -> None:
        self.router = TableKeyRouter(alias_dict_path, store_overlay_path=store_overlay_path)
        self.gpu_anchor = gpu_anchor or GPUAnchorExtractor()

    def extract(
        self,
        title: str,
        sanitized_table: dict[str, str],
        sanitized_sections: dict[str, str],
        cpu_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[ExtractionEnvelope]]:
        """Run deterministic extraction across all categories.

        Returns:
            Tuple of (partially_populated_specs, list_of_envelopes)
        """
        specs = empty_laptop_specifications()
        envelopes: list[ExtractionEnvelope] = []

        # Route table keys into canonical hardware buckets
        routed_table = self.router.route_table(sanitized_table)

        # Find section contexts
        display_sec = self._find_section_context(["display", "screen"], sanitized_sections, sanitized_table)
        gpu_sec = self._find_section_context(["graphics", "gpu", "vga", "video"], sanitized_sections, sanitized_table)
        mem_sec = self._find_section_context(["memory", "ram"], sanitized_sections, sanitized_table)
        storage_sec = self._find_section_context(
            ["storage", "ssd", "hard drive", "hdd"], sanitized_sections, sanitized_table
        )
        power_sec = self._find_section_context(["battery", "power", "adapter"], sanitized_sections, sanitized_table)
        physical_sec = self._find_section_context(
            ["dimension", "weight", "physical"], sanitized_sections, sanitized_table
        )
        conn_sec = self._find_section_context(
            ["connectivity", "network", "port", "wireless"], sanitized_sections, sanitized_table
        )
        audio_sec = self._find_section_context(
            ["audio", "sound", "speaker", "webcam", "camera", "microphone"], sanitized_sections, sanitized_table
        )
        sec_sec = self._find_section_context(
            ["security", "keyboard", "touchpad", "pointing", "fingerprint"], sanitized_sections, sanitized_table
        )

        # 1. Identity
        self._extract_identity(title, sanitized_table, routed_table, specs, envelopes)

        # 2. CPU (raw_spec)
        self._extract_cpu(title, sanitized_table, routed_table, specs)

        # 3. GPU
        self._extract_gpu(title, sanitized_table, routed_table, gpu_sec, specs, envelopes, cpu_context)

        # 4. Memory
        self._extract_memory(title, sanitized_table, routed_table, mem_sec, specs, envelopes, cpu_context)

        # 5. Storage
        self._extract_storage(title, sanitized_table, routed_table, storage_sec, specs, envelopes)

        # 6. Display
        self._extract_display(title, sanitized_table, routed_table, display_sec, specs, envelopes)

        # 7. Power & Battery
        self._extract_power(sanitized_table, routed_table, power_sec, specs, envelopes, cpu_context)

        # 8. Physical
        self._extract_physical(title, sanitized_table, routed_table, physical_sec, specs, envelopes)

        # 9. Connectivity
        self._extract_connectivity(sanitized_table, routed_table, conn_sec, specs)

        # 10. Operating System
        self._extract_operating_system(title, sanitized_table, routed_table, conn_sec, specs)

        # 11. Build & Security
        self._extract_build_security(title, sanitized_table, routed_table, sec_sec, specs, envelopes)

        # 12. Audio & Webcam
        self._extract_audio_webcam(sanitized_table, routed_table, audio_sec, specs, envelopes)

        return specs, envelopes

    # -------------------------------------------------------------------------
    # Helper: Raw Spec Aggregation & Section Context
    # -------------------------------------------------------------------------
    @staticmethod
    def _format_raw_spec(
        entries: list[tuple[str, str]] | None = None,
        fallback_text: str | None = None,
    ) -> str | None:
        """Format gathered raw specification entries as "{Key}: {Value}" joined by " | ".

        Preserves original table keys and values, de-duplicates identical pairs,
        and falls back to section/title context if no table rows exist.
        """
        parts: list[str] = []
        seen = set()

        if entries:
            for k, v in entries:
                k_clean = str(k).strip() if k is not None else ""
                v_clean = str(v).strip() if v is not None else ""
                if not k_clean and not v_clean:
                    continue
                # Sanitize literal pipe delimiters inside keys and values
                # to strictly preserve ' | ' as the entry separator
                k_clean = k_clean.replace(" | ", " / ").replace("|", "/")
                v_clean = v_clean.replace(" | ", " / ").replace("|", "/")
                dedup_key = (k_clean.lower(), v_clean.lower())
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    entry = f"{k_clean}: {v_clean}" if k_clean else f"Spec: {v_clean}"
                    parts.append(entry)

        if parts:
            return " | ".join(parts)

        if fallback_text and fallback_text.strip():
            ft = fallback_text.strip().replace(" | ", " / ").replace("|", "/")
            if ":" not in ft:
                ft = f"Context: {ft}"
            return ft

        return None

    def _collect_raw_spec(
        self,
        table: dict[str, str],
        target_buckets: set[str],
        fallback_text: str | None = None,
        prefix_entries: list[tuple[str, str]] | None = None,
    ) -> str | None:
        """Collect all table rows mapped to target_buckets in their original table order.

        Returns:
            A formatted string "{Key}: {Value}" joined by " | ", or None if empty.
        """
        entries: list[tuple[str, str]] = []
        if prefix_entries:
            entries.extend(prefix_entries)

        for k, v in table.items():
            bucket = self.router.route_key(k)
            parent = self.router.PARENT_DOMAINS.get(bucket)
            # Handle standard, parent domain, and dual-routed buckets
            if (
                bucket in target_buckets
                or (parent and parent in target_buckets)
                or (bucket == "camera_and_audio" and ("camera" in target_buckets or "audio" in target_buckets))
                or (
                    bucket == "connectivity_and_ports"
                    and ("ports" in target_buckets or "connectivity" in target_buckets)
                )
            ):
                entries.append((k, v))

        return self._format_raw_spec(entries, fallback_text=fallback_text)

    def _find_section_context(
        self,
        keywords: list[str],
        sanitized_sections: dict[str, str],
        sanitized_table: dict[str, str],
    ) -> str:
        """Find matching section-level context for envelopes."""
        # Check dedicated sections first
        for sec_name, sec_text in sanitized_sections.items():
            sec_lower = sec_name.lower()
            if any(k in sec_lower for k in keywords):
                return f"=== Section: {sec_name} ===\n{sec_text}"

        # Otherwise synthesize from relevant table key-values
        matching_rows = []
        for k, v in sanitized_table.items():
            k_lower = k.lower()
            if any(kw in k_lower for kw in keywords):
                if any(
                    bad in k_lower
                    for bad in ["max storage", "maximum storage", "storage support", "max memory", "maximum memory"]
                ):
                    continue
                matching_rows.append(f"{k}: {v}")

        if matching_rows:
            return "\n".join(matching_rows)
        return ""

    # -------------------------------------------------------------------------
    # Category Extractors
    # -------------------------------------------------------------------------
    @classmethod
    def clean_laptop_name(cls, title: str) -> str:
        """Isolate clean laptop name prefix from title, stripping trailing specs dump."""
        t = re.sub(r"^(?:laptop|notebook)\s+", "", title.strip(), flags=re.IGNORECASE)
        # 1. Delimiters (dash, en-dash, em-dash, pipe, comma before specs)
        parts = re.split(
            r"\s+[–—|]\s+|\s+-\s+(?=(?:Intel|AMD|Ryzen|Core|Snapdragon|Apple|\d+GB|RTX))|,\s+(?=(?:Intel|AMD|Ryzen|Core|Snapdragon|\d+GB|RTX))",
            t,
            maxsplit=1,
        )
        cand = parts[0].strip()
        # 2. End at Gaming Laptop / Laptop / Notebook if present
        m = re.search(r"^(.*?\b(?:gaming\s+laptop|laptop|notebook)\b)", cand, re.IGNORECASE)
        if m and len(m.group(1).strip()) > 8:
            return m.group(1).strip()
        # 3. Truncate before specs keywords if still present
        m2 = re.search(
            r"^(.*?)\b(?:Intel|AMD|Ryzen|Core\s+[iI\d]|Core\s+Ultra|\d+GB\s+(?:RAM|DDR)|RTX|GeForce)\b",
            cand,
            re.IGNORECASE,
        )
        if m2 and len(m2.group(1).strip()) > 5:
            return m2.group(1).strip().rstrip(" ,–-")
        return cand

    def _extract_identity(
        self,
        title: str,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)
        clean_name = self.clean_laptop_name(title)
        clean_lower = clean_name.lower()
        title_lower = title.lower()

        # 1. Brand: Check routed table or table
        brand_rows = routed_table.get("brand", [])
        for _, v in brand_rows:
            v_lower = v.lower()
            for b_key, b_name in CANONICAL_BRANDS.items():
                if b_key in v_lower:
                    specs["identity"]["brand"] = b_name
                    break
            if specs["identity"]["brand"]:
                break

        if not specs["identity"]["brand"]:
            for k, v in table.items():
                kl = k.lower()
                if any(term in kl for term in ["brand", "manufacturer"]):
                    v_lower = v.lower()
                    for b_key, b_name in CANONICAL_BRANDS.items():
                        if b_key in v_lower:
                            specs["identity"]["brand"] = b_name
                            break
                    if specs["identity"]["brand"]:
                        break

        # If not in table, fall back to clean_name and title
        if not specs["identity"]["brand"]:
            for b_key, b_name in CANONICAL_BRANDS.items():
                if re.search(r"\b" + re.escape(b_key) + r"\b", clean_lower):
                    specs["identity"]["brand"] = b_name
                    break
        if not specs["identity"]["brand"]:
            for b_key, b_name in CANONICAL_BRANDS.items():
                if re.search(r"\b" + re.escape(b_key) + r"\b", title_lower):
                    specs["identity"]["brand"] = b_name
                    break
        if not specs["identity"]["brand"] and re.search(r"\brog\b", clean_lower):
            specs["identity"]["brand"] = "ASUS"

        brand = specs["identity"]["brand"]

        # Retailer SKU / Product code from table
        for k, v in table.items():
            kl = k.lower()
            if kl in {"sku", "retailer sku", "item number", "product code"}:
                v_clean = v.strip()
                if v_clean and not any(bad in v_clean.lower() for bad in ["n/a", "none"]):
                    specs["identity"]["retailer_sku"] = v_clean
                    break

        # 2. Manufacturer Part Number (MPN) / SKU
        table_mpn = None
        is_machine_type = False
        for target_k in ["part number", "product number", "mpn"]:
            for k, v in table.items():
                if k.lower() == target_k:
                    v_clean = v.strip()
                    if v_clean and not any(bad in v_clean.lower() for bad in ["n/a", "none"]):
                        table_mpn = v_clean
                        is_machine_type = False
                        break
            if table_mpn:
                break

        if not table_mpn:
            for k, v in table.items():
                kl = k.lower()
                if any(
                    term in kl
                    for term in ["part number", "part no", "machine type", "mpn", "product number", "base unit"]
                ) and not any(bad in kl for bad in ["processor", "cpu", "gpu", "graphic", "video"]):
                    v_clean = v.strip()
                    if v_clean and not any(
                        bad in v_clean.lower() for bad in ["n/a", "none", "ssd", "ram", "rtx", "gtx"]
                    ):
                        if "machine type" in kl or len(v_clean) <= 4:
                            table_mpn = v_clean
                            is_machine_type = True
                        else:
                            table_mpn = v_clean
                            is_machine_type = False
                        break

        # Check if table has a Model or SKU key containing a definitive OEM part number
        if not table_mpn:
            for k, v in table.items():
                kl = k.lower()
                if kl in {"model", "sku", "retailer sku", "model number", "product code"}:
                    v_clean = v.strip()
                    if re.match(
                        r"^(?:9S7-[A-Za-z0-9]+-[A-Za-z0-9]+|90N[A-Za-z0-9]{5}-[A-Za-z0-9]+|NX\.[A-Za-z0-9]{5}\.[A-Za-z0-9]{3}|8[0-3][A-Za-z0-9]{8}|[A-Za-z0-9]{7}#[A-Za-z0-9]{3}|[A-Z]{2}\d{3}[A-Z]{2,4}-[A-Z0-9]+)$",
                        v_clean,
                        re.IGNORECASE,
                    ):
                        table_mpn = v_clean
                        is_machine_type = False
                        break

        # Check retailer_sku if it matches standard OEM MPN signatures
        if not table_mpn and specs["identity"].get("retailer_sku"):
            r_sku = specs["identity"]["retailer_sku"].strip()
            if re.match(
                r"^(?:9S7-[A-Za-z0-9]+-[A-Za-z0-9]+|90N[A-Za-z0-9]{5}-[A-Za-z0-9]+|NX\.[A-Za-z0-9]{5}\.[A-Za-z0-9]{3}|8[0-3][A-Za-z0-9]{8}|[A-Za-z0-9]{7}#[A-Za-z0-9]{3}|[A-Z]{2}\d{3}[A-Z]{2,4}-[A-Z0-9]+)$",
                r_sku,
                re.IGNORECASE,
            ):
                table_mpn = r_sku

        # Check title and SKU for full Lenovo MPN (e.g. 83S000C2IN, 83DV00N8ED, 82X700BVPS)
        full_lenovo_match = re.search(
            r"\b(8[0-3][A-Za-z0-9]{8})\b",
            f"{title} {specs['identity'].get('retailer_sku', '')}",
        )
        if table_mpn and not is_machine_type:
            specs["identity"]["manufacturer_part_number"] = table_mpn
        elif full_lenovo_match:
            specs["identity"]["manufacturer_part_number"] = full_lenovo_match.group(1)
        elif table_mpn:
            specs["identity"]["manufacturer_part_number"] = table_mpn
        else:
            # Look for full MPN in clean_name first, then title
            mpn_matches_clean = re.findall(
                r"\b([A-Za-z0-9]+(?:[-.#][A-Za-z0-9]+)+|[0-9]{2}[A-Za-z0-9]{6,8})\b",
                clean_name,
            )
            mpn_matches_title = re.findall(
                r"\b([A-Za-z0-9]+(?:[-.#][A-Za-z0-9]+)+|[0-9]{2}[A-Za-z0-9]{6,8})\b",
                title,
            )

            def _is_valid_mpn(m: str) -> bool:
                if re.match(r"^(?:2-in-1|wi-fi|win-11|type-c)$", m, re.I):
                    return False
                if re.match(r"^(?:i[3579]|r[3579]|core|ryzen|ultra)[-_]\w+", m, re.I):
                    return False
                if any(
                    k in m.upper() for k in ["RTX", "GTX", "DDR", "SSD", "HDD", "IPS", "FHD", "QHD", "WUXGA", "OLED"]
                ):
                    return False
                return len(m) >= 6

            valid_clean = [m for m in mpn_matches_clean if _is_valid_mpn(m)]
            valid_title = [m for m in mpn_matches_title if _is_valid_mpn(m)]

            if valid_clean:
                specs["identity"]["manufacturer_part_number"] = valid_clean[0]
            elif valid_title:
                specs["identity"]["manufacturer_part_number"] = valid_title[0]
            elif table_mpn:
                specs["identity"]["manufacturer_part_number"] = table_mpn

        # 3. Laptop Family
        # Check table first
        for k, v in table.items():
            kl = k.lower()
            if any(term in kl for term in ["series", "laptop family", "family"]) and not any(
                bad in kl for bad in ["processor", "cpu", "gpu", "graphic", "video"]
            ):
                v_clean = v.strip()
                if v_clean and not any(bad in v_clean.lower() for bad in ["n/a", "none", "laptop"]):
                    specs["identity"]["laptop_family"] = v_clean
                    break

        # Check CANONICAL_FAMILIES against clean_name
        if not specs["identity"]["laptop_family"] and brand and brand in CANONICAL_FAMILIES:
            for fam in sorted(CANONICAL_FAMILIES[brand], key=len, reverse=True):
                if re.search(r"\b" + re.escape(fam) + r"\b", clean_name, re.IGNORECASE):
                    specs["identity"]["laptop_family"] = fam
                    break

        # 4. Laptop Model
        # Check table first - prioritize descriptive model name over part code
        for k, v in table.items():
            kl = k.lower()
            if kl in {"model name", "laptop model", "model / series", "product model"}:
                v_clean = v.strip()
                if v_clean and not any(bad in v_clean.lower() for bad in ["n/a", "none"]):
                    specs["identity"]["laptop_model"] = v_clean
                    break

        if not specs["identity"]["laptop_model"]:
            for k, v in table.items():
                kl = k.lower()
                if any(term in kl for term in ["model / series", "model"]) and not any(
                    bad in kl
                    for bad in [
                        "processor",
                        "cpu",
                        "gpu",
                        "graphic",
                        "video",
                        "wireless",
                        "lan",
                        "wifi",
                        "wi-fi",
                        "wlan",
                        "network",
                        "bluetooth",
                        "adapter",
                        "battery",
                        "camera",
                        "display",
                        "panel",
                        "audio",
                        "speaker",
                    ]
                ):
                    v_clean = v.strip()
                    # Do not treat network cards, Wi-Fi models, or pure MPN codes as the marketing laptop model
                    if re.search(r"\b(?:killer|wi-fi|wifi|wlan|ax\d{3,4}|1750x|2x2\s*ax)\b", v_clean, re.I):
                        continue
                    if not re.match(
                        r"^(?:9S7-[A-Za-z0-9]+-[A-Za-z0-9]+|90N[A-Za-z0-9]{5}-[A-Za-z0-9]+)$", v_clean, re.I
                    ):
                        if v_clean and not any(bad in v_clean.lower() for bad in ["n/a", "none"]):
                            specs["identity"]["laptop_model"] = v_clean
                            break

        # If not in table, synthesize from family + size/qualifier in clean_name
        if not specs["identity"]["laptop_model"] and specs["identity"]["laptop_family"]:
            fam = specs["identity"]["laptop_family"]
            m_sz = re.search(
                r"\b"
                + re.escape(fam)
                + r"(?:\s+(\d{1,2}(?:\.\d)?|\bpro\s*\d{1,2}|\bhx|\bmax|\bplus|\bultra|\bgo|\bs))?\b",
                clean_name,
                re.IGNORECASE,
            )
            if m_sz:
                specs["identity"]["laptop_model"] = m_sz.group(0).strip()
            else:
                specs["identity"]["laptop_model"] = fam

        # 5. Bundle Detection
        is_bundle = False
        if re.search(r"\b(?:bundle|first light geforce)\b", title, re.IGNORECASE):
            is_bundle = True
        for k, v in table.items():
            kl = k.lower()
            vl = str(v).strip().lower()
            if (
                any(b in kl for b in ["bundled accessories", "bundle", "gift"])
                and vl
                and vl not in ("none", "no", "n/a")
            ):
                is_bundle = True
                break
        specs["identity"]["is_bundle"] = is_bundle

        # 5. Color
        # Check routed color rows or table keys specifically for color (avoiding gamut/coverage/depth)
        color_cands = []
        for rk, rv in routed_table.get("color", []):
            color_cands.append((rk, rv))
        if not color_cands:
            for k, v in table.items():
                kl = k.lower()
                if "color" in kl and not any(
                    bad in kl
                    for bad in [
                        "gamut",
                        "coverage",
                        "accuracy",
                        "depth",
                        "calibration",
                        "space",
                        "rgb",
                        "hdr",
                        "display",
                        "screen",
                    ]
                ):
                    color_cands.append((k, v))

        for _, cv in color_cands:
            clean_c = re.sub(r"\(.*?\)", "", cv).strip()
            # Strip display/gamut technical specs leaking into color
            clean_c = re.split(
                r"\b(?:coverage|gamut|accuracy|\d+%\s*srgb|\d+%\s*ntsc|\d+%\s*dci-p3|oled|fhd|qhd|144hz|165hz|240hz|300-nit|brightness|displayhdr|dolby vision|x-rite|pantone)\b",
                clean_c,
                flags=re.IGNORECASE,
            )[0].strip(" ,-|/")
            # Deduplicate repeated phrases or words (e.g. 'Luna Grey Luna Grey' -> 'Luna Grey', 'Black Black' -> 'Black')
            m_rep = re.match(r"^(.+?)\s+\1$", clean_c, flags=re.IGNORECASE)
            if m_rep:
                clean_c = m_rep.group(1).strip()
            clean_c = re.sub(r"\b(\w+)\s+\1\b", r"\1", clean_c, flags=re.IGNORECASE).strip()
            if clean_c and not any(bad in clean_c.lower() for bad in ["none", "n/a"]):
                specs["identity"]["color"] = clean_c
                break

        if not specs["identity"]["color"]:
            # Title color fallback: match known color names at word boundaries
            color_pat = (
                r"\b(shadow black|luna grey|eclipse gray|eclipse black|mica silver|abyssal black|"
                r"graphite|mecha gray|storm grey|cosmos grey|jade black|cool silver|interstellar indigo|"
                r"platinum silver|pure silver|basalt grey|glacier blue|phantom black|dark shadow gray|"
                r"natural silver|jet black|carbon black|silver|black|gray|grey|blue|white|gold|platinum)\b"
            )
            trailing_parts = re.split(r"[–—,-]\s*", title)
            if trailing_parts:
                for part in reversed(trailing_parts):
                    m_col = re.search(color_pat, part, re.IGNORECASE)
                    if m_col:
                        found_col = m_col.group(1).title()
                        # Deduplicate repeated words
                        found_col = re.sub(r"\b(\w+)\s+\1\b", r"\1", found_col, flags=re.IGNORECASE).strip()
                        specs["identity"]["color"] = found_col
                        break

        # 6. Option B: Package envelopes for unresolved identity fields
        # Note: Envelope context contains ONLY the isolated clean laptop name,
        # preventing AI from confusing trailing CPU/RAM/GPU specifications with model info.
        if not specs["identity"]["laptop_family"]:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="identity.laptop_family",
                    field_description="Laptop product family or sub-brand name, e.g. Victus, Legion, ROG, ThinkPad, Pavilion",
                    raw_context=clean_name,
                    failure_reason="missing",
                    expected_type="str",
                    allowed_values=CANONICAL_FAMILIES.get(brand, []) if brand else [],
                )
            )

        if not specs["identity"]["laptop_model"]:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="identity.laptop_model",
                    field_description="Laptop model name, e.g. Victus 15, LOQ 15IRX9, Strix G16",
                    raw_context=clean_name,
                    failure_reason="missing",
                    expected_type="str",
                )
            )

        if not specs["identity"]["manufacturer_part_number"]:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="identity.manufacturer_part_number",
                    field_description="Manufacturer part number or alphanumeric SKU code, e.g. 15-fa2082wm, 83DV00N8ED, NX.VPQEM.008",
                    raw_context=clean_name,
                    failure_reason="missing",
                    expected_type="str",
                )
            )

        # 6. Warranty & Condition
        warranty_rows = routed_table.get("warranty", [])
        w_cand = None
        for _, v in warranty_rows:
            vs = v.strip()
            if vs and not any(
                bad in vs.lower()
                for bad in [
                    "http",
                    "click/pwe",
                    "register within",
                    "dropbox",
                    "cloud service",
                    "cloud storage",
                    "onedrive",
                    "google drive",
                ]
            ):
                w_cand = vs
                break
        if not w_cand:
            for k, v in table.items():
                kl = k.lower()
                if "warranty" in kl and not any(bad in kl for bad in ["activate", "note"]):
                    vs = v.strip()
                    if vs and not any(
                        bad in vs.lower()
                        for bad in [
                            "http",
                            "click/pwe",
                            "register within",
                            "dropbox",
                            "cloud service",
                            "cloud storage",
                            "onedrive",
                            "google drive",
                        ]
                    ):
                        w_cand = vs
                        break
        if w_cand:
            specs["identity"]["warranty"] = w_cand
            m_yr = re.search(r"\b([1-5])\s*(?:-|–|\s)?(?:years?|yr|y)\b", w_cand, re.IGNORECASE)
            if m_yr:
                specs["identity"]["warranty_years"] = int(m_yr.group(1))
            else:
                m_mo = re.search(r"\b(12|24|36|48)\s*months?\b", w_cand, re.IGNORECASE)
                if m_mo:
                    specs["identity"]["warranty_years"] = int(m_mo.group(1)) // 12

        cond_rows = routed_table.get("condition", [])
        cond_cand = None
        for _, v in cond_rows:
            vs = v.strip()
            if vs:
                cond_cand = vs
                break
        if not cond_cand:
            for k, v in table.items():
                if "condition" in k.lower():
                    cond_cand = v.strip()
                    break
        if cond_cand:
            cl = cond_cand.lower()
            if "refurbished" in cl:
                specs["identity"]["condition"] = "Refurbished"
            elif "used" in cl:
                specs["identity"]["condition"] = "Used"
            elif "open box" in cl:
                specs["identity"]["condition"] = "Open Box"
            elif "new" in cl:
                specs["identity"]["condition"] = "New"
            else:
                specs["identity"]["condition"] = cond_cand
        elif "refurbished" in title_lower:
            specs["identity"]["condition"] = "Refurbished"
        elif "open box" in title_lower:
            specs["identity"]["condition"] = "Open Box"

        prefix_id = [("Title", title.strip())] if title and title.strip() else []
        specs["identity"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"brand", "model", "identity"},
            prefix_entries=prefix_id,
        )

    def _extract_cpu(
        self,
        title: str,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        specs: dict[str, Any],
    ) -> None:
        """Extract raw CPU specification rows into specs['cpu']['raw_spec'] and resolve unanchored fields."""
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["cpu"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"cpu"},
            fallback_text=f"Title: {title.strip()}" if title and title.strip() else None,
        )

        cpu_rows = routed_table.get("cpu", [])
        ai_rows = routed_table.get("ai_npu", []) + routed_table.get("ai_performance", [])
        cpu_text = " ".join(v for _, v in cpu_rows + ai_rows)

        # NPU TOPS fallback if not populated by cpu_anchor
        if specs["cpu"]["npu_tops"] is None:
            m_npu = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:tops|ai\s*tops)\b", cpu_text, re.IGNORECASE)
            if not m_npu:
                for k, v in table.items():
                    if any(term in k.lower() for term in ["npu", "ai boost", "ai engine"]):
                        m_npu = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:tops|ai\s*tops)\b", v, re.IGNORECASE)
                        if m_npu:
                            break
            if m_npu:
                valid, tops_clean, _ = PhysicalValidator.validate_npu_tops(m_npu.group(1))
                if valid:
                    specs["cpu"]["npu_tops"] = tops_clean

        # Base Power (W) fallback if not populated
        if specs["cpu"]["base_power_w"] is None:
            m_bp = re.search(
                r"\b(\d{2,3})\s*w\s*(?:tdp|base\s*power|processor\s*base\s*power)\b", cpu_text, re.IGNORECASE
            )
            if m_bp:
                specs["cpu"]["base_power_w"] = int(m_bp.group(1))

    def _extract_gpu(
        self,
        title: str,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
        cpu_context: dict[str, Any] | None = None,
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["gpu"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"gpu", "gpu_vram"},
            fallback_text=context,
        )

        gpu_rows = routed_table.get("gpu", [])
        gpu_text = " ".join(v for _, v in gpu_rows)
        if not gpu_text:
            for k, v in table.items():
                k_lower = k.lower()
                if any(term in k_lower for term in ["gpu", "graphic", "vga", "video"]):
                    gpu_text += f" {v}"
        # Prioritize specification table text first!
        full_search = f"{gpu_text} {context} {title}"

        # Collect spec text snippets for GPU anchor
        spec_text_snippets = [gpu_text, context]
        if routed_table:
            spec_text_snippets.extend([v for _, v in routed_table.get("gpu_vram", [])])
            spec_text_snippets.extend([v for _, v in routed_table.get("gpu_power", [])])
            spec_text_snippets.extend([v for _, v in routed_table.get("gpu_boost", [])])

        # Layer 3.5: GPU Anchor ground-truth extraction
        gpu_anchored_specs, gpu_constraints, matched_key = self.gpu_anchor.extract(
            title=title,
            spec_texts=spec_text_snippets,
            cpu_context=cpu_context,
        )
        if gpu_anchored_specs:
            specs["gpu"]["manufacturer"] = gpu_anchored_specs["manufacturer"]
            specs["gpu"]["model"] = gpu_anchored_specs["model"]
            specs["gpu"]["variant"] = gpu_anchored_specs.get("variant")
            specs["gpu"]["vram_gb"] = gpu_anchored_specs.get("vram_gb")
            specs["gpu"]["integrated"] = gpu_anchored_specs["integrated"]
            specs["gpu"]["tdp_w"] = gpu_anchored_specs.get("tdp_w")
            specs["gpu"]["boost_clock_mhz"] = gpu_anchored_specs.get("boost_clock_mhz")
            specs["gpu"]["ai_tops"] = gpu_anchored_specs.get("ai_tops")

            # Extract additional details if not captured by anchor (e.g. boost clock or ai tops from other rows)
            self._extract_gpu_details(gpu_text, full_search, routed_table, specs)
            return

        # 1. Fallback regex checks for discrete GPUs with strict architectural generations
        # NVIDIA GeForce RTX (20, 30, 40, and new 50 series)
        rtx_match = re.search(r"\brtx\s*([2-5]\d{3}(?:\s*(?:ti|super))?)\b", full_search, re.IGNORECASE)
        if rtx_match:
            specs["gpu"]["manufacturer"] = "NVIDIA"
            specs["gpu"]["model"] = f"GeForce RTX {rtx_match.group(1).upper()}"
            specs["gpu"]["integrated"] = False
            self._extract_gpu_vram(gpu_text, full_search, context, specs, envelopes)
            self._extract_gpu_details(gpu_text, full_search, routed_table, specs)
            return

        # NVIDIA GeForce GTX (Turing 16-series and Pascal 10-series)
        gtx_match = re.search(r"\bgtx\s*((?:16[56]0|10[5-8]0)(?:\s*ti)?)\b", full_search, re.IGNORECASE)
        if gtx_match:
            specs["gpu"]["manufacturer"] = "NVIDIA"
            specs["gpu"]["model"] = f"GeForce GTX {gtx_match.group(1).upper()}"
            specs["gpu"]["integrated"] = False
            self._extract_gpu_vram(gpu_text, full_search, context, specs, envelopes)
            self._extract_gpu_details(gpu_text, full_search, routed_table, specs)
            return

        # NVIDIA GeForce MX (Entry-level discrete)
        mx_match = re.search(r"\bgeforce\s+mx\s*([1-5]\d{2})\b|\bmx\s*([1-5]\d{2})\b", full_search, re.IGNORECASE)
        if mx_match:
            mx_num = mx_match.group(1) or mx_match.group(2)
            specs["gpu"]["manufacturer"] = "NVIDIA"
            specs["gpu"]["model"] = f"GeForce MX{mx_num}"
            specs["gpu"]["integrated"] = False
            self._extract_gpu_vram(gpu_text, full_search, context, specs, envelopes)
            self._extract_gpu_details(gpu_text, full_search, routed_table, specs)
            return

        # AMD Radeon RX Discrete (e.g. RX 6500M, RX 7600M)
        rx_match = re.search(r"\bradeon\s*(?:rx\s*)?([67]\d{3}[ms](?:\s*xt)?)\b", full_search, re.IGNORECASE)
        if rx_match:
            specs["gpu"]["manufacturer"] = "AMD"
            specs["gpu"]["model"] = f"Radeon RX {rx_match.group(1).upper()}"
            specs["gpu"]["integrated"] = False
            self._extract_gpu_vram(gpu_text, full_search, context, specs, envelopes)
            self._extract_gpu_details(gpu_text, full_search, routed_table, specs)
            return

        # Intel Arc Discrete (e.g. Arc A370M, Arc A530M)
        arc_disc_match = re.search(r"\bintel\s+arc\s+(a\d{3}m)\b|\barc\s+(a\d{3}m)\b", full_search, re.IGNORECASE)
        if arc_disc_match:
            arc_code = (arc_disc_match.group(1) or arc_disc_match.group(2)).upper()
            specs["gpu"]["manufacturer"] = "Intel"
            specs["gpu"]["model"] = f"Intel Arc {arc_code}"
            specs["gpu"]["integrated"] = False
            self._extract_gpu_vram(gpu_text, full_search, context, specs, envelopes)
            self._extract_gpu_details(gpu_text, full_search, routed_table, specs)
            return

        # 2. Check for integrated GPU
        if re.search(
            r"\b(integrated|intel\s+uhd|intel\s+iris|intel\s+arc|radeon\s+graphics|adreno)\b",
            full_search,
            re.IGNORECASE,
        ):
            specs["gpu"]["integrated"] = True
            if cpu_context and cpu_context.get("integrated_gpu"):
                specs["gpu"]["model"] = cpu_context["integrated_gpu"]
                if "Intel" in cpu_context["integrated_gpu"]:
                    specs["gpu"]["manufacturer"] = "Intel"
                elif "AMD" in cpu_context["integrated_gpu"] or "Radeon" in cpu_context["integrated_gpu"]:
                    specs["gpu"]["manufacturer"] = "AMD"
                elif "Qualcomm" in cpu_context["integrated_gpu"] or "Adreno" in cpu_context["integrated_gpu"]:
                    specs["gpu"]["manufacturer"] = "Qualcomm"
                elif "Apple" in cpu_context["integrated_gpu"]:
                    specs["gpu"]["manufacturer"] = "Apple"
            self._extract_gpu_details(gpu_text, full_search, routed_table, specs)
            return

        # If completely unextracted
        envelopes.append(
            ExtractionEnvelope(
                field_path="gpu.model",
                field_description="GPU model name",
                raw_context=context or full_search[:300],
                failure_reason="missing_key",
                expected_type="str",
                section_name="Graphics",
            )
        )

    def _extract_gpu_vram(
        self,
        gpu_text: str,
        full_search: str,
        context: str,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
    ) -> None:
        """Helper to extract and validate discrete VRAM."""
        vram_search = f"{gpu_text} {full_search}"
        vram_match = re.search(r"(\d+)\s*(?:gb|g)\s*(?:gddr\d|vram)?", vram_search, re.IGNORECASE)
        if vram_match:
            vram = int(vram_match.group(1))
            valid, vram_clean, _ = PhysicalValidator.validate_gpu_vram(vram)
            if valid:
                specs["gpu"]["vram_gb"] = vram_clean
                return

        envelopes.append(
            ExtractionEnvelope(
                field_path="gpu.vram_gb",
                field_description="Discrete GPU VRAM capacity in GB",
                raw_context=context or gpu_text,
                failure_reason="missing_key" if not vram_match else "validation_failed",
                expected_type="int",
                section_name="Graphics",
            )
        )

    def _extract_gpu_details(
        self,
        gpu_text: str,
        full_search: str,
        routed_table: dict[str, list[tuple[str, str]]],
        specs: dict[str, Any],
    ) -> None:
        """Extract TGP (tdp_w), GPU Boost Clock (MHz), and AI TOPS."""
        pwr_rows = routed_table.get("gpu_power", [])
        pwr_text = " ".join(v for _, v in pwr_rows) + " " + gpu_text
        m_tgp = re.search(r"\b(\d{2,3})\s*w\b", pwr_text, re.IGNORECASE)
        if m_tgp:
            valid, clean_w, _ = PhysicalValidator.validate_gpu_power(m_tgp.group(1))
            if valid:
                specs["gpu"]["tdp_w"] = clean_w

        boost_rows = routed_table.get("gpu_boost", [])
        boost_text = " ".join(v for _, v in boost_rows) + " " + gpu_text
        m_boost = re.search(r"\b([12]\d{3})\s*mhzx?\b", boost_text, re.IGNORECASE)
        if m_boost:
            valid, clean_boost, _ = PhysicalValidator.validate_gpu_boost(m_boost.group(1))
            if valid:
                specs["gpu"]["boost_clock_mhz"] = clean_boost

        ai_rows = routed_table.get("ai_performance", [])
        ai_text = " ".join(v for _, v in ai_rows) + " " + gpu_text
        m_ai = re.search(r"\b(\d{2,4})\s*(?:ai\s*)?tops\b", ai_text, re.IGNORECASE)
        if not m_ai and ai_rows:
            m_ai = re.search(r"\b(\d{2,4})\b", ai_text)
        if m_ai:
            cand_ai = int(m_ai.group(1))
            if cand_ai >= 50:
                specs["gpu"]["ai_tops"] = cand_ai

    def _extract_memory(
        self,
        title: str,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
        cpu_context: dict[str, Any] | None = None,
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["memory"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"memory", "max_memory", "memory_slots", "memory_speed", "memory_type"},
            fallback_text=context,
        )

        mem_rows = routed_table.get("memory", [])
        mem_text = " ".join(v for _, v in mem_rows).strip()

        if not mem_text:
            for k, v in table.items():
                kl = k.lower()
                if ("ram" in kl or "memory" in kl) and not any(
                    bad in kl
                    for bad in [
                        "graphic",
                        "graphics",
                        "gpu",
                        "vga",
                        "video",
                        "dedicated",
                        "optane",
                        "cache",
                        "rom",
                        "max",
                        "support",
                    ]
                ):
                    mem_text += f" {v}"

        primary_text = f"{mem_text} {context}".strip()
        search_targets = [primary_text, title] if primary_text else [title]

        cap_val = None

        # Check hybrid multi-stick configuration first (e.g. "8GB Soldered DDR5-4800 + 8GB SODIMM" or "8GB DDR4 onboard + 8GB DDR4 SO-DIMM")
        for target in search_targets:
            m_hybrid = re.search(
                r"(\d+)\s*GB\s*(?:(?:DDR[345]|LPDDR[45]x?)\s*)?(?:soldered|onboard|on-board|on\s*board)[^+]*\+\s*(\d+)\s*GB\s*(?:(?:DDR[345]|LPDDR[45]x?)\s*)?(?:sodimm|so-dimm)",
                target,
                re.IGNORECASE,
            )
            if m_hybrid:
                cand = int(m_hybrid.group(1)) + int(m_hybrid.group(2))
                valid, cap_clean, _ = PhysicalValidator.validate_memory_capacity(cand, cpu_context)
                if valid:
                    cap_val = cap_clean
                    break

        if not cap_val:
            for _, v in mem_rows:
                # 1. Multi-DIMM check (e.g. 2x 16GB or 2 × 16GB -> 32GB)
                m_dimm = re.search(r"\b(\d+)\s*[xX×]\s*(\d+)\s*(?:gb|g)\b", v, re.IGNORECASE)
                if m_dimm:
                    count = int(m_dimm.group(1))
                    mod_size = int(m_dimm.group(2))
                    cand = count * mod_size if count > 1 else mod_size
                    valid, cap_clean, _ = PhysicalValidator.validate_memory_capacity(cand, cpu_context)
                    if valid:
                        cap_val = cap_clean
                        break

                # 2. Direct leading capacity e.g. "16 GB (2 x 8 GB)" -> 16
                m_direct = re.search(r"^\s*(\d+)\s*(?:gb|g)\b", v, re.IGNORECASE)
                if m_direct:
                    cand = int(m_direct.group(1))
                    valid, cap_clean, _ = PhysicalValidator.validate_memory_capacity(cand, cpu_context)
                    if valid:
                        cap_val = cap_clean
                        break

        if not cap_val:
            for target in search_targets:
                # 1. Multi-DIMM check first
                m_dimm = re.search(r"\b(\d+)\s*[xX×]\s*(\d+)\s*(?:gb|g)\b", target, re.IGNORECASE)
                if m_dimm:
                    count = int(m_dimm.group(1))
                    mod_size = int(m_dimm.group(2))
                    cand = count * mod_size if count > 1 else mod_size
                    valid, cap_clean, _ = PhysicalValidator.validate_memory_capacity(cand, cpu_context)
                    if valid:
                        cap_val = cap_clean
                        break

                # 2. Total capacity with optional configuration e.g. "16 GB (2 x 8 GB)" or "16GB RAM"
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

                # 3. Fallback generic match: ignoring SSD, HDD, VRAM, and GPU models (e.g. RTX 4050 6GB)
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

        # Type: Check memory_type bucket, then primary text, then title
        type_targets = [v for _, v in routed_table.get("memory_type", [])] + search_targets
        for target in type_targets:
            type_match = re.search(
                r"\b(lpddr5x|lpddr5|lpddr4x|lpddr4|ddr5|ddr4|unified memory)\b", target, re.IGNORECASE
            )
            if type_match:
                ram_type = type_match.group(1)
                valid, type_clean, _ = PhysicalValidator.validate_memory_type(ram_type, cpu_context)
                if valid:
                    specs["memory"]["memory_type"] = type_clean
                    break
        if not specs["memory"]["memory_type"]:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="memory.memory_type",
                    field_description="RAM generation type (e.g. DDR5, LPDDR5X)",
                    raw_context=context or primary_text or title,
                    failure_reason="missing_key",
                    expected_type="str",
                    allowed_values=["DDR4", "DDR5", "LPDDR4", "LPDDR4X", "LPDDR5", "LPDDR5X", "Unified Memory"],
                    cpu_context=cpu_context,
                    section_name="Memory",
                )
            )

        # Speed: e.g. 5600 MHz or 5.60 GT/s
        speed_targets = [v for _, v in routed_table.get("memory_speed", [])] + [primary_text]
        for target in speed_targets:
            spd_gt = re.search(r"\b([2-8]\.\d{1,2})\s*gt/s\b", target, re.IGNORECASE)
            if spd_gt:
                gt_val = float(spd_gt.group(1))
                mhz_calc = int(round(gt_val * 1000))
                specs["memory"]["speed"] = f"{mhz_calc} MHz"
                break
            spd_match = re.search(r"\b([4-8]\d{3})\s*(?:mhz|mt/s)\b", target, re.IGNORECASE)
            if spd_match:
                specs["memory"]["speed"] = f"{spd_match.group(1)} MHz"
                break

        # Slots & Max Memory
        slot_rows = list(routed_table.get("memory_slots", []))
        # Also check storage slots/expansion rows that contain memory slot keywords
        for k, v in table.items():
            kl = k.lower()
            if any(term in kl for term in ["memory slot", "ram slot", "expansion slot", "slots"]):
                if any(w in v.lower() for w in ["so-dimm", "sodimm", "csodimm", "ddr", "ram", "memory"]):
                    slot_rows.append((k, v))

        slot_text = " ".join(v for _, v in slot_rows)
        if slot_text:
            m_sod = re.search(r"\b(\d+)\s*(?:ddr[45]\s*)?(?:csodimm|so-?dimm)\b", slot_text, re.IGNORECASE)
            if m_sod:
                specs["memory"]["slot_count"] = int(m_sod.group(1))
            elif any(
                term in slot_text.lower()
                for term in ["no slots", "no expansion", "not upgradable", "0 slots", "zero slots"]
            ):
                specs["memory"]["slot_count"] = 0
            elif "soldered to systemboard" in slot_text.lower() and not re.search(
                r"\b(?:sodimm|so-dimm|slot)\b", slot_text.lower()
            ):
                specs["memory"]["slot_count"] = 0
            elif re.search(r"\b(two|dual)\b", slot_text, re.IGNORECASE) and re.search(
                r"\b(?:ddr[45]\s*)?(?:csodimm|so-?dimm|slots?)\b", slot_text, re.IGNORECASE
            ):
                specs["memory"]["slot_count"] = 2
            elif re.search(r"\b(one|single)\b\s+(?:ddr[45]\s*)?(?:sodimm|so-dimm|slot)", slot_text, re.IGNORECASE):
                specs["memory"]["slot_count"] = 1
            else:
                m_sl = re.search(
                    r"\b([1-4])\s*(?:x\s*)?(?:ddr[45]\s*)?(?:csodimm|so-?dimm|slots?)\b|ram,\s*number\s*of\s*slots:\s*([1-4])",
                    slot_text,
                    re.IGNORECASE,
                )
                if m_sl:
                    cnt = m_sl.group(1) or m_sl.group(2)
                    specs["memory"]["slot_count"] = int(cnt)
        elif not specs["memory"]["slot_count"]:
            m_dual = re.search(r"\(\s*(\d+)\s*x\s*\d+\s*(?:gb|g)?\s*\)", mem_text, re.IGNORECASE)
            if m_dual:
                specs["memory"]["slot_count"] = int(m_dual.group(1))

        max_mem_rows = list(routed_table.get("max_memory", []))
        if not max_mem_rows:
            max_mem_rows = [
                (k, v)
                for k, v in table.items()
                if any(
                    term in k.lower() for term in ["max memory", "maximum memory", "maximum supported system memory"]
                )
            ]
        if max_mem_rows:
            max_text = " ".join(v for _, v in max_mem_rows)
            m_max = re.search(
                r"\b(?:up\s+to\s*|max(?:imum)?\s*(?:supported\s*(?:system\s*)?memory|memory|ram)?\s*[:\s]*|^)\s*(\d{1,3})\s*(?:gb|g)\b",
                max_text,
                re.IGNORECASE,
            )
            if m_max:
                specs["memory"]["max_supported_gb"] = int(m_max.group(1))

        # Soldered vs Upgradeable
        mem_all = f"{mem_text} {' '.join(v for _, v in slot_rows)} {' '.join(v for _, v in routed_table.get('memory_type', []))}"
        if re.search(
            r"\b(soldered|on-board|onboard|on\s+board|integrated|unified\s+memory|lpddr[45]x?)\b",
            mem_all,
            re.IGNORECASE,
        ):
            specs["memory"]["is_soldered"] = True
        elif re.search(r"\b(sodimm|so-dimm|upgradeable|removable)\b", mem_all, re.IGNORECASE) or (
            specs["memory"]["slot_count"] and specs["memory"]["slot_count"] > 0
        ):
            specs["memory"]["is_soldered"] = False

    def _extract_storage(
        self,
        title: str,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["storage"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"storage", "max_storage", "storage_slots", "storage_interface"},
            fallback_text=context,
        )

        storage_rows = routed_table.get("storage", [])
        storage_text = " ".join(v for _, v in storage_rows).strip()

        if not storage_text:
            for k, v in table.items():
                kl = k.lower()
                if any(s in kl for s in ["storage", "ssd", "hdd", "disk", "hard drive"]) and not any(
                    bad in kl for bad in ["max", "support", "slot", "expansion", "upgrade"]
                ):
                    storage_text += f" {v}"

        # Prioritize specification table text first! Only fallback to context/title if table is empty
        search_targets = [storage_text, title] if storage_text else [context, title]

        for target in search_targets:
            # Strip expansion limit phrases like "up to 4TB" or "supports up to 4TB"
            clean_tgt = re.sub(
                r"\b(?:up\s+to|support(?:s)?\s*(?:up\s+to)?)\s*\d+\s*(?:tb|gb)\b", "", target, flags=re.I
            )

            # Check HDD vs SSD
            if re.search(r"\b\d+\s*(?:tb|gb)\s*hdd\b", clean_tgt, re.I):
                st_type = "HDD"
            elif bool(re.search(r"\b(?:hdd|hard\s*drive|hard\s*disk)\b", clean_tgt, re.I)) and not bool(
                re.search(r"\b(?:ssd|nvme)\b", re.sub(r"\bsupport[a-z]*\s+nvme\b", "", clean_tgt, flags=re.I), re.I)
            ):
                st_type = "HDD"
            else:
                st_type = "SSD"

            # 1TB to 4TB
            tb_match = re.search(r"\b([1-4])\s*tb\b", clean_tgt, re.IGNORECASE)
            if tb_match:
                specs["storage"]["capacity_gb"] = int(tb_match.group(1)) * 1024
                specs["storage"]["storage_type"] = st_type
                break

            # GB
            gb_match = re.search(r"\b(128|256|512)\s*gb\s*(?:ssd|nvme|pcie|emmc|hdd)?\b", clean_tgt, re.IGNORECASE)
            if gb_match:
                specs["storage"]["capacity_gb"] = int(gb_match.group(1))
                specs["storage"]["storage_type"] = st_type
                break

        # Storage interface & form factor search context
        search_all_storage = f"{storage_text} {' '.join(v for _, v in routed_table.get('storage_interface', []))} {' '.join(v for _, v in routed_table.get('storage_form_factor', []))} {title}"

        # 1. Interface (e.g. PCIe Gen4 NVMe, PCIe 4.0 NVMe, NVMe, SATA III)
        m_if = re.search(
            r"\b(PCIe\s*(?:Gen\s*)?[345](?:\.0)?(?:\s*[xX×]\s*[24])?(?:\s*NVMe)?|NVMe\s*PCIe|NVMe|SATA(?:\s*III)?)\b",
            search_all_storage,
            re.IGNORECASE,
        )
        if m_if:
            raw_if = m_if.group(1).strip()
            if re.search(r"pcie\s*(?:gen\s*)?4(?:\.0)?(?:\s*[xX×]\s*4)?\s*nvme", raw_if, re.I):
                specs["storage"]["interface"] = "PCIe 4.0 NVMe"
            elif re.search(r"pcie\s*(?:gen\s*)?5(?:\.0)?(?:\s*[xX×]\s*4)?\s*nvme", raw_if, re.I):
                specs["storage"]["interface"] = "PCIe 5.0 NVMe"
            elif re.search(r"pcie\s*(?:gen\s*)?3(?:\.0)?(?:\s*[xX×]\s*4)?\s*nvme", raw_if, re.I):
                specs["storage"]["interface"] = "PCIe 3.0 NVMe"
            elif re.search(r"pcie\s*(?:gen\s*)?4(?:\.0)?", raw_if, re.I):
                specs["storage"]["interface"] = "PCIe 4.0"
            elif re.search(r"pcie\s*(?:gen\s*)?5(?:\.0)?", raw_if, re.I):
                specs["storage"]["interface"] = "PCIe 5.0"
            elif re.search(r"pcie\s*(?:gen\s*)?3(?:\.0)?", raw_if, re.I):
                specs["storage"]["interface"] = "PCIe 3.0"
            elif re.search(r"nvme", raw_if, re.I):
                specs["storage"]["interface"] = "NVMe"
            elif re.search(r"sata", raw_if, re.I):
                specs["storage"]["interface"] = "SATA III"
            else:
                specs["storage"]["interface"] = raw_if

        # 2. Form Factor (e.g. M.2 2280, M.2 2242, M.2, 2.5-inch)
        m_ff = re.search(
            r"\b(M\.2\s*(?:2280|2242|2230)?|2\.5(?:-inch|\")?)\b",
            search_all_storage,
            re.IGNORECASE,
        )
        if m_ff:
            raw_ff = m_ff.group(1).strip()
            raw_ff = re.sub(r"\s+", " ", raw_ff)
            if "2.5" in raw_ff:
                specs["storage"]["form_factor"] = "2.5-inch"
            else:
                specs["storage"]["form_factor"] = raw_ff

        # 3. Storage Slots
        slot_rows = list(routed_table.get("storage_slots", []))
        max_st_rows = list(routed_table.get("max_storage", []))
        all_slot_text = f"{' '.join(v for _, v in slot_rows)} {' '.join(v for _, v in max_st_rows)}"
        if not all_slot_text.strip():
            for k, v in table.items():
                if any(w in k.lower() for w in ["storage slot", "m.2 slot", "storage capability", "storage support"]):
                    all_slot_text += f" {v}"

        # Clean out "GEN 4 slot" or "PCIe 4.0 slot" or "Gen4 Slot" false triggers
        clean_slot_text = re.sub(
            r"\b(?:gen|pcie|pcie\s*gen)\s*[345](?:\.0)?(?:\s*[xX×]\s*[24])?\s*(?:m\.2\s*)?slots?\b",
            "m.2 slot",
            all_slot_text,
            flags=re.I,
        )

        # Look for multi-slot sum e.g. "1 × M.2 ... Slot and 1 × M.2 ... Slot"
        m_and_slots = re.findall(r"\b1\s*[^a-zA-Z0-9\s]?\s*m\.2[^\n,]*?slot", all_slot_text, re.I)
        if len(m_and_slots) >= 2:
            specs["storage"]["slot_count"] = len(m_and_slots)
        elif re.search(r"\b(?:supports\s+only\s+one|only\s+one|one\s+m\.2)\b", all_slot_text, re.I):
            specs["storage"]["slot_count"] = 1
        elif re.search(
            r"\b(?:extra\s+m\.2\s+slot|second\s+m\.2|two\s+drives|2x\s*m\.2|two\s+m\.2)\b", all_slot_text, re.I
        ):
            specs["storage"]["slot_count"] = 2
        else:
            m_sc = re.search(
                r"\b(?:total\s*)?([1-4])\s*[xX×]\s*m\.2|two\s+m\.2|up\s+to\s+two\s+drives|\b([1-4])\s*(?:m\.2\s*)?slots?\b",
                clean_slot_text,
                re.IGNORECASE,
            )
            if m_sc:
                if "two" in m_sc.group(0).lower():
                    specs["storage"]["slot_count"] = 2
                elif m_sc.group(1):
                    specs["storage"]["slot_count"] = int(m_sc.group(1))
                elif m_sc.group(2):
                    specs["storage"]["slot_count"] = int(m_sc.group(2))
                else:
                    specs["storage"]["slot_count"] = 2

        if specs["storage"].get("slot_count") is None:
            m_cnt = re.search(
                r"\b(?:ssd\s*count|number\s*of\s*ssds?(?:\s*installed)?)\s*[:=]?\s*([1-4])\b", str(table), re.IGNORECASE
            )
            if m_cnt:
                specs["storage"]["slot_count"] = int(m_cnt.group(1))

        # 4. Maximum Storage Support
        if max_st_rows:
            max_text = " ".join(v for _, v in max_st_rows)
            # Up to two drives... up to 1TB each
            m_two_each = re.search(
                r"(?:two\s+drives|2x\s+m\.2)[^,\n]*?up to\s*(\d+)\s*tb\s*each", max_text, re.IGNORECASE
            )
            if m_two_each:
                specs["storage"]["max_supported_gb"] = 2 * int(m_two_each.group(1)) * 1024
            else:
                m_mult = re.search(r"(\d+)\s*[xX×]\s*[^,\n]*?up to\s*(\d+)\s*tb\s*each", max_text, re.IGNORECASE)
                if m_mult:
                    specs["storage"]["max_supported_gb"] = int(m_mult.group(1)) * int(m_mult.group(2)) * 1024
                else:
                    m_tb = re.search(r"\b(?:up\s+to\s*)?([1-4])\s*tb\b", max_text, re.IGNORECASE)
                    if m_tb:
                        specs["storage"]["max_supported_gb"] = int(m_tb.group(1)) * 1024
                    else:
                        m_gb = re.search(r"\b(?:up\s+to\s*)?(\d{3,4})\s*gb\b", max_text, re.IGNORECASE)
                        if m_gb:
                            specs["storage"]["max_supported_gb"] = int(m_gb.group(1))

        if not specs["storage"]["capacity_gb"]:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="storage.capacity_gb",
                    field_description="Primary storage capacity in GB",
                    raw_context=context or storage_text or title,
                    failure_reason="missing_key",
                    expected_type="int",
                    section_name="Storage",
                )
            )

    def _extract_display(
        self,
        title: str,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["display"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"display"},
            fallback_text=context,
        )

        disp_rows = routed_table.get("display", [])
        disp_text = " ".join(v for _, v in disp_rows).strip()
        if not disp_text:
            for k, v in table.items():
                if any(d in k.lower() for d in ["display", "screen", "panel"]):
                    disp_text += f" {v}"

        # Prioritize specification table text first! Only fallback to title if table is empty
        primary_text = f"{disp_text} {context}".strip()
        search_targets = [primary_text, title] if primary_text else [title]

        # Screen size
        for target in search_targets:
            size_match = re.search(
                r"\b(1[0-8](?:\.\d)?)\s*(?:inches|inch|[\"”″“']|''|-inch|\b(?=[fF][hH][dD]|[qQ][hH][dD]|[uU][hH][dD]|[oO][lL][eE][dD]|[iI][pP][sS]|[wW][uU][xX][gG][aA]|[wW][qQ][xX][gG][aA]))(?!\w)",
                target,
                re.IGNORECASE,
            )
            if size_match:
                valid, clean_size, _ = PhysicalValidator.validate_display_size(size_match.group(1))
                if valid:
                    specs["display"]["size_inches"] = clean_size
                    break

        if not specs["display"]["size_inches"]:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="display.size_inches",
                    field_description="Display screen diagonal size in inches",
                    raw_context=context or primary_text or title,
                    failure_reason="missing_key",
                    expected_type="float",
                    section_name="Display",
                )
            )

        # Refresh rate
        for target in search_targets:
            hz_match = re.search(r"\b(\d{2,3})\s*hz\b", target, re.IGNORECASE)
            if hz_match:
                valid, clean_hz, _ = PhysicalValidator.validate_refresh_rate(hz_match.group(1))
                if valid:
                    specs["display"]["refresh_rate_hz"] = clean_hz
                    break

        if not specs["display"]["refresh_rate_hz"]:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="display.refresh_rate_hz",
                    field_description="Display refresh rate in Hz",
                    raw_context=context or primary_text or title,
                    failure_reason="missing_key",
                    expected_type="int",
                    section_name="Display",
                )
            )

        # Resolution
        for target in search_targets:
            res_match = re.search(r"\b(\d{3,4})\s*[xX×]\s*(\d{3,4})\b", target)
            if res_match:
                w = int(res_match.group(1))
                h = int(res_match.group(2))
                if 1024 <= w <= 7680 and 600 <= h <= 4320:
                    specs["display"]["resolution_width"] = w
                    specs["display"]["resolution_height"] = h
                    specs["display"]["resolution"] = f"{w}x{h}"
                    break

        if not specs["display"]["resolution"]:
            for target in search_targets:
                if re.search(r"\b(?:4k|uhd)\b", target, re.I):
                    specs["display"]["resolution_width"] = 3840
                    specs["display"]["resolution_height"] = 2160
                    specs["display"]["resolution"] = "3840x2160"
                    break
                elif re.search(r"\b3k\b", target, re.I):
                    specs["display"]["resolution_width"] = 2880
                    specs["display"]["resolution_height"] = 1800
                    specs["display"]["resolution"] = "2880x1800"
                    break
                elif re.search(r"\b(?:2\.5k|wqxga|qhd\+|qhd\s*plus)\b", target, re.I):
                    specs["display"]["resolution_width"] = 2560
                    specs["display"]["resolution_height"] = 1600
                    specs["display"]["resolution"] = "2560x1600"
                    break
                elif re.search(r"\bqhd\b", target, re.I):
                    if "16:10" in target:
                        specs["display"]["resolution_width"] = 2560
                        specs["display"]["resolution_height"] = 1600
                        specs["display"]["resolution"] = "2560x1600"
                    else:
                        specs["display"]["resolution_width"] = 2560
                        specs["display"]["resolution_height"] = 1440
                        specs["display"]["resolution"] = "2560x1440"
                    break
                elif re.search(r"\bwuxga\b", target, re.I):
                    specs["display"]["resolution_width"] = 1920
                    specs["display"]["resolution_height"] = 1200
                    specs["display"]["resolution"] = "1920x1200"
                    break
                elif re.search(r"\bfhd\b", target, re.I):
                    specs["display"]["resolution_width"] = 1920
                    specs["display"]["resolution_height"] = 1080
                    specs["display"]["resolution"] = "1920x1080"
                    break

        # Aspect Ratio
        for target in search_targets:
            ar_match = re.search(r"\b(16:9|16:10|3:2|4:3|21:9)\b", target)
            if ar_match:
                specs["display"]["aspect_ratio"] = ar_match.group(1)
                break

        if (
            not specs["display"]["aspect_ratio"]
            and specs["display"]["resolution_width"]
            and specs["display"]["resolution_height"]
        ):
            ratio = specs["display"]["resolution_width"] / specs["display"]["resolution_height"]
            if abs(ratio - 16 / 9) < 0.03:
                specs["display"]["aspect_ratio"] = "16:9"
            elif abs(ratio - 16 / 10) < 0.03:
                specs["display"]["aspect_ratio"] = "16:10"
            elif abs(ratio - 3 / 2) < 0.03:
                specs["display"]["aspect_ratio"] = "3:2"
            elif abs(ratio - 4 / 3) < 0.03:
                specs["display"]["aspect_ratio"] = "4:3"
            elif abs(ratio - 21 / 9) < 0.05:
                specs["display"]["aspect_ratio"] = "21:9"

        # Panel Type
        for target in search_targets:
            panel_match = re.search(r"\b(oled|amoled|ips|mini-led|retina|tn|va)\b", target, re.IGNORECASE)
            if panel_match:
                specs["display"]["panel_type"] = panel_match.group(1).upper()
                break

        # Brightness (nits)
        bright_rows = routed_table.get("display_brightness", [])
        bright_text = " ".join(v for _, v in bright_rows)
        m_br = re.search(r"(\d{3,4})\s*(?:nits?|cd/m[²2])", f"{bright_text} {primary_text}", re.IGNORECASE)
        if not m_br and bright_rows:
            m_br = re.search(r"\b([2-9]\d{2}|1\d{3})\b", bright_text)
        if m_br:
            valid, clean_br, _ = PhysicalValidator.validate_brightness(m_br.group(1))
            if valid:
                specs["display"]["brightness_nits"] = clean_br

        # Color Gamut
        gamut_rows = routed_table.get("display_gamut", [])
        gamut_text = " ".join(v for _, v in gamut_rows)
        m_gamut = re.search(
            r"\b(\d{2,3}(?:\.\d+)?%\s*(?:sRGB|NTSC|DCI-P3|Adobe\s*RGB))\b",
            f"{gamut_text} {primary_text}",
            re.IGNORECASE,
        )
        if m_gamut:
            specs["display"]["color_gamut"] = m_gamut.group(1).strip()
        elif gamut_rows:
            for _, gv in gamut_rows:
                gvs = gv.strip()
                if "%" in gvs and len(gvs) <= 40:
                    specs["display"]["color_gamut"] = gvs
                    break

        # Response Time (ms)
        resp_rows = routed_table.get("display_response_time", [])
        resp_text = " ".join(v for _, v in resp_rows)
        m_resp = re.search(r"(\d+(?:\.\d+)?)\s*ms\b", f"{resp_text} {primary_text}", re.IGNORECASE)
        if m_resp:
            valid, clean_resp, _ = PhysicalValidator.validate_response_time(m_resp.group(1))
            if valid:
                specs["display"]["response_time_ms"] = clean_resp

        # Surface Treatment
        surf_rows = routed_table.get("display_surface", [])
        surf_text = f"{' '.join(v for _, v in surf_rows)} {primary_text}".lower()
        if "anti-reflect" in surf_text:
            specs["display"]["surface_treatment"] = "Anti-reflection"
        elif "anti-glare" in surf_text or "anti glare" in surf_text or "ag display" in surf_text:
            specs["display"]["surface_treatment"] = "Anti-glare"
        elif "matte" in surf_text or "comfyview" in surf_text:
            specs["display"]["surface_treatment"] = "Matte"
        elif "glossy" in surf_text:
            specs["display"]["surface_treatment"] = "Glossy"

        # HDR: strictly require genuine HDR certifications/standards
        hdr_rows = routed_table.get("display_hdr", [])
        hdr_text = f"{' '.join(v for _, v in hdr_rows)} {primary_text}"
        m_hdr = re.search(
            r"\b((?:VESA\s+)?DisplayHDR(?:\s+True\s+Black)?\s*(?:400|500|600|1000|1400)?|Dolby\s*Vision|HDR\s*10(?:\+)?|HDR\s*(?:400|500|600|1000|1400)?(?:\s+True\s+Black)?)\b",
            hdr_text,
            re.IGNORECASE,
        )
        if m_hdr:
            specs["display"]["hdr"] = m_hdr.group(1).strip()
        elif any("dolby vision" in k.lower() and "yes" in v.lower() for k, v in table.items()):
            specs["display"]["hdr"] = "Dolby Vision"
        elif hdr_rows:
            for _, hv in hdr_rows:
                hvs = hv.strip()
                if not hvs or any(bad in hvs.lower() for bad in ["no", "none", "false", "n/a"]):
                    continue
                if any(
                    bad in hvs.lower()
                    for bad in ["srgb", "ntsc", "dci-p3", "adobe rgb", "%", "color", "gamut", "depth"]
                ):
                    continue
                if re.search(r"\bhdr\b", hvs, re.I):
                    specs["display"]["hdr"] = hvs
                    break

        # Touchscreen
        touch_targets = [primary_text, title, " ".join(table.values())]
        for tt in touch_targets:
            if not tt:
                continue
            if re.search(
                r"\b(?:touchscreen|touch\s*screen|multi-touch|touch\s+display|touch\s+\d+hz|dual\s+16[″\"]\s+3k\s+oled\s+touch)\b",
                tt,
                re.I,
            ):
                if not re.search(r"\b(?:non-touch|no\s+touch)\b", tt, re.I):
                    specs["display"]["touchscreen"] = True
                    break
            elif re.search(r"\btouch\b", tt, re.I) and not re.search(
                r"\b(?:touchpad|touch\s*pad|non-touch|no\s+touch)\b", tt, re.I
            ):
                specs["display"]["touchscreen"] = True
                break

        for k, v in table.items():
            if "touch" in k.lower() and "pad" not in k.lower():
                vl = v.lower()
                if any(yes in vl for yes in ["yes", "true", "supported"]):
                    specs["display"]["touchscreen"] = True
                    break
                elif any(no in vl for no in ["no", "false", "non-touch"]):
                    specs["display"]["touchscreen"] = False
                    break

        if not specs["display"]["panel_type"]:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="display.panel_type",
                    field_description="Display panel type (IPS, OLED, TN, etc.)",
                    raw_context=context or primary_text or title,
                    failure_reason="missing_key",
                    expected_type="str",
                    allowed_values=["IPS", "OLED", "AMOLED", "TN", "VA", "Mini-LED"],
                    section_name="Display",
                )
            )

    def _extract_power(
        self,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
        cpu_context: dict[str, Any] | None = None,
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["power_battery"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"power"},
            fallback_text=context,
        )

        pwr_rows = routed_table.get("power", [])
        pwr_text = " ".join(v for _, v in pwr_rows).strip()
        if not pwr_text:
            for k, v in table.items():
                if any(p in k.lower() for p in ["battery", "power", "adapter"]):
                    pwr_text += f" {v}"
        full_search = f"{pwr_text} {context}"

        # Battery Wh
        wh_match = re.search(r"\b(\d{2}(?:\.\d)?)\s*(?:wh(?:rs)?|watt-hours?)\b", full_search, re.IGNORECASE)
        if wh_match:
            valid, clean_wh, _ = PhysicalValidator.validate_battery_capacity(wh_match.group(1))
            if valid:
                specs["power_battery"]["battery_capacity_wh"] = clean_wh
            else:
                envelopes.append(
                    ExtractionEnvelope(
                        field_path="power_battery.battery_capacity_wh",
                        field_description="Battery capacity in watt-hours (Wh)",
                        raw_context=context or full_search,
                        failure_reason="validation_failed",
                        expected_type="float",
                        section_name="Battery & Power",
                    )
                )
        else:
            envelopes.append(
                ExtractionEnvelope(
                    field_path="power_battery.battery_capacity_wh",
                    field_description="Battery capacity in watt-hours (Wh)",
                    raw_context=context or full_search,
                    failure_reason="missing_key",
                    expected_type="float",
                    section_name="Battery & Power",
                )
            )

        # Power Adapter W (strictly require adapter/charger context; reject CPU/GPU turbo/PL2 power)
        adapter_rows = [
            v
            for k, v in table.items()
            if any(t in k.lower() for t in ["adapter", "charger", "power supply", "power adapter"])
        ]
        adapter_text = " ".join(adapter_rows)
        w_match = None
        if adapter_text:
            w_match = re.search(r"\b(\d{2,3})\s*w\b", adapter_text, re.IGNORECASE)

        if not w_match:
            clean_pwr_lines = [
                line
                for line in full_search.split("\n")
                if not any(
                    bad in line.lower()
                    for bad in ["turbo power", "base power", "tgp", "tdp", "pl1", "pl2", "cpu power", "graphics power"]
                )
            ]
            clean_pwr_search = " ".join(clean_pwr_lines)
            w_match = re.search(
                r"\b(\d{2,3})\s*w\s*(?:(?:smart\s+)?ac\s+adapter|adapter|charger|power\s+supply|power\s+adapter|barrel|tip|usb-c\s+adapter)\b",
                clean_pwr_search,
                re.IGNORECASE,
            )

        if w_match:
            valid, clean_w, _ = PhysicalValidator.validate_power_adapter(w_match.group(1), cpu_context)
            if valid:
                specs["power_battery"]["power_adapter_w"] = clean_w

        # Battery Cells
        cell_match = re.search(r"\b([2-6])\s*[- ]\s*cells?\b|battery\s+cells?:\s*([2-6])\b", full_search, re.IGNORECASE)
        if cell_match:
            cand_cells = int(cell_match.group(1) or cell_match.group(2))
            specs["power_battery"]["battery_cells"] = cand_cells

        # Fast Charging
        fc_val = None
        for k, v in table.items():
            kl = k.lower()
            if any(term in kl for term in ["fast charge", "fast charging", "rapid charge"]):
                vs = v.strip()
                if vs and not any(bad in vs.lower() for bad in ["no", "none", "not supported", "false"]):
                    m_time = re.search(r"(\d+%\s*in\s*(?:about\s*)?\d+\s*min(?:utes)?)", vs, re.IGNORECASE)
                    if m_time:
                        fc_val = m_time.group(1).strip()
                    elif any(good in vs.lower() for good in ["yes", "supported"]):
                        fc_val = "Supported"
                    else:
                        fc_val = vs
                    break

        if not fc_val:
            m_emb = re.search(
                r"(recharge\s+from\s+0-50%\s+in\s+(?:about\s+)?\d+\s*min(?:utes)?|supports\s+battery\s+fast\s+charge[^\n,;]*|fast\s+charg\w+[^\n,;]*|rapid\s+charge(?:\s+pro)?)",
                full_search,
                re.IGNORECASE,
            )
            if m_emb:
                cand_fc = m_emb.group(1).strip()
                cand_fc = re.split(r"[|\n)]", cand_fc)[0].strip()
                if cand_fc:
                    fc_val = cand_fc

        if fc_val:
            specs["power_battery"]["fast_charging"] = fc_val

    def _extract_physical(
        self,
        title: str,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["physical"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"dimensions", "weight", "package_dimensions"},
            fallback_text=context,
        )

        dim_rows = routed_table.get("dimensions", [])
        weight_rows = routed_table.get("weight", [])
        color_rows = routed_table.get("color", [])

        dim_text = " ".join(v for _, v in dim_rows).strip()
        weight_text = " ".join(v for _, v in weight_rows).strip()
        color_text = " ".join(v for _, v in color_rows).strip()

        if not dim_text or not weight_text or not color_text:
            for k, v in table.items():
                kl = k.lower()
                if (
                    not dim_text
                    and any(p in kl for p in ["dimension", "dimensions (wxdxh)", "size"])
                    and "package" not in kl
                ):
                    dim_text += f" {v}"
                if not weight_text and "weight" in kl and "package" not in kl:
                    weight_text += f" {v}"
                if not color_text and any(p in kl for p in ["color", "case color", "product color"]):
                    color_text += f" {v}"

        full_search = f"{weight_text} {context}"

        # 1. Weight (kg)
        for wk, wv in weight_rows:
            if any(bad in wk.lower() for bad in ["package", "packaging", "packag", "box", "shipping"]):
                continue
            m = re.search(r"\b([0-4]\.\d{1,2})\b", wv)
            if m:
                valid, clean_wt, _ = PhysicalValidator.validate_weight(m.group(1))
                if valid:
                    specs["physical"]["weight_kg"] = clean_wt
                    break

        if specs["physical"]["weight_kg"] is None:
            clean_search = re.sub(
                r"\b(?:package\s*weight|packaging\s*weight|weight\s*in\s*packaging)[^|\n]*",
                "",
                full_search,
                flags=re.IGNORECASE,
            )
            wt_match = re.search(r"\b([0-4]\.\d{1,2})\s*kg\b", clean_search, re.IGNORECASE)
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

        # 2. Dimensions (Width, Depth, Height in mm)
        search_dim = f"{dim_text} {context}"
        w, d, h = self._parse_dimensions_text(search_dim)
        if w and d and h:
            valid, nw, nd, nh, _ = PhysicalValidator.normalize_dimensions(w, d, h)
            if valid:
                specs["physical"]["width_mm"] = nw
                specs["physical"]["depth_mm"] = nd
                specs["physical"]["height_mm"] = nh

        # 3. Color (only if not already set by _extract_identity)
        if not specs["identity"]["color"] and color_text.strip():
            c_clean = re.sub(r"\(.*?\)", "", color_text).strip()
            c_clean = re.split(
                r"\b(?:coverage|gamut|accuracy|\d+%\s*srgb|\d+%\s*ntsc|\d+%\s*dci-p3|oled|fhd|qhd|144hz|165hz|240hz|300-nit|brightness|displayhdr|dolby vision|x-rite|pantone)\b",
                c_clean,
                flags=re.IGNORECASE,
            )[0].strip(" ,-|/")
            m_rep = re.match(r"^(.+?)\s+\1$", c_clean, flags=re.IGNORECASE)
            if m_rep:
                c_clean = m_rep.group(1).strip()
            c_clean = re.sub(r"\b(\w+)\s+\1\b", r"\1", c_clean, flags=re.IGNORECASE).strip()
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

    def _parse_dimensions_text(self, text: str) -> tuple[float | None, float | None, float | None]:
        if not text:
            return None, None, None

        # 1. Labeled coordinates (Height: ... Width: ... Depth: ...)
        m_h = re.search(r"\bheight\b[^\d]*(\d+(?:\.\d+)?)\s*(mm|cm)?", text, re.I)
        m_w = re.search(r"\bwidth\b[^\d]*(\d+(?:\.\d+)?)\s*(mm|cm)?", text, re.I)
        m_d = re.search(r"\bdepth\b[^\d]*(\d+(?:\.\d+)?)\s*(mm|cm)?", text, re.I)
        if m_h and m_w and m_d:
            h_val = float(m_h.group(1))
            w_val = float(m_w.group(1))
            d_val = float(m_d.group(1))
            h_unit = m_h.group(2)
            if h_unit == "cm" or "cm" in text.lower():
                if h_val < 10:
                    h_val *= 10.0
                if w_val < 60:
                    w_val *= 10.0
                if d_val < 60:
                    d_val *= 10.0
            return w_val, d_val, h_val

        # 2. Triple measurement (e.g. 359.86 x 258.7 x 21.9-23.9 mm or 36.9 x 25.94 x 2.29 cm)
        m_trip = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:mm|cm)?\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm)?\s*[xX×*]\s*(\d+(?:\.\d+)?)(?:[-–—](\d+(?:\.\d+)?))?\s*(mm|cm)?",
            text,
        )
        if m_trip:
            v1 = float(m_trip.group(1))
            v2 = float(m_trip.group(2))
            v3 = float(m_trip.group(3))
            unit = m_trip.group(5)
            if unit == "cm" or (v1 < 60 and v2 < 60 and v3 < 60 and min(v1, v2, v3) < 4.5):
                v1 *= 10.0
                v2 *= 10.0
                v3 *= 10.0
            return v1, v2, v3

        return None, None, None

    def _extract_connectivity(
        self,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["connectivity"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"ports", "connectivity", "connectivity_and_ports", "card_reader"},
            fallback_text=context,
        )

        full_search = f"{' '.join(table.values())} {context}"

        # 1. WiFi
        if re.search(r"\bwi-?fi\s*7\b", full_search, re.IGNORECASE):
            specs["connectivity"]["wifi"] = "Wi-Fi 7"
        elif re.search(r"\bwi-?fi\s*6e\b", full_search, re.IGNORECASE):
            specs["connectivity"]["wifi"] = "Wi-Fi 6E"
        elif re.search(r"\bwi-?fi\s*6\b", full_search, re.IGNORECASE):
            specs["connectivity"]["wifi"] = "Wi-Fi 6"

        # 2. Bluetooth
        bt_match = re.search(r"\bbluetooth\s*(?:v?|version)?\s*([4-6](?:\.[0-4])?)\b", full_search, re.IGNORECASE)
        if bt_match:
            ver = bt_match.group(1)
            if "." not in ver:
                ver = f"{ver}.0"
            specs["connectivity"]["bluetooth"] = f"Bluetooth {ver}"
        elif re.search(r"\bbt\s*([4-6](?:\.[0-4])?)\b", full_search, re.IGNORECASE):
            m_bt = re.search(r"\bbt\s*([4-6](?:\.[0-4])?)\b", full_search, re.IGNORECASE)
            ver = m_bt.group(1)
            if "." not in ver:
                ver = f"{ver}.0"
            specs["connectivity"]["bluetooth"] = f"Bluetooth {ver}"

        # 3. Ports: Collect from routed ports bucket and any unrouted rows
        port_rows = routed_table.get("ports", [])
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
                    # Reject ISO dates (e.g. 2031-11-08)
                    if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}$", p_clean):
                        continue
                    # Reject lifecycle or support dates/metadata
                    if re.search(
                        r"\b(?:20\d\d[-/]\d\d[-/]\d\d|end of support|lifecycle|warranty)\b", p_clean, re.IGNORECASE
                    ):
                        continue
                    # Reject marketing phrases or non-port claims
                    if any(
                        bad in p_clean.lower()
                        for bad in [
                            "all the ports you need",
                            "built to dominate",
                            "connect with ease",
                            "support dolby vision",
                            "stylus support",
                            "supported ssd",
                            "support list",
                        ]
                    ):
                        continue
                    cleaned_ports.append(p_clean)

            if cleaned_ports:
                specs["connectivity"]["ports"] = cleaned_ports

        # 4. Ethernet
        for k, v in table.items():
            kl = k.lower()
            if "wlan" in kl or "wireless" in kl:
                continue
            if any(term in kl for term in ["ethernet", "rj-45", "rj45"]) or re.search(r"\b(?<!w)lan\b", kl):
                vs = str(v).strip()
                if not any(bad in vs.lower() for bad in ["none", "n/a", "no", "without"]):
                    specs["connectivity"]["ethernet"] = vs
                    break

        if not specs["connectivity"]["ethernet"] and specs["connectivity"]["ports"]:
            for p in specs["connectivity"]["ports"]:
                if re.search(r"\b(rj-?45|ethernet|lan)\b", p, re.IGNORECASE):
                    specs["connectivity"]["ethernet"] = p
                    break

        # 5. Thunderbolt Version
        tb_rows = [v for k, v in table.items() if "thunderbolt" in k.lower() or "thunderbolt" in v.lower()]
        tb_text = " ".join(tb_rows) + " " + " ".join(specs["connectivity"]["ports"])
        m_tb = re.search(r"\bthunderbolt\s*([345])\b", tb_text, re.IGNORECASE)
        if m_tb:
            specs["connectivity"]["thunderbolt_version"] = f"Thunderbolt {m_tb.group(1)}"
        elif re.search(r"\bthunderbolt\b", tb_text, re.IGNORECASE) and not any(
            bad in tb_text.lower() for bad in ["no thunderbolt", "without thunderbolt"]
        ):
            if not any(k.lower() == "interfaces, thunderbolt" and v.lower() == "no" for k, v in table.items()):
                specs["connectivity"]["thunderbolt_version"] = "Thunderbolt"

        # 6. Card Reader
        cr_rows = routed_table.get("card_reader", [])
        if not cr_rows:
            cr_rows = [(k, v) for k, v in table.items() if "card reader" in k.lower()]
        if cr_rows:
            for _, cv in cr_rows:
                cv_clean = cv.strip()
                cv_lower = cv_clean.lower()
                if any(bad in cv_lower for bad in ["no", "none", "false"]):
                    specs["connectivity"]["has_card_reader"] = False
                    break
                else:
                    specs["connectivity"]["has_card_reader"] = True
                    if re.search(r"\bsd\s*express\b", cv_lower):
                        specs["connectivity"]["card_reader_type"] = "SD Express"
                    elif re.search(r"\bmicrosd\b|\bmicro-sd\b", cv_lower):
                        specs["connectivity"]["card_reader_type"] = "MicroSD"
                    elif re.search(r"\b(\d-in-1)\b", cv_lower):
                        m_in1 = re.search(r"\b(\d-in-1)\b", cv_clean, re.IGNORECASE)
                        specs["connectivity"]["card_reader_type"] = f"{m_in1.group(1)} Card Reader"
                    elif re.search(r"\bsd\b", cv_lower):
                        specs["connectivity"]["card_reader_type"] = "SD Card Reader"
                    elif cv_clean not in ("Yes", "yes"):
                        specs["connectivity"]["card_reader_type"] = cv_clean
                    break

        if specs["connectivity"]["has_card_reader"] is None and specs["connectivity"]["ports"]:
            for p in specs["connectivity"]["ports"]:
                pl = p.lower()
                if "card reader" in pl or "microsd" in pl or "sd card" in pl:
                    specs["connectivity"]["has_card_reader"] = True
                    if "microsd" in pl:
                        specs["connectivity"]["card_reader_type"] = "MicroSD"
                    elif "sd" in pl:
                        specs["connectivity"]["card_reader_type"] = "SD Card Reader"
                    break

    def _extract_operating_system(
        self,
        title: str,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
    ) -> None:
        specs["operating_system"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"os"},
            fallback_text=context,
        )

        os_rows = routed_table.get("os", []) if routed_table else []
        table_os_text = " ".join(v for _, v in os_rows)
        if not table_os_text:
            for k, v in table.items():
                if k.lower() in ("os", "operating system"):
                    table_os_text += f" {v}"

        targets = [table_os_text, title, context] if table_os_text else [title, context]

        for tgt in targets:
            if not tgt or not tgt.strip():
                continue
            # Strip recommendation clause: "ASUS recommends Windows 11 Pro for business"
            clean_tgt = re.sub(
                r"(?:asus\s+recommends\s+|recommends?\s+)windows\s*11\s*pro(?:\s+for\s+business)?",
                "",
                tgt,
                flags=re.IGNORECASE,
            )
            if re.search(r"\bwindows\s*11\s*pro\b", clean_tgt, re.IGNORECASE):
                specs["operating_system"]["name"] = "Windows 11 Pro"
                break
            elif re.search(r"\b(?:windows\s*11\s*home|windows\s*11|win\s*11)\b", clean_tgt, re.IGNORECASE):
                specs["operating_system"]["name"] = "Windows 11 Home"
                break
            elif re.search(r"\bwindows\s*10\s*pro\b", clean_tgt, re.IGNORECASE):
                specs["operating_system"]["name"] = "Windows 10 Pro"
                break
            elif re.search(r"\b(?:windows\s*10\s*home|windows\s*10)\b", clean_tgt, re.IGNORECASE):
                specs["operating_system"]["name"] = "Windows 10 Home"
                break
            elif re.search(r"\bfreedos\b|\bfree\s*dos\b", clean_tgt, re.IGNORECASE):
                specs["operating_system"]["name"] = "FreeDOS"
                break
            elif re.search(
                r"\b(?:no\s*operating\s*system|no\s*preloaded|no\s*preinstalled|no\s*os|without\s*os|eshell)\b",
                clean_tgt,
                re.IGNORECASE,
            ):
                specs["operating_system"]["name"] = "No OS"
                break
            elif re.search(r"\bdos\b", clean_tgt, re.IGNORECASE):
                specs["operating_system"]["name"] = "FreeDOS"
                break
            elif re.search(r"\bmacos\b", clean_tgt, re.IGNORECASE):
                specs["operating_system"]["name"] = "macOS"
                break
            elif re.search(r"\bubuntu\b|\blinux\b", clean_tgt, re.IGNORECASE):
                specs["operating_system"]["name"] = "Linux"
                break

    def _extract_build_security(
        self,
        title: str,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["build_security"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"keyboard", "security", "pointing_device"},
            fallback_text=context,
        )

        kb_rows = routed_table.get("keyboard", [])
        sec_rows = routed_table.get("security", [])
        pad_rows = routed_table.get("pointing_device", [])

        if not kb_rows:
            kb_rows = [(k, v) for k, v in table.items() if any(w in k.lower() for w in ["keyboard", "input device"])]
        if not sec_rows:
            sec_rows = [(k, v) for k, v in table.items() if any(w in k.lower() for w in ["security", "fingerprint"])]
        if not pad_rows:
            pad_rows = [
                (k, v) for k, v in table.items() if any(w in k.lower() for w in ["touchpad", "pointing device"])
            ]

        # 1. Backlit keyboard & Backlight Type
        kb_text = " ".join(v for _, v in kb_rows) + " " + title

        is_non_backlit = False
        if re.search(r"\b(?:non-backlit|no\s*backlight|not\s*backlit|without\s*backlight)\b", kb_text, re.IGNORECASE):
            is_non_backlit = True
        for _, v in kb_rows:
            vl = v.strip().lower()
            if any(bad in vl for bad in ["non-backlit", "no backlight", "not backlit", "without backlight"]) or vl in (
                "no",
                "none",
                "false",
            ):
                is_non_backlit = True
                break
        for k, v in table.items():
            if "backlight" in k.lower():
                vl = v.strip().lower()
                if any(bad in vl for bad in ["no", "none", "false", "non-backlit"]):
                    is_non_backlit = True
                    break

        if is_non_backlit:
            specs["build_security"]["has_backlit_keyboard"] = False
            specs["build_security"]["keyboard_backlight_type"] = None
        elif re.search(r"\bper-?key\s*rgb\b", kb_text, re.IGNORECASE):
            specs["build_security"]["keyboard_backlight_type"] = "Per-Key RGB"
            specs["build_security"]["has_backlit_keyboard"] = True
        elif re.search(r"\b4-?zone\s*rgb\b", kb_text, re.IGNORECASE):
            specs["build_security"]["keyboard_backlight_type"] = "4-Zone RGB"
            specs["build_security"]["has_backlit_keyboard"] = True
        elif re.search(r"\b(?:1-?zone\s*rgb|single\s*zone\s*rgb)\b", kb_text, re.IGNORECASE):
            specs["build_security"]["keyboard_backlight_type"] = "1-Zone RGB"
            specs["build_security"]["has_backlit_keyboard"] = True
        elif re.search(r"\brgb\b", kb_text, re.IGNORECASE):
            specs["build_security"]["keyboard_backlight_type"] = "RGB Backlit"
            specs["build_security"]["has_backlit_keyboard"] = True
        elif re.search(r"\bamber\s+(?:backlit|backlight)\b|\bamber\b", kb_text, re.IGNORECASE) and any(
            "amber" in v.lower() for _, v in kb_rows
        ):
            specs["build_security"]["keyboard_backlight_type"] = "Amber Backlit"
            specs["build_security"]["has_backlit_keyboard"] = True
        elif re.search(r"\bwhite\s+(?:backlit|backlight)\b", kb_text, re.IGNORECASE):
            specs["build_security"]["keyboard_backlight_type"] = "White Backlit"
            specs["build_security"]["has_backlit_keyboard"] = True
        elif re.search(r"\bbacklit\b|\bbacklight\b", kb_text, re.IGNORECASE):
            specs["build_security"]["keyboard_backlight_type"] = "Backlit"
            specs["build_security"]["has_backlit_keyboard"] = True
        else:
            for k, v in table.items():
                if "backlight" in k.lower():
                    vl = v.strip().lower()
                    if any(yes in vl for yes in ["yes", "true", "supported", "available", "present"]):
                        specs["build_security"]["has_backlit_keyboard"] = True
                        specs["build_security"]["keyboard_backlight_type"] = "Backlit"
                        break

        # 2. Numpad
        numpad_rows = [
            v
            for k, v in table.items()
            if any(nk in k.lower() for nk in ["numeric keypad", "numpad", "num-key", "number pad"])
        ]
        if numpad_rows:
            np_val = " ".join(numpad_rows).lower()
            if any(bad in np_val for bad in ["no", "none", "without", "false"]):
                specs["build_security"]["has_numpad"] = False
            else:
                specs["build_security"]["has_numpad"] = True
        elif re.search(r"\b(?:without|no)\s+(?:numeric\s*keypad|num-?key|numpad)\b", kb_text, re.IGNORECASE):
            specs["build_security"]["has_numpad"] = False
        elif re.search(r"\b(num-?key|numeric\s*keypad|numpad|number\s*pad)\b", kb_text, re.IGNORECASE):
            specs["build_security"]["has_numpad"] = True

        # 3. Fingerprint reader
        for sk, vs in sec_rows:
            row_str = f"{sk}: {vs}"
            if re.search(
                r"\b(?:no\s+fingerprint|without\s+fingerprint)\b", row_str, re.IGNORECASE
            ) or vs.strip().lower() in ("no", "none", "n/a"):
                specs["build_security"]["has_fingerprint"] = False
                break
            elif re.search(r"\bfingerprint\b", row_str, re.IGNORECASE):
                if any(bad in vs.lower() for bad in ["no", "none", "n/a", "not supported", "not available"]):
                    specs["build_security"]["has_fingerprint"] = False
                else:
                    specs["build_security"]["has_fingerprint"] = True
                break

        # 4. Pointing device (Touchpad)
        for _, vs in pad_rows:
            clean_pad = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", " ", vs).strip()
            if not clean_pad or any(bad in clean_pad.lower() for bad in ["none", "n/a"]):
                continue
            # Reject stylus / pen negative disclaimers
            if re.search(
                r"\b(?:pen\s+not\s+supported|not\s+supported|no\s+support|not\s+included|without\s+pen|no\s+stylus)\b",
                clean_pad,
                re.IGNORECASE,
            ):
                continue
            if clean_pad.strip().lower() in ("pen", "stylus"):
                continue
            specs["build_security"]["pointing_device"] = clean_pad
            break

        # 5. Chassis material
        mat_rows = routed_table.get("materials", [])
        if not mat_rows:
            mat_rows = [
                (k, v)
                for k, v in table.items()
                if any(m in k.lower() for m in ["case material", "chassis material", "build material", "material"])
            ]
        for mk, mv in mat_rows:
            if "sustainable" in mk.lower():
                continue
            mv_clean = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", " ", mv).strip()
            if not mv_clean or any(bad in mv_clean.lower() for bad in ["none", "n/a"]):
                continue
            # Reject form-factor, security certs, and panel terms
            if any(
                bad in mv_clean.lower()
                for bad in [
                    "secured-core",
                    "security",
                    "tpm",
                    "password",
                    "fingerprint",
                    "clamshell",
                    "convertible",
                    "classical",
                    "gaming laptop",
                    "notebook",
                    "2-in-1",
                    "detachable",
                    "ips",
                ]
            ):
                continue
            specs["build_security"]["chassis_material"] = mv_clean
            break

        # 6. Security features
        sec_list = []
        for _, vs in sec_rows:
            clean_sec = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", " ", vs).strip()
            if clean_sec and not any(bad in clean_sec.lower() for bad in ["none", "n/a"]):
                sec_list.append(clean_sec)
        if sec_list:
            specs["build_security"]["security_features"] = sec_list

    def _extract_audio_webcam(
        self,
        table: dict[str, str],
        routed_table: dict[str, list[tuple[str, str]]] | None,
        context: str,
        specs: dict[str, Any],
        envelopes: list[ExtractionEnvelope],
    ) -> None:
        if routed_table is None:
            routed_table = self.router.route_table(table)

        specs["audio_webcam"]["raw_spec"] = self._collect_raw_spec(
            table=table,
            target_buckets={"camera", "audio", "camera_and_audio"},
            fallback_text=context,
        )

        cam_rows = routed_table.get("camera", [])
        audio_rows = routed_table.get("audio", [])

        if not cam_rows:
            cam_rows = [(k, v) for k, v in table.items() if any(w in k.lower() for w in ["camera", "webcam"])]
        if not audio_rows:
            audio_rows = [
                (k, v)
                for k, v in table.items()
                if any(w in k.lower() for w in ["speaker", "audio", "microphone", "mic"])
            ]

        # Webcam
        for _, vs in cam_rows:
            m_num = re.search(r"\b(\d{3,4}\s*p|\d+(?:\.\d+)?\s*(?:MP|M\b))\b", vs, re.IGNORECASE)
            if m_num:
                specs["audio_webcam"]["webcam_resolution"] = m_num.group(1).strip()
                break
            m_fhd = re.search(r"\b(Full\s*HD|FHD)\b", vs, re.IGNORECASE)
            if m_fhd:
                specs["audio_webcam"]["webcam_resolution"] = "1080p"
                break
            m_named = re.search(r"\b(QHD|UHD|4K|HD)\b", vs, re.IGNORECASE)
            if m_named:
                named_map = {"HD": "720p", "QHD": "1440p", "UHD": "2160p", "4K": "2160p"}
                specs["audio_webcam"]["webcam_resolution"] = named_map.get(
                    m_named.group(1).upper(), m_named.group(1).upper()
                )
                break

        # Webcam Shutter & IR Camera
        cam_text = " ".join(v for _, v in cam_rows) + " " + " ".join(v for _, v in audio_rows)
        if re.search(r"\b(?:without|no)\s+(?:privacy\s*shutter|e-?shutter)\b", cam_text, re.IGNORECASE):
            specs["audio_webcam"]["has_privacy_shutter"] = False
        elif re.search(
            r"\b(privacy\s*shutter|e-?shutter|camera\s*shutter|webcam\s*shutter)\b", cam_text, re.IGNORECASE
        ):
            specs["audio_webcam"]["has_privacy_shutter"] = True

        if re.search(r"\b(?:without|no)\s+(?:ir|infrared)\b", cam_text, re.IGNORECASE):
            specs["audio_webcam"]["has_ir_camera"] = False
        elif re.search(
            r"\b(ir\s*camera|ir\s*webcam|infrared|windows\s*hello\s*camera|ir\s*function)\b", cam_text, re.IGNORECASE
        ):
            specs["audio_webcam"]["has_ir_camera"] = True

        # Microphone & Speakers
        for k, vs in audio_rows:
            combined_entry = f"{k}: {vs}"
            if not specs["audio_webcam"]["microphone"]:
                if re.search(
                    r"\bbuilt-in\s*microphones?\s*[:=]?\s*2\b|\bdual\s*array\b", combined_entry, re.IGNORECASE
                ):
                    specs["audio_webcam"]["microphone"] = "Dual array microphone"
                elif re.search(r"\bmicrophone\s*[:=]?\s*(?:yes|1|built-in)\b", combined_entry, re.IGNORECASE):
                    specs["audio_webcam"]["microphone"] = "Built-in microphone"
                elif re.search(r"\b(?:mic|microphone|array)\b", vs, re.IGNORECASE):
                    if not any(bad in vs.lower() for bad in ["none", "n/a", "no "]):
                        clean_mic = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", " ", vs)
                        clean_mic = re.sub(r"\s+", " ", clean_mic).strip()
                        specs["audio_webcam"]["microphone"] = clean_mic

            if specs["audio_webcam"]["speaker_count"] is None:
                m_wt = re.findall(r"(\d+)\s*(?:woofers?|tweeters?)", vs, re.IGNORECASE)
                if len(m_wt) >= 2:
                    specs["audio_webcam"]["speaker_count"] = sum(int(c) for c in m_wt)
                else:
                    m_sp = re.search(
                        r"(\d+)[-\s]*(?:stereo\s*)?(?:x\s*\d+(?:\.\d+)?\s*W|speakers?|speaker\s*system)",
                        vs,
                        re.IGNORECASE,
                    )
                    if m_sp:
                        specs["audio_webcam"]["speaker_count"] = int(m_sp.group(1))
                    elif re.search(r"\b(?:quad|four|4x)\b", vs, re.IGNORECASE):
                        specs["audio_webcam"]["speaker_count"] = 4
                    elif re.search(r"\b(?:dual|stereo|two|2x)\b", vs, re.IGNORECASE):
                        specs["audio_webcam"]["speaker_count"] = 2
