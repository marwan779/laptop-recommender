import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

class TableKeyRouter:
    """Routes raw HTML specification table labels to canonical hardware categories."""

    # Explicit high-priority overrides for ambiguous or misclassified labels
    EXPLICIT_OVERRIDES = {
        # Storage primary vs expansion/slots
        "storage expansion": "storage_slots",
        "storage capability": "storage_slots",
        "storage slot": "storage_slots",
        "storage slots": "storage_slots",
        "m.2 slots": "storage_slots",
        "expansion slot": "storage_slots",
        "expansion slots": "storage_slots",
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
        # Memory primary vs max / slots
        "memory capacity": "memory",
        "ram, memory capacity, gb": "memory",
        "ram, number of slots": "memory_slots",
        "ram info": "memory",
        "ram memory": "memory",
        "ram memory installed": "memory",
        "installed memory": "memory",
        "dimm memory": "memory",
        "max memory": "max_memory",
        "maximum memory": "max_memory",
        "maximum memory supported": "max_memory",
        "max total system memory": "max_memory",
        "ram, maximum capacity, gb": "max_memory",
        "memory card supported": "card_reader",
        # Dimensions vs package
        "package dimensions": "package_dimensions",
        "package size (w x d x h), mm": "package_dimensions",
        # Camera & Audio
        "camera & audio": "camera_and_audio",
        # Ports
        "connectivity": "connectivity_and_ports",
    }

    CANONICAL_FIELD_TO_BUCKET = {
        # Storage
        "Storage": "storage",
        "Storage Capacity": "storage",
        "Maximum Storage Support": "max_storage",
        "Storage Slots": "storage_slots",
        "Storage Interface": "storage_interface",
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
        # Camera & Audio
        "Camera / Webcam": "camera",
        "Camera & Audio": "camera_and_audio",
        "Audio": "audio",
        "Microphone": "audio",
        # Physical
        "Dimensions": "dimensions",
        "Weight": "weight",
        "Product Color": "color",
        "Build / Materials": "build",
        # Display
        "Display": "display",
        "Display Size": "display",
        "Display Resolution": "display",
        "Display Refresh Rate": "display",
        "Display Aspect Ratio": "display",
        "Touchscreen": "display",
        "Display Brightness": "display",
        "Display Color Gamut / Accuracy": "display",
        "Display Features": "display",
        "Display Technology / Features": "display",
        # GPU
        "Graphics (GPU)": "gpu",
        "GPU Memory": "gpu_vram",
        "GPU Power": "gpu",
        "GPU Vendor": "gpu",
        "Integrated Graphics": "gpu",
        # CPU
        "Processor": "cpu",
        "Processor Brand": "cpu",
        "Processor Cores / Threads": "cpu",
        "Processor Speed / Clock": "cpu",
        "Processor Cache": "cpu",
        # Power
        "Battery": "power",
        "Power / Power Supply": "power",
        "Power Adapter / Charging": "power",
        # OS
        "Operating System": "os",
        # Build & Security
        "Security": "security",
        "Keyboard": "keyboard",
        "Keyboard / Pointing Device": "keyboard",
        "Touchpad / Pointing Device": "pointing_device",
        # Brand / Model
        "Brand": "brand",
        "Model / Product Name": "model",
        "Product Identifier": "model",
    }

    def __init__(self, alias_dict_path: Optional[Path] = None) -> None:
        if alias_dict_path is None:
            alias_dict_path = Path(__file__).resolve().parent.parent / "pipeline" / "data" / "compumarts_alias_dict.json"
        
        self.label_to_bucket: Dict[str, str] = {}
        if alias_dict_path.exists():
            with open(alias_dict_path, encoding="utf-8") as f:
                data = json.load(f)
            observed = data.get("observed_labels", {})
            for raw_lbl, meta in observed.items():
                canon_field = meta.get("canonical_field", "")
                bucket = self.CANONICAL_FIELD_TO_BUCKET.get(canon_field)
                if bucket:
                    # Normalized key (stripped, lowercased)
                    norm_k = self._normalize_key(raw_lbl)
                    self.label_to_bucket[norm_k] = bucket

        # Apply explicit overrides (they take precedence)
        for k, b in self.EXPLICIT_OVERRIDES.items():
            self.label_to_bucket[self._normalize_key(k)] = b

    @staticmethod
    def _normalize_key(k: str) -> str:
        k = k.strip().lower()
        k = re.sub(r"[:\s\t\r\n]+", " ", k).strip()
        k = re.sub(r"[®™©]", "", k).strip()
        return k

    def route_key(self, raw_key: str) -> str:
        """Route a single table row key to a canonical bucket."""
        norm = self._normalize_key(raw_key)
        
        # 1. Exact match in precomputed dictionary
        if norm in self.label_to_bucket:
            return self.label_to_bucket[norm]
        
        # 2. Heuristic fallback for unseen keys
        if any(term in norm for term in ["max storage", "maximum storage", "storage support"]):
            return "max_storage"
        if any(term in norm for term in ["storage slot", "m.2 slot", "expansion slot"]):
            return "storage_slots"
        if any(term in norm for term in ["storage", "ssd", "hdd", "hard disk", "hard drive", "internal"]):
            return "storage"
        if any(term in norm for term in ["max memory", "maximum memory", "max ram"]):
            return "max_memory"
        if any(term in norm for term in ["memory slot", "ram slot"]):
            return "memory_slots"
        if any(term in norm for term in ["ram", "memory"]):
            return "memory"
        if any(term in norm for term in ["port", "external i/o", "hdmi", "thunderbolt", "usb", "interface"]):
            return "ports"
        if any(term in norm for term in ["camera", "webcam"]):
            return "camera"
        if "dimension" in norm and "package" not in norm:
            return "dimensions"
        if "weight" in norm and "package" not in norm:
            return "weight"
        if any(term in norm for term in ["display", "screen", "panel"]):
            return "display"
        if any(term in norm for term in ["graphic", "gpu", "vga", "video"]):
            return "gpu"
        if any(term in norm for term in ["cpu", "processor"]):
            return "cpu"
        if any(term in norm for term in ["battery", "power", "adapter"]):
            return "power"
        if any(term in norm for term in ["operating system", "os"]):
            return "os"
        
        return "unrouted"

    def route_table(self, table: Dict[str, str]) -> Dict[str, List[Tuple[str, str]]]:
        """Route all rows in a table to canonical buckets."""
        routed: Dict[str, List[Tuple[str, str]]] = {}
        for k, v in table.items():
            bucket = self.route_key(k)
            # Handle multi-bucket routing e.g. connectivity_and_ports
            if bucket == "connectivity_and_ports":
                routed.setdefault("connectivity", []).append((k, v))
                if any(w in v.lower() for w in ["port", "usb", "hdmi", "thunderbolt", "jack", "lan", "rj45", "rj-45"]):
                    routed.setdefault("ports", []).append((k, v))
            elif bucket == "camera_and_audio":
                routed.setdefault("camera", []).append((k, v))
                routed.setdefault("audio", []).append((k, v))
            else:
                routed.setdefault(bucket, []).append((k, v))
        return routed


if __name__ == "__main__":
    router = TableKeyRouter()
    catalog_path = Path("tests/fixtures/compumarts_138_raw_catalog.json")
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    products = catalog["products"]
    print(f"Loaded {len(products)} products from {catalog_path}")

    bucket_counts = {}
    loq_tested = False

    for p in products:
        table = {r["label"]: r["value"] for r in p.get("spec_rows", [])}
        routed = router.route_table(table)
        for b in routed:
            bucket_counts[b] = bucket_counts.get(b, 0) + 1

        # Check LOQ 15IAX9
        if "lenovo-loq-15iax9-83gs00ecin" in p["url"]:
            loq_tested = True
            print("\n--- LOQ 15IAX9 Routing Check ---")
            print("Storage bucket:", routed.get("storage"))
            print("Max Storage bucket:", routed.get("max_storage"))
            print("Storage Slots bucket:", routed.get("storage_slots"))

    print("\n--- Product Bucket Coverage (out of 138) ---")
    for b, c in sorted(bucket_counts.items(), key=lambda x: -x[1]):
        print(f"  {b:25}: {c}/138 ({c/138*100:.1f}%)")

