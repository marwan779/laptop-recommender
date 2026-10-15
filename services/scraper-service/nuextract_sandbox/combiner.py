import re
from typing import Any

class SpecCombiner:
    """Layer 2: Combine raw table rows, title, and metadata into structured context blocks for NuExtract."""

    AREA_KEYWORDS: dict[str, list[str]] = {
        "identity": ["brand", "model", "part", "series", "family", "product name", "machine type", "base unit"],
        "cpu": ["cpu", "processor", "core", "thread", "clock", "cache", "chip"],
        "gpu": ["gpu", "graphic", "video card", "vram", "tgp", "tdp", "display adapter"],
        "memory": ["ram", "memory", "dimm", "sodimm", "channel", "ddr", "installed memory"],
        "storage": ["storage", "ssd", "nvme", "m.2", "hard disk", "drive", "emmc", "capacity", "slot"],
        "display": ["display", "screen", "resolution", "refresh", "panel", "aspect", "touch", "ips", "oled", "brightness", "hz"],
        "power_battery": ["battery", "power adapter", "ac adapter", "power supply", "wattage", "wh\b", "cell"],
        "connectivity": ["port", "usb", "hdmi", "ethernet", "lan", "rj-45", "wi-fi", "wifi", "bluetooth", "wlan", "thunderbolt"],
        "audio_webcam": ["audio", "speaker", "sound", "microphone", "mic", "webcam", "camera"],
        "operating_system": ["operating system", "os", "windows", "dos", "freedos", "linux", "ubuntu"],
        "physical": ["dimension", "weight", "color", "height", "width", "depth", "chassis", "material"],
        "build_security": ["keyboard", "backlit", "fingerprint", "security", "lock", "tpm", "touchpad"],
    }

    # Only include the title in areas that genuinely require title context
    AREAS_WITH_TITLE = {"identity", "cpu", "display"}

    def combine_unified_markdown(self, scraped_data: dict[str, Any]) -> str:
        """Combine all scraped data into a single, clean Markdown specification document."""
        title = scraped_data.get("title", "").strip()
        raw_specs = scraped_data.get("raw_specs", {})
        metadata = scraped_data.get("metadata", {})
        desc = scraped_data.get("raw_description", "").strip()

        lines = [f"# Product Title: {title}"]

        if metadata:
            meta_items = [f"{k}: {v}" for k, v in metadata.items() if v is not None]
            if meta_items:
                lines.append(f"## Store Metadata:\n" + "\n".join(f"- {item}" for item in meta_items))

        if raw_specs:
            lines.append("## Product Specifications:")
            for k, v in raw_specs.items():
                k_clean = re.sub(r"\s+", " ", str(k)).strip()
                v_clean = re.sub(r"\s+", " ", str(v)).strip()
                lines.append(f"- **{k_clean}**: {v_clean}")

        if desc and not raw_specs:
            lines.append("## Description Details:")
            for d_line in desc.splitlines()[:25]:
                if d_line.strip():
                    lines.append(d_line.strip())

        return "\n\n".join(lines)

    def combine_area_blocks(self, scraped_data: dict[str, Any]) -> dict[str, str]:
        """Combine raw rows into component-specific context text blocks.

        Rule: Only include product title in identity, cpu, and display to prevent
        spurious token bleed into missing fields (e.g. 16GB RAM becoming cell count).
        """
        title = scraped_data.get("title", "").strip()
        raw_specs = scraped_data.get("raw_specs", {})
        metadata = scraped_data.get("metadata", {})

        blocks: dict[str, list[str]] = {
            area: [f"Product Title: {title}"] if area in self.AREAS_WITH_TITLE else []
            for area in self.AREA_KEYWORDS
        }

        # Inject relevant metadata into identity only
        if metadata:
            if metadata.get("sku"):
                blocks["identity"].append(f"Store SKU / MPN: {metadata['sku']}")
            if metadata.get("brand"):
                blocks["identity"].append(f"Brand: {metadata['brand']}")

        # Group rows by keyword relevance with strict negative boundaries
        for k, v in raw_specs.items():
            k_low = str(k).lower()

            # Prevent battery life from bleeding into GPU
            if "battery" in k_low:
                blocks["power_battery"].append(f"{k}: {v}")
                continue

            for area, keywords in self.AREA_KEYWORDS.items():
                # Avoid confusing memory with storage
                if area == "memory" and any(bad in k_low for bad in ["storage", "ssd", "hard disk", "drive"]):
                    continue
                if area == "storage" and any(bad in k_low for bad in ["system memory", "ram", "dimm"]):
                    continue
                # Avoid confusing power adapter with wireless/network adapter or graphics power
                if area == "power_battery" and any(bad in k_low for bad in ["wireless", "network", "graphics power", "tgp"]):
                    continue
                if area == "cpu" and any(bad in k_low for bad in ["graphics", "gpu"]):
                    continue

                if any(kw in k_low for kw in keywords):
                    blocks[area].append(f"{k}: {v}")

        return {area: "\n".join(lines) for area, lines in blocks.items()}
