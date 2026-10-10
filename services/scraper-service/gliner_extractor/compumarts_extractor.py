"""Dedicated CompuMarts Laptop Specification Extractor.

Features:
  1. Store-specific extraction layer tailored strictly to CompuMarts Egypt catalog structures.
  2. Modular methods for every specification dimension (CPU, GPU, RAM, Storage, Display, etc.).
  3. Scoped, typed keyword dictionaries embedded directly in each method (derived from the 259 live table keys).
  4. "Knows Its Limits" boundary detection: deterministic regex extraction for confident patterns,
     packaging complex/ambiguous/prose rows into a ContextEnvelope for GLiNER fallback.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextEnvelope:
    """Rich context envelope for delegating complex or ambiguous rows to GLiNER."""

    target_area: str
    target_labels: list[str]
    raw_key: str
    raw_value: str
    product_title: str
    sibling_context: dict[str, Any] = field(default_factory=dict)
    reason: str = "complex_row"

    def format_gliner_text(self, max_words: int = 180) -> str:
        """Format the envelope into a brief, rich semantic prompt under 384 tokens."""
        ctx_parts = []
        if self.product_title:
            title_words = self.product_title.strip().split()
            short_title = " ".join(title_words[:16])
            ctx_parts.append(f"Product: {short_title}")
        if self.sibling_context:
            siblings_str = ", ".join(f"{k}: {v}" for k, v in self.sibling_context.items() if v)
            if siblings_str:
                sib_words = siblings_str.split()
                if len(sib_words) > 20:
                    siblings_str = " ".join(sib_words[:20])
                ctx_parts.append(f"Known: {siblings_str}")

        clean_val = re.sub(r"\s+", " ", str(self.raw_value or "")).strip()
        row_str = f"Spec: {self.raw_key}: {clean_val}" if self.raw_key else clean_val
        ctx_parts.append(row_str)

        full_text = "\n".join(ctx_parts)
        words = full_text.split()
        if len(words) > max_words:
            full_text = " ".join(words[:max_words])
        return full_text


class CompumartsExtractor:
    """Dedicated extractor layer for CompuMarts Egypt."""

    # -------------------------------------------------------------------------
    # 1. IDENTITY & BRAND KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    IDENTITY_KEYWORDS: dict[str, str] = {
        'base unit': 'manufacturer_part_number',
        'brand': 'brand',
        'brand & model': 'brand',
        'brand model': 'brand',
        'brand name': 'brand',
        'machine type': 'manufacturer_part_number',
        'marketing name': 'laptop_model',
        'model': 'laptop_model',
        'model name': 'laptop_model',
        'model number': 'manufacturer_part_number',
        'part no': 'manufacturer_part_number',
        'part no.': 'manufacturer_part_number',
        'part number': 'manufacturer_part_number',
        'product name': 'laptop_model',
        'product number': 'manufacturer_part_number',
        'sales model name': 'laptop_model',
        'series': 'laptop_family',
    }

    SUB_BRAND_MAP: dict[str, str] = {
        "rog strix": "ASUS",
        "rog zephyrus": "ASUS",
        "rog flow": "ASUS",
        "rog": "ASUS",
        "tuf gaming": "ASUS",
        "tuf": "ASUS",
        "zenbook": "ASUS",
        "vivobook": "ASUS",
        "proart": "ASUS",
        "alienware": "DELL",
        "xps": "DELL",
        "inspiron": "DELL",
        "vostro": "DELL",
        "latitude": "DELL",
        "legion": "Lenovo",
        "loq": "Lenovo",
        "ideapad": "Lenovo",
        "thinkpad": "Lenovo",
        "thinkbook": "Lenovo",
        "yoga": "Lenovo",
        "predator": "Acer",
        "nitro": "Acer",
        "aspire": "Acer",
        "swift": "Acer",
        "travelmate": "Acer",
        "victus": "HP",
        "omen": "HP",
        "pavilion": "HP",
        "envy": "HP",
        "spectre": "HP",
        "probook": "HP",
        "elitebook": "HP",
        "aorus": "Gigabyte",
        "aero": "Gigabyte",
        "cyborg": "MSI",
        "katana": "MSI",
        "sword": "MSI",
        "thin": "MSI",
        "vector": "MSI",
        "stealth": "MSI",
        "titan": "MSI",
        "raider": "MSI",
        "crosshair": "MSI",
        "modern": "MSI",
        "prestige": "MSI",
    }

    KNOWN_FAMILIES: list[str] = [
        # Lenovo
        "Legion Pro 7", "Legion Pro 5", "Legion Slim 5", "Legion 7", "Legion 5", "Legion 9", "Legion",
        "LOQ 15", "LOQ 16", "LOQ",
        "IdeaPad Slim 5", "IdeaPad Slim 3", "IdeaPad Slim", "IdeaPad Gaming 3", "IdeaPad Pro 5", "IdeaPad",
        "ThinkPad X1 Carbon", "ThinkPad X1", "ThinkPad E16", "ThinkPad E14", "ThinkPad T14", "ThinkPad L15", "ThinkPad",
        "ThinkBook 16", "ThinkBook 14", "ThinkBook",
        "Yoga Pro 9", "Yoga Slim 7", "Yoga 9", "Yoga 7", "Yoga",
        # ASUS
        "ROG Strix SCAR 18", "ROG Strix SCAR 16", "ROG Strix SCAR", "ROG Strix G18", "ROG Strix G16", "ROG Strix",
        "ROG Zephyrus G16", "ROG Zephyrus G14", "ROG Zephyrus Duo", "ROG Zephyrus",
        "ROG Flow X16", "ROG Flow X13", "ROG Flow Z13", "ROG Flow",
        "TUF Gaming A16", "TUF Gaming A15", "TUF Gaming F16", "TUF Gaming F15", "TUF Gaming", "TUF",
        "Zenbook Duo", "Zenbook Pro", "Zenbook S 16", "Zenbook S 14", "Zenbook S", "Zenbook 14", "Zenbook",
        "Vivobook Pro 16", "Vivobook Pro 15", "Vivobook Pro", "Vivobook S 16", "Vivobook S 15", "Vivobook S 14", "Vivobook S", "Vivobook Go", "Vivobook 16", "Vivobook 15", "Vivobook",
        "ProArt P16", "ProArt PX13", "ProArt",
        # Acer
        "Predator Helios 18", "Predator Helios 16", "Predator Helios Neo 16", "Predator Helios Neo", "Predator Helios", "Predator Triton", "Predator",
        "Nitro V 16", "Nitro V 15", "Nitro V", "Nitro 17", "Nitro 16", "Nitro 5", "Nitro",
        "Swift Go 14", "Swift Go 16", "Swift Go", "Swift X", "Swift",
        "Aspire 7", "Aspire 5", "Aspire 3", "Aspire",
        "TravelMate",
        # HP
        "Omen Transcend 16", "Omen Transcend 14", "Omen Transcend", "Omen 17", "Omen 16", "Omen",
        "Victus 16", "Victus 15", "Victus",
        "Pavilion Plus 16", "Pavilion Plus 14", "Pavilion Plus", "Pavilion Aero", "Pavilion",
        "Envy x360", "Envy 17", "Envy 16", "Envy",
        "Spectre x360", "Spectre",
        "EliteBook", "ProBook",
        # Dell
        "Alienware m18", "Alienware m16", "Alienware x16", "Alienware x14", "Alienware",
        "XPS 16", "XPS 14", "XPS 15", "XPS 13", "XPS",
        "Inspiron 16", "Inspiron 15", "Inspiron 14", "Inspiron",
        "Vostro", "Latitude", "Precision",
        # MSI
        "Titan 18", "Titan", "Raider GE78", "Raider GE68", "Raider", "Stealth 16", "Stealth 14", "Stealth",
        "Vector 17", "Vector 16", "Vector", "Crosshair 17", "Crosshair 16", "Crosshair",
        "Katana 17", "Katana 15", "Katana", "Sword 17", "Sword 16", "Sword",
        "Cyborg 15", "Cyborg 14", "Cyborg", "Thin 15", "Thin GF63", "Thin",
        "Prestige 16", "Prestige 14", "Prestige 13", "Prestige", "Modern 15", "Modern 14", "Modern",
        # Gigabyte
        "AORUS 17X", "AORUS 16X", "AORUS 17", "AORUS 16", "AORUS 15", "AORUS",
        "AERO 16", "AERO 14", "AERO",
    ]

# -------------------------------------------------------------------------
    # CPU KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    CPU_KEYWORDS: dict[str, str] = {
        'ai chip': 'npu',
        'ai engine': 'npu',
        'ai features': 'npu',
        'cache': 'cache',
        'chipset': 'chipset',
        'cores': 'cores',
        'cores / threads': 'cores_threads',
        'cores threads': 'cores_threads',
        'cpu': 'full_name',
        'cpu cache': 'cache',
        'cpu class': 'full_name',
        'cpu cores': 'cores',
        'cpu cores / threads': 'cores_threads',
        'cpu cores threads': 'cores_threads',
        'cpu model': 'model',
        'cpu series': 'full_name',
        'cpu speed': 'clock_speed',
        'cpu threads': 'threads',
        'cpu type': 'line',
        'generation description': 'series',
        'graphics processor': 'full_name',
        'laptop cpu family': 'line',
        'max turbo frequency': 'clock_speed',
        'maximum turbo frequency': 'clock_speed',
        'neural processor': 'npu',
        'npu': 'npu',
        'npu manufacturer': 'npu',
        'npu name': 'npu',
        'npu performance': 'npu',
        'processor': 'full_name',
        'processor (cpu)': 'full_name',
        'processor cache': 'cache',
        'processor clock speed ghz': 'clock_speed',
        'processor core': 'cores',
        'processor cores': 'cores',
        'processor cores / threads': 'cores_threads',
        'processor cores threads': 'cores_threads',
        'processor cpu': 'full_name',
        'processor count': 'cores',
        'processor details': 'full_name',
        'processor family': 'line',
        'processor generation': 'series',
        'processor manufacturer': 'manufacturer',
        'processor model': 'model',
        'processor number of cores': 'cores',
        'processor series': 'series',
        'processor speed': 'clock_speed',
        'processor tdp': 'full_name',
        'processor threads': 'threads',
        'processor type': 'line',
        'processor, clock speed, ghz': 'clock_speed',
        'processor, manufacturer': 'manufacturer',
        'processor, model': 'model',
        'processor, number of cores': 'cores',
        'processor, series': 'series',
        'release generation': 'series',
        'turbo frequency': 'clock_speed',
    }

    # -------------------------------------------------------------------------
    # GPU KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    GPU_KEYWORDS: dict[str, str] = {
        'combined cpu gpu power': 'tdp_w',
        'combined cpu-gpu power': 'tdp_w',
        'cpu & gpu power': 'tdp_w',
        'cpu gpu power': 'tdp_w',
        'discrete optimus': 'switch',
        'discrete share': 'switch',
        'discrete/optimus': 'switch',
        'discrete/share': 'switch',
        'gpu': 'model',
        'gpu boost clock': 'boost_clock',
        'gpu memory': 'vram_gb',
        'gpu memory type': 'vram_gb',
        'gpu performance': 'tdp_w',
        'gpu power': 'tdp_w',
        'gpu power / clock': 'tdp_w',
        'gpu power clock': 'tdp_w',
        'gpu tgp': 'tdp_w',
        'graphic': 'model',
        'graphic memory': 'vram_gb',
        'graphic wattage': 'tdp_w',
        'graphics': 'model',
        'graphics (dedicated)': 'model',
        'graphics (discrete)': 'model',
        'graphics (gpu)': 'model',
        'graphics (integrated)': 'model',
        'graphics card': 'model',
        'graphics card ram size': 'vram_gb',
        'graphics card tgp': 'tdp_w',
        'graphics clock': 'model',
        'graphics controller manufacturer': 'manufacturer',
        'graphics controller model': 'model',
        'graphics dedicated': 'model',
        'graphics description': 'model',
        'graphics discrete': 'model',
        'graphics features': 'model',
        'graphics gpu': 'model',
        'graphics integrated': 'model',
        'graphics manufacturer': 'model',
        'graphics memory': 'vram_gb',
        'graphics memory accessibility': 'vram_gb',
        'graphics memory capacity': 'vram_gb',
        'graphics memory technology': 'vram_gb',
        'graphics model': 'model',
        'graphics power': 'tdp_w',
        'graphics power (tgp)': 'tdp_w',
        'graphics power tgp': 'tdp_w',
        'graphics switch': 'switch',
        'graphics tech': 'model',
        'graphics tgp': 'tdp_w',
        'integrated gpu': 'model',
        'integrated graphics': 'model',
        'intergrated gpu': 'model',
        'laptop gpu': 'model',
        'max graphics power': 'tdp_w',
        'max power': 'tdp_w',
        'maximum graphics power': 'tdp_w',
        'maximum graphics power (tgp)': 'tdp_w',
        'maximum graphics power tgp': 'tdp_w',
        'maximum power': 'tdp_w',
        'mux switch': 'switch',
        'video card integrated video card model': 'model',
        'video card manufacturer': 'model',
        'video card type': 'model',
        'video card, integrated video card model': 'model',
        'video card, manufacturer': 'model',
        'video card, type': 'model',
        'video graphics': 'model',
        'video memory': 'vram_gb',
    }

    # -------------------------------------------------------------------------
    # RAM KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    RAM_KEYWORDS: dict[str, str] = {
        '32gb lpddr5x on board (max total system memory up to': 'capacity_gb',
        '32gb lpddr5x on board max total system memory up to': 'capacity_gb',
        'computer memory type': 'memory_type',
        'dimm memory': 'capacity_gb',
        'installed memory': 'capacity_gb',
        'max memory': 'max_supported_gb',
        'max total system memory': 'capacity_gb',
        'maximum memory': 'max_supported_gb',
        'maximum memory supported': 'max_supported_gb',
        'maximum supported system memory': 'max_supported_gb',
        'memory': 'capacity_gb',
        'memory (ram)': 'capacity_gb',
        'memory capability': 'slot_count',
        'memory max': 'max_supported_gb',
        'memory max.': 'max_supported_gb',
        'memory ram': 'capacity_gb',
        'memory slot': 'slot_count',
        'memory slot and max capacity': 'slot_count',
        'memory slots': 'slot_count',
        'memory speed': 'speed',
        'memory technology': 'memory_type',
        'memory type': 'memory_type',
        'memory upgrade': 'slot_count',
        'multi channel memory technology': 'memory_type',
        'multi-channel memory technology': 'memory_type',
        'installed ram': 'capacity_gb',
        'on board memory': 'capacity_gb',
        'ram': 'capacity_gb',
        'ram memory': 'capacity_gb',
        'ram memory capacity gb': 'capacity_gb',
        'ram memory installed': 'capacity_gb',
        'ram memory type': 'memory_type',
        'ram size': 'capacity_gb',
        'ram slots': 'slot_count',
        'ram, memory capacity, gb': 'capacity_gb',
        'ram, memory type': 'memory_type',
        'standard memory': 'capacity_gb',
        'system memory': 'capacity_gb',
        'system memory speed': 'speed',
        'system memory speed (mt/s)': 'speed',
        'system memory speed mt s': 'speed',
        'system memory technology': 'memory_type',
        'total system memory': 'capacity_gb',
    }

    # -------------------------------------------------------------------------
    # STORAGE KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    STORAGE_KEYWORDS: dict[str, str] = {
        'expansion slot': 'slot_count',
        'expansion slot (includes used)': 'slot_count',
        'expansion slot includes used': 'slot_count',
        'expansion slot(includes used)': 'slot_count',
        'expansion slots': 'slot_count',
        'hard disk capacity': 'capacity_gb',
        'hard disk size': 'capacity_gb',
        'internal': 'capacity_gb',
        'internal storage': 'capacity_gb',
        'solid state drive interface': 'interface',
        'ssd form factor': 'form_factor',
        'storage': 'capacity_gb',
        'storage capability': 'slot_count',
        'storage capacity': 'capacity_gb',
        'storage expansion': 'slot_count',
        'storage interface': 'interface',
        'storage slot': 'slot_count',
        'storage slots': 'slot_count',
        'total solid state drive capacity': 'capacity_gb',
    }

    # -------------------------------------------------------------------------
    # DISPLAY KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    DISPLAY_KEYWORDS: dict[str, str] = {
        'adaptive sync technology': 'features',
        'adaptive-sync technology': 'features',
        'aspect ratio': 'aspect_ratio',
        'brightness': 'features',
        'brightness & color': 'features',
        'brightness color': 'features',
        'color gamut': 'features',
        'contrast ratio': 'features',
        'display': 'size_inches',
        'display features': 'features',
        'display resolution': 'resolution',
        'display screen technology': 'panel_type',
        'display screen type': 'panel_type',
        'display size': 'size_inches',
        'display technology': 'panel_type',
        'display type': 'panel_type',
        'flicker free': 'features',
        'flicker-free': 'features',
        'ips level anti glare ag 1000': 'features',
        'ips-level, anti-glare(ag), 1000': 'features',
        'laptop screen size': 'size_inches',
        'led backlit unit': 'features',
        'nebula display': 'panel_type',
        'panel': 'panel_type',
        'panel size': 'size_inches',
        'panel tech': 'panel_type',
        'panel type': 'panel_type',
        'pantone': 'panel_type',
        'peak brightness': 'features',
        'refresh rate': 'refresh_rate_hz',
        'resolution': 'resolution',
        'response time': 'features',
        'response time (g2g)': 'features',
        'response time g2g': 'features',
        'screen brightness cd m2': 'features',
        'screen diagonal inches': 'size_inches',
        'screen info': 'panel_type',
        'screen refresh rate': 'refresh_rate_hz',
        'screen resolution': 'resolution',
        'screen size': 'size_inches',
        'screen touch screen': 'touchscreen',
        'screen type': 'panel_type',
        'screen, brightness, cd/m2': 'features',
        'screen, diagonal, inches': 'size_inches',
        'screen, refresh rate': 'refresh_rate_hz',
        'screen, resolution': 'resolution',
        'screen, touch screen': 'touchscreen',
        'sgs eye care display': 'features',
        'standard refresh rate': 'refresh_rate_hz',
        'surface texture of display': 'features',
        'tearing prevention technology': 'features',
        'touch panel': 'touchscreen',
        'touch screen': 'touchscreen',
        'touchscreen': 'touchscreen',
        'viewing angle': 'features',
    }

    # -------------------------------------------------------------------------
    # POWER_BATTERY KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    POWER_BATTERY_KEYWORDS: dict[str, str] = {
        '240w ac adapter (output': 'power_adapter_w',
        '240w ac adapter output': 'power_adapter_w',
        '250w ac adapter (output': 'power_adapter_w',
        '250w ac adapter output': 'power_adapter_w',
        '4 5 45w ac adapter output': 'power_adapter_w',
        'adapter': 'power_adapter_w',
        'battery': 'battery_capacity_wh',
        'battery & charger': 'power_adapter_w',
        'battery & power': 'battery_capacity_wh',
        'battery &amp; charger': 'power_adapter_w',
        'battery &amp; power': 'battery_capacity_wh',
        'battery amp charger': 'power_adapter_w',
        'battery amp power': 'battery_capacity_wh',
        'battery and power': 'battery_capacity_wh',
        'battery capacity': 'battery_capacity_wh',
        'battery capacity w h': 'battery_capacity_wh',
        'battery capacity, w/h': 'battery_capacity_wh',
        'battery charger': 'power_adapter_w',
        'battery chemistry': 'battery_capacity_wh',
        'battery energy': 'battery_capacity_wh',
        'battery life': 'battery_life_hours',
        'battery life detail': 'battery_life_hours',
        'battery power': 'battery_capacity_wh',
        'battery recharge time': 'battery_life_hours',
        'battery runtime': 'battery_capacity_wh',
        'battery type': 'battery_capacity_wh',
        'charger included': 'power_adapter_w',
        'fast charging': 'battery_life_hours',
        'maximum battery run time': 'battery_life_hours',
        'maximum power supply wattage': 'power_adapter_w',
        'number of cells': 'battery_cells',
        'power': 'power_adapter_w',
        'power adapter': 'power_adapter_w',
        'power connector': 'power_adapter_w',
        'power supply': 'power_adapter_w',
        'power supply type': 'power_adapter_w',
        'replaceable battery': 'battery_capacity_wh',
        'required charging power': 'power_adapter_w',
        'type c 100w ac adapter output 20v dc 5a 100w input': 'power_adapter_w',
        'type-c, 100w ac adapter, output 20v dc, 5a, 100w, input': 'power_adapter_w',
        'video playback battery life': 'battery_life_hours',
        'web browsing battery life': 'battery_life_hours',
        'weight (with battery)': 'battery_capacity_wh',
        'weight (without battery)': 'battery_capacity_wh',
        'weight with battery': 'battery_capacity_wh',
        'weight without battery': 'battery_capacity_wh',
        'ø4.5, 45w ac adapter, output': 'power_adapter_w',
    }

    # -------------------------------------------------------------------------
    # CONNECTIVITY KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    CONNECTIVITY_KEYWORDS: dict[str, str] = {
        'additional ports': 'ports',
        'audio jack': 'ports',
        'audio port': 'ports',
        'bluetooth': 'bluetooth',
        'bluetooth standard': 'bluetooth',
        'card reader': 'ports',
        'communications': 'combo',
        'connectivity': 'combo',
        'display output': 'ports',
        'docking': 'ports',
        'ethernet': 'ethernet',
        'ethernet port': 'ethernet',
        'ethernet technology': 'ethernet',
        'hdmi': 'ports',
        'hdmi 1 usb 3 2 gen 1 type a 1 usb 3 2 gen 2 type a 2 usb 3 2 gen 2 type c 2 rj 45 total usb ports': 'ethernet',
        'hdmi port': 'ports',
        'hdmi ×1, usb 3.2 gen 1 type-a ×1, usb 3.2 gen 2 type-a ×2, usb 3.2 gen 2 type-c ×2, rj-45, total usb ports': 'ethernet',
        'i o port': 'ports',
        'i o ports': 'ports',
        'i o ports left': 'ports',
        'i o ports rear': 'ports',
        'i o ports right': 'ports',
        'i/o port': 'ports',
        'i/o ports': 'ports',
        'i/o ports (left)': 'ports',
        'i/o ports (rear)': 'ports',
        'i/o ports (right)': 'ports',
        'interfaces docking station connector': 'ports',
        'interfaces ethernet network interface': 'ethernet',
        'interfaces ethernet network interface type': 'ethernet',
        'interfaces hdmi': 'ports',
        'interfaces sd card slot': 'ports',
        'interfaces serial port com': 'ports',
        'interfaces thunderbolt': 'ports',
        'interfaces usb 2 0': 'ports',
        'interfaces usb 3 0': 'ports',
        'interfaces usb type c': 'ports',
        'interfaces, docking station connector': 'ports',
        'interfaces, ethernet network interface': 'ethernet',
        'interfaces, ethernet network interface type': 'ethernet',
        'interfaces, hdmi': 'ports',
        'interfaces, sd card slot': 'ports',
        'interfaces, serial port (com)': 'ports',
        'interfaces, thunderbolt': 'ports',
        'interfaces, usb 2.0': 'ports',
        'interfaces, usb 3.0': 'ports',
        'interfaces, usb type-c™': 'ports',
        'lan': 'ethernet',
        'laptop ports': 'ports',
        'left ports': 'ports',
        'memory card reader': 'ports',
        'network': 'ethernet',
        'network (rj-45)': 'ethernet',
        'network - wireless': 'wifi',
        'network and communication': 'ethernet',
        'network interface': 'ethernet',
        'network rj 45': 'ethernet',
        'network wireless': 'wifi',
        'network/wireless': 'wifi',
        'networking': 'ethernet',
        'number of hdmi outputs': 'ports',
        'number of usb 3 2 gen 1 type a ports': 'ports',
        'number of usb 3 2 gen 2 type a ports': 'ports',
        'number of usb 3 2 gen 2 type c ports': 'ports',
        'number of usb 3 2 gen 2x2 type c ports': 'ports',
        'number of usb 3.2 gen 1 type-a ports': 'ports',
        'number of usb 3.2 gen 2 type-a ports': 'ports',
        'number of usb 3.2 gen 2 type-c ports': 'ports',
        'number of usb 3.2 gen 2x2 type-c ports': 'ports',
        'number of usb4 ports': 'ports',
        'on board wireless': 'wifi',
        'other ports': 'ports',
        'ports': 'ports',
        'right ports': 'ports',
        'rj 45 ethernet port': 'ethernet',
        'rj-45 ethernet port': 'ethernet',
        'rj45': 'ethernet',
        'standard ports': 'ports',
        'thunderbolt': 'ports',
        'thunderbolt / usb-c': 'ports',
        'thunderbolt port': 'ports',
        'thunderbolt usb c': 'ports',
        'total number of usb ports': 'ports',
        'total usb ports': 'ports',
        'usb': 'ports',
        'usb & display ports': 'ports',
        'usb 3 2 gen 1 type a': 'ports',
        'usb 3 2 gen 2 type c': 'ports',
        'usb 3.2 gen 1 type-a': 'ports',
        'usb 3.2 gen 2 type-c': 'ports',
        'usb a': 'ports',
        'usb a always on': 'ports',
        'usb a ports': 'ports',
        'usb c': 'ports',
        'usb c features': 'ports',
        'usb c ports': 'ports',
        'usb c power delivery': 'ports',
        'usb display ports': 'ports',
        'usb ports': 'ports',
        'usb type c': 'ports',
        'usb type-c': 'ports',
        'usb type-c®': 'ports',
        'usb-a': 'ports',
        'usb-a always-on': 'ports',
        'usb-a ports': 'ports',
        'usb-c': 'ports',
        'usb-c features': 'ports',
        'usb-c ports': 'ports',
        'usb-c power delivery': 'ports',
        'video output': 'ports',
        'video port': 'ports',
        'wi fi': 'wifi',
        'wi-fi': 'wifi',
        'wired network': 'ethernet',
        'wireless': 'wifi',
        'wireless & lan': 'wifi',
        'wireless &amp; lan': 'wifi',
        'wireless adapter': 'wifi',
        'wireless amp lan': 'wifi',
        'wireless communication': 'wifi',
        'wireless connection': 'wifi',
        'wireless connectivity': 'wifi',
        'wireless lan': 'wifi',
        'wireless lan model': 'wifi',
        'wireless lan standard': 'wifi',
        'wlan': 'wifi',
        'wlan + bluetooth': 'combo',
        'wlan bluetooth': 'combo',
    }

    # -------------------------------------------------------------------------
    # PHYSICAL KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    PHYSICAL_KEYWORDS: dict[str, str] = {
        'approximate weight': 'weight_kg',
        'body color': 'color',
        'bottom case color': 'color',
        'bottom case material': 'material',
        'bottom case-color': 'color',
        'bottom case-material': 'material',
        'build material': 'material',
        'case color': 'color',
        'case material': 'material',
        'chassis color': 'color',
        'chassis material': 'material',
        'color': 'color',
        'color & build': 'color',
        'color & chassis': 'color',
        'color & hdr': 'color',
        'color & material': 'color',
        'color &amp; build': 'color',
        'color &amp; material': 'color',
        'color / material': 'color',
        'color accuracy': 'color',
        'color amp build': 'color',
        'color amp material': 'color',
        'color build': 'color',
        'color chassis': 'color',
        'color depth': 'color',
        'color hdr': 'color',
        'color material': 'color',
        'color of the product': 'color',
        'color options': 'color',
        'color range': 'color',
        'colour gamut': 'color',
        'depth': 'dimensions',
        'design & material': 'material',
        'design material': 'material',
        'device weight kg': 'weight_kg',
        'device weight, kg': 'weight_kg',
        'dimension (w x d x h)': 'dimensions',
        'dimension w x d x h': 'dimensions',
        'dimensions': 'dimensions',
        'depth': 'depth_mm',
        'depth (front)': 'depth_mm',
        'depth (rear)': 'depth_mm',
        'depth front': 'depth_mm',
        'depth rear': 'depth_mm',
        'depth mm': 'depth_mm',
        'dimensions & weight': 'weight_kg',
        'dimensions &amp; weight': 'weight_kg',
        'dimensions (w x d x h)': 'dimensions',
        'dimensions (w x h x d)': 'dimensions',
        'dimensions (wxdxh)': 'dimensions',
        'dimensions amp weight': 'weight_kg',
        'dimensions and weight': 'weight_kg',
        'dimensions w x d x h': 'dimensions',
        'dimensions w x h x d': 'dimensions',
        'dimensions weight': 'weight_kg',
        'dimensions wxdxh': 'dimensions',
        'height': 'height_mm',
        'height (front)': 'height_mm',
        'height (rear)': 'height_mm',
        'height front': 'height_mm',
        'height rear': 'height_mm',
        'height mm': 'height_mm',
        'keyboard color': 'color',
        'lcd cover color': 'color',
        'lcd cover material': 'material',
        'lcd cover-color': 'color',
        'lcd cover-material': 'material',
        'material': 'material',
        'material type': 'material',
        'minimum dimensions (w x d x h)': 'dimensions',
        'minimum dimensions w x d x h': 'dimensions',
        'physical': 'physical_characteristics',
        'physical characteristics': 'physical_characteristics',
        'product color': 'color',
        'surface treatment': 'material',
        'top case color': 'color',
        'top case material': 'material',
        'top case-color': 'color',
        'top case-material': 'material',
        'weight': 'weight_kg',
        'weight (approximate)': 'weight_kg',
        'weight approximate': 'weight_kg',
        'weight in packaging kg': 'weight_kg',
        'weight in packaging, kg': 'weight_kg',
        'width': 'width_mm',
        'width (front)': 'width_mm',
        'width (rear)': 'width_mm',
        'width front': 'width_mm',
        'width rear': 'width_mm',
        'width mm': 'width_mm',
    }

    # -------------------------------------------------------------------------
    # OS KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    OS_KEYWORDS: dict[str, str] = {
        'operating system': 'name',
        'os': 'name',
        'os details': 'name',
        'os version': 'name',
    }

    # -------------------------------------------------------------------------
    # BUILD_SECURITY KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    BUILD_SECURITY_KEYWORDS: dict[str, str] = {
        'additional keyboard features': 'has_backlit_keyboard',
        'build & durability': 'security_features',
        'build durability': 'security_features',
        'durability': 'security_features',
        'finger print reader': 'has_fingerprint',
        'fingerprint': 'has_fingerprint',
        'fingerprint reader': 'has_fingerprint',
        'fingerprint scanner': 'has_fingerprint',
        'input devices': 'pointing_device',
        'keyboard': 'has_backlit_keyboard',
        'keyboard & touch': 'has_backlit_keyboard',
        'keyboard & touchpad': 'has_backlit_keyboard',
        'keyboard &amp; touch': 'has_backlit_keyboard',
        'keyboard amp touch': 'has_backlit_keyboard',
        'keyboard backlight': 'has_backlit_keyboard',
        'keyboard feature': 'has_backlit_keyboard',
        'keyboard features': 'has_backlit_keyboard',
        'keyboard keycaps': 'has_backlit_keyboard',
        'keyboard language': 'has_backlit_keyboard',
        'keyboard touch': 'has_backlit_keyboard',
        'keyboard touchpad': 'has_backlit_keyboard',
        'keyboard type': 'has_backlit_keyboard',
        'lighting keyboard': 'has_backlit_keyboard',
        'mil spec test': 'security_features',
        'mil-spec test': 'security_features',
        'military grade': 'security_features',
        'numeric keypad': 'has_backlit_keyboard',
        'other security': 'security_features',
        'pointing device': 'pointing_device',
        'pointing device type': 'pointing_device',
        'security': 'security_features',
        'security chip': 'security_features',
        'security feature': 'security_features',
        'security features': 'security_features',
        'security management': 'security_features',
        'special feature': 'special_features',
        'special features': 'special_features',
        'touchpad': 'pointing_device',
        'touchpad features': 'pointing_device',
    }

    # -------------------------------------------------------------------------
    # AUDIO_WEBCAM KEYWORD REGISTRY
    # -------------------------------------------------------------------------
    AUDIO_WEBCAM_KEYWORDS: dict[str, str] = {
        'audio': 'speakers',
        'audio & camera': 'webcam',
        'audio & input': 'speakers',
        'audio & speakers': 'speakers',
        'audio &amp; camera': 'webcam',
        'audio &amp; speakers': 'speakers',
        'audio amp camera': 'webcam',
        'audio amp speakers': 'speakers',
        'audio camera': 'webcam',
        'audio chip': 'speakers',
        'audio codec': 'speakers',
        'audio features': 'speakers',
        'audio input': 'speakers',
        'audio speakers': 'speakers',
        'audio tech': 'speakers',
        'audio technology': 'speakers',
        'built in devices': 'built_in_devices',
        'built-in devices': 'built_in_devices',
        'camera': 'webcam',
        'camera & audio': 'webcam',
        'camera &amp; audio': 'webcam',
        'camera amp audio': 'webcam',
        'camera audio': 'webcam',
        'dual speakers dts': 'speakers',
        'dual speakers with dts': 'speakers',
        'dual speakers, dts': 'speakers',
        'front camera': 'webcam',
        'front facing camera': 'webcam',
        'front-facing camera': 'webcam',
        'gaming audio': 'speakers',
        'mic': 'microphone',
        'microphone': 'microphone',
        'number of speakers': 'speakers',
        'photo camera': 'webcam',
        'speaker': 'speakers',
        'speakers': 'speakers',
        'speakers type': 'speakers',
        'webcam': 'webcam',
    }

    IGNORED_METADATA_KEYWORDS: set[str] = {
        '83f0007hed (region',
        '83f0007hed region',
        'accessories',
        'additional storage support',
        'ai pc category',
        'announce date',
        'antivirus',
        'aura sync',
        'base warranty',
        'built in apps',
        'built-in apps',
        'bundled accessories',
        'bundled software',
        'category',
        'cloud service',
        'color calibration',
        'cooling system',
        'country region',
        'country/region',
        'device category',
        'ean / upc',
        'ean / upc / jan',
        'ean code',
        'ean upc',
        'ean upc jan',
        'ecolabels & compliances',
        'ecolabels compliances',
        'end of support',
        'epeat silver energy star 8 0 rohs reparability index',
        'epeat silver, energy star 8.0, rohs, reparability index',
        'free shipping',
        'gift accessories',
        'included accessories',
        'included in the box',
        'included upgrade',
        'm 2 slots support either sata or nvme',
        'm 2 ssd support list',
        'm.2 slots support either sata or nvme',
        'm.2 ssd support list',
        'manufacturer warranty',
        'max storage support',
        'microsoft office',
        'office',
        'optical',
        'optical drive',
        'os & warranty',
        'os &amp; warranty',
        'os amp warranty',
        'os warranty',
        'package contents',
        'package size (w x d x h), mm',
        'package size w x d x h mm',
        'pen',
        'pen support',
        'product type',
        'region',
        'reparability index',
        'reparability index (bnl)',
        'reparability index (for france)',
        'reparability index (france)',
        'reparability index bnl',
        'reparability index for france',
        'reparability index france',
        'screen to body ratio',
        'screen to body ratio without speakers',
        'screen-to-body ratio',
        'screen-to-body ratio (without speakers)',
        'storage support',
        'stylus support',
        'support dolby vision hdr',
        'thermal feature',
        'topseller',
        'upc code',
        'warranty',
        'warranty & bundle',
        'warranty bundle',
        'warranty note',
        'warranty period',
        'warranty upgrade',
        'weee',
        'wwan',
        'xbox game pass',
    }

    @staticmethod
    def _normalize_key(key: str) -> str:
        """Strip and normalize key for dictionary lookup."""
        k = key.strip().lower()
        return re.sub(r"[^a-z0-9]+", " ", k).strip()

    # -------------------------------------------------------------------------
    # EXTRACTION METHODS
    # -------------------------------------------------------------------------

    def extract_identity(
        self,
        raw_specs: dict[str, Any],
        title: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract brand, family, model, and part numbers."""
        envelopes: list[ContextEnvelope] = []
        ident: dict[str, Any] = {
            "brand": None,
            "laptop_family": None,
            "laptop_model": None,
            "manufacturer_part_number": None,
        }

        # Check metadata first
        if metadata:
            if metadata.get("brand"):
                ident["brand"] = metadata["brand"]
            if metadata.get("mpn"):
                ident["manufacturer_part_number"] = metadata["mpn"]
            elif metadata.get("retailer_sku"):
                ident["manufacturer_part_number"] = metadata["retailer_sku"]

        # Check raw specs table
        for raw_k, raw_v in raw_specs.items():
            k_norm = self._normalize_key(raw_k)
            role = self.IDENTITY_KEYWORDS.get(k_norm) or self.IDENTITY_KEYWORDS.get(raw_k.strip().lower())
            if not role or not raw_v:
                continue
            v_str = str(raw_v).strip()
            if role == "brand" and not ident["brand"]:
                ident["brand"] = v_str
            elif role == "laptop_model" and not ident["laptop_model"]:
                ident["laptop_model"] = v_str
            elif role == "laptop_family" and not ident["laptop_family"]:
                ident["laptop_family"] = v_str
            elif role == "manufacturer_part_number" and not ident["manufacturer_part_number"]:
                ident["manufacturer_part_number"] = v_str

        # Title Family & Brand Normalization
        if not ident["laptop_family"]:
            for fam in self.KNOWN_FAMILIES:
                if re.search(rf"\b{re.escape(fam)}\b", title, re.IGNORECASE):
                    ident["laptop_family"] = fam
                    break

        if not ident["brand"]:
            t_low = title.lower()
            # 1. Direct brands
            for b in ["acer", "asus", "lenovo", "hp", "dell", "msi", "apple", "samsung", "huawei", "gigabyte", "razer", "microsoft"]:
                if re.search(rf"\b{b}\b", t_low):
                    ident["brand"] = b.upper() if b in ("hp", "msi", "dell", "asus") else b.capitalize()
                    break
            # 2. Sub-brands
            if not ident["brand"]:
                for sub, parent in self.SUB_BRAND_MAP.items():
                    if re.search(rf"\b{re.escape(sub)}\b", t_low):
                        ident["brand"] = parent
                        if not ident["laptop_family"]:
                            ident["laptop_family"] = sub.title()
                        break

        # If brand still not found but laptop_family found, infer brand from sub-brand map
        if not ident["brand"] and ident["laptop_family"]:
            fam_low = ident["laptop_family"].lower()
            for sub, parent in self.SUB_BRAND_MAP.items():
                if sub in fam_low:
                    ident["brand"] = parent
                    break

        # Fallback part number from title if model code present (e.g. 83LY00R8ED, G835LW-AI642W)
        if not ident["manufacturer_part_number"]:
            m_mpn = re.search(r"\b([0-9]{2}[A-Z0-9]{8}|[A-Z0-9]{5,8}-[A-Z0-9]{5,8})\b", title)
            if m_mpn:
                ident["manufacturer_part_number"] = m_mpn.group(1)

        missing_ident = []
        if not ident["brand"]:
            missing_ident.append("laptop brand")
        if not ident["laptop_family"]:
            missing_ident.append("laptop series")
        if not ident["laptop_model"]:
            missing_ident.append("laptop model")
        if not ident["manufacturer_part_number"]:
            missing_ident.append("part number")

        ident_rows = [(k, str(v)) for k, v in raw_specs.items() if self.IDENTITY_KEYWORDS.get(k.strip().lower()) or self.IDENTITY_KEYWORDS.get(self._normalize_key(k))]
        if missing_ident and (ident_rows or title):
            envelopes.append(ContextEnvelope(
                target_area="identity",
                target_labels=missing_ident,
                raw_key=ident_rows[0][0] if ident_rows else "Product",
                raw_value=" | ".join(f"{k}: {v}" for k, v in ident_rows[:3]) if ident_rows else title,
                product_title=title,
                sibling_context={},
                reason=f"unresolved_identity_fields:{','.join(missing_ident)}",
            ))

        return ident, envelopes

    def extract_cpu(
        self,
        raw_specs: dict[str, Any],
        title: str,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract CPU hardware specifications with limit boundary detection."""
        envelopes: list[ContextEnvelope] = []
        cpu: dict[str, Any] = {
            "manufacturer": None,
            "line": None,
            "model": None,
            "series": None,
            "full_name": None,
            "cores": None,
            "threads": None,
            "clock_speed": None,
        }

        cpu_raw_rows: list[tuple[str, str, str]] = []  # (raw_k, raw_v, role)

        for raw_k, raw_v in raw_specs.items():
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            # EXPLICIT GUARD: Never allow motherboard chipset or graphics chipset to enter CPU!
            if "chipset" in k_clean:
                continue

            role = self.CPU_KEYWORDS.get(k_clean) or self.CPU_KEYWORDS.get(k_norm)
            if role and raw_v:
                cpu_raw_rows.append((raw_k, str(raw_v).strip(), role))

        # Sort priority: 'full_name' first
        for raw_k, v_str, role in cpu_raw_rows:
            # If a row was tagged as 'cores' (e.g. 'Processor Core: Intel Core Ultra 5...') but contains CPU branding, redirect to full_name
            if role == "cores" and re.search(r"\b(Intel|AMD|Ryzen|Snapdragon|Core\s+Ultra|Processor)\b", v_str, re.I):
                if not cpu["full_name"]:
                    cpu["full_name"] = v_str
                role = "full_name"

            if role == "full_name" and not cpu["full_name"]:
                cpu["full_name"] = v_str
            elif role == "model" and not cpu["model"]:
                cpu["model"] = v_str
            elif role == "line" and not cpu["line"]:
                cpu["line"] = v_str
            elif role == "cores" and cpu["cores"] is None:
                m = re.search(r"\b(\d+)\s*(?:Core|cores|\(P\+E\))\b", v_str, re.I)
                if m:
                    cpu["cores"] = int(m.group(1))
            elif role == "threads" and cpu["threads"] is None:
                m = re.search(r"\b(\d+)\s*(?:Thread|threads)\b", v_str, re.I)
                if m:
                    cpu["threads"] = int(m.group(1))
            elif role == "cores_threads":
                m_c = re.search(r"\b(\d+)\s*(?:Core|C\b|cores)\b", v_str, re.I)
                m_t = re.search(r"\b(\d+)\s*(?:Thread|T\b|threads)\b", v_str, re.I)
                if m_c and cpu["cores"] is None:
                    cpu["cores"] = int(m_c.group(1))
                if m_t and cpu["threads"] is None:
                    cpu["threads"] = int(m_t.group(1))
            elif role == "clock_speed" and not cpu["clock_speed"]:
                cpu["clock_speed"] = v_str

        # If full_name is present, decompose via deterministic patterns
        target_text = f"{cpu['full_name'] or ''} {title}".strip()
        if target_text:
            # 1. Manufacturer
            if re.search(r"\b(intel|core|ultra|xeon|celeron|pentium|i[3579])\b|\bi[3579]-", target_text, re.I):
                cpu["manufacturer"] = "Intel"
            elif re.search(r"\b(amd|ryzen|athlon|r[3579])\b|\br[3579]-", target_text, re.I):
                cpu["manufacturer"] = "AMD"
            elif re.search(r"\bsnapdragon\b|\bqualcomm\b", target_text, re.I):
                cpu["manufacturer"] = "Qualcomm"
            elif re.search(r"\bapple\b|\bM[1234]\b", target_text, re.I):
                cpu["manufacturer"] = "Apple"

            # 2. Line & Model
            for m_u in re.finditer(r"(Core\s+Ultra\s+(?:X\s*)?[579]|Ultra\s+(?:X\s*)?[579])\s*(?:Processor\s+)?([0-9]{3,4}[A-Za-z0-9]{0,3})?", target_text, re.I):
                raw_u = m_u.group(1).strip()
                if not cpu["line"]:
                    cpu["line"] = "Core Ultra 7" if "7" in raw_u else ("Core Ultra 9" if "9" in raw_u else "Core Ultra 5")
                if m_u.group(2) and not cpu["model"]:
                    cpu["model"] = m_u.group(2).strip()

            for m_i in re.finditer(r"(Core\s+[iI]?[3579]|[iI][3579])[- ]*(?:Processor\s+)?([0-9]{3,5}[A-Za-z0-9]{0,3})?", target_text, re.I):
                if not cpu["line"]:
                    raw_grp = m_i.group(1)
                    num = re.search(r"[3579]", raw_grp).group(0)
                    if "core" in raw_grp.lower() and "i" not in raw_grp.lower():
                        cpu["line"] = f"Core {num}"
                    else:
                        cpu["line"] = f"Core i{num}"
                if m_i.group(2) and not cpu["model"]:
                    cpu["model"] = m_i.group(2).strip()

            for m_r in re.finditer(r"(Ryzen\s+(?:AI\s+(?:MAX\+?\s*)?)?(?:[3579]\b)?(?:\s+PRO)?|[rR][3579])\s*(?:HX\s*)?([0-9]{3,4}[A-Za-z0-9]{0,3})?", target_text, re.I):
                if not cpu["line"]:
                    raw_r = m_r.group(1).strip()
                    if re.match(r"^[rR][3579]$", raw_r):
                        cpu["line"] = f"Ryzen {raw_r[1]}"
                    else:
                        cpu["line"] = raw_r
                if m_r.group(2) and not cpu["model"]:
                    m_hx = re.search(r"\bHX\s*([0-9]{3,4})\b", target_text, re.I)
                    cpu["model"] = f"HX {m_hx.group(1)}" if m_hx else m_r.group(2).strip()

            m_sd = re.search(r"(Snapdragon\s+X\s+(?:Elite|Plus)?)\s*([A-Za-z0-9\-]+)?", target_text, re.I)
            if m_sd:
                if not cpu["line"]:
                    cpu["line"] = m_sd.group(1).strip()
                if m_sd.group(2) and not cpu["model"]:
                    cpu["model"] = m_sd.group(2).strip()

            # 3. Cores, Threads, and Clock Speed from full_name/target_text if not yet set
            all_cpu_text = f"{target_text} {' '.join(v for _, v, _ in cpu_raw_rows)}"
            if cpu["cores"] is None:
                m_c = re.search(r"\b(\d+)\s*(?:C\b|Cores?\b)", all_cpu_text, re.I)
                if m_c:
                    cpu["cores"] = int(m_c.group(1))
            if cpu["threads"] is None:
                m_t = re.search(r"\b(\d+)\s*(?:T\b|Threads?\b)", all_cpu_text, re.I)
                if not m_t:
                    m_t = re.search(r"\b\d+\s*cores?,\s*(\d+)\b", all_cpu_text, re.I)
                if m_t:
                    cpu["threads"] = int(m_t.group(1))
            if not cpu["clock_speed"]:
                m_clk = re.search(r"(?:up\s+to\s+)?(\d+(?:\.\d+)?\s*(?:GHz|MHz))\b", all_cpu_text, re.I)
                if m_clk:
                    cpu["clock_speed"] = m_clk.group(0).strip()

        # Limit Boundary Check: Trigger envelope if ANY CPU field is missing
        missing_cpu = []
        if not cpu["manufacturer"]:
            missing_cpu.append("processor manufacturer")
        if not cpu["line"]:
            missing_cpu.append("processor line")
        if not cpu["model"]:
            missing_cpu.append("processor model")
        if cpu["cores"] is None:
            missing_cpu.append("cpu core count")
        if cpu["threads"] is None:
            missing_cpu.append("cpu thread count")
        if not cpu["clock_speed"]:
            missing_cpu.append("cpu clock speed")

        if missing_cpu and (cpu_raw_rows or title):
            envelopes.append(ContextEnvelope(
                target_area="cpu",
                target_labels=missing_cpu,
                raw_key=cpu_raw_rows[0][0] if cpu_raw_rows else "Processor",
                raw_value=cpu["full_name"] or (" | ".join(v for _, v, _ in cpu_raw_rows[:2]) if cpu_raw_rows else title),
                product_title=title,
                sibling_context={"manufacturer": cpu["manufacturer"]},
                reason=f"unresolved_cpu_fields:{','.join(missing_cpu)}",
            ))

        return cpu, envelopes

    def extract_gpu(
        self,
        raw_specs: dict[str, Any],
        title: str,
        sibling_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract discrete and integrated GPU hardware specifications."""
        envelopes: list[ContextEnvelope] = []
        gpu: dict[str, Any] = {
            "manufacturer": None,
            "model": None,
            "full_name": None,
            "vram_gb": None,
            "tdp_w": None,
            "integrated": False,
        }

        gpu_raw_rows: list[tuple[str, str, str]] = []

        for raw_k, raw_v in raw_specs.items():
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            role = self.GPU_KEYWORDS.get(k_clean) or self.GPU_KEYWORDS.get(k_norm)
            if role and raw_v:
                gpu_raw_rows.append((raw_k, str(raw_v).strip(), role))

        combined_text = " ".join(v for _, v, _ in gpu_raw_rows) or title

        for raw_k, v_str, role in gpu_raw_rows:
            if role in ("tdp_w", "graphic wattage", "gpu power", "maximum graphics power"):
                m_w = re.search(r"(\d+)\s*(?:W|Watt)", v_str, re.I)
                if m_w and gpu["tdp_w"] is None:
                    gpu["tdp_w"] = int(m_w.group(1))

            if role in ("vram_gb", "graphics memory", "gpu memory") and gpu["vram_gb"] is None:
                m_v = re.search(r"\b([2468]|12|16|24)\s*GB\b", v_str, re.I)
                if m_v:
                    gpu["vram_gb"] = int(m_v.group(1))

        # Clean symbols that break regex boundaries (e.g. RTX® 5060 -> RTX 5060)
        clean_gpu_text = re.sub(r"[®™\u200e\u200f]", "", combined_text).strip()

        # Deterministic Discrete GPU Regex
        m_disc = re.search(
            r"\b(GeForce\s+RTX\s+[0-9]{4}(?:\s*Ti|\s*Laptop\s+GPU)?|"
            r"RTX\s+[0-9]{4}(?:\s*Ti|\s*Laptop\s+GPU)?|"
            r"Radeon\s+(?:RX\s+)?[0-9A-Za-z]+|"
            r"(?:GeForce\s+)?MX[0-9]{3}|"
            r"Intel\s+Arc\s+\w+)\b",
            clean_gpu_text,
            re.I,
        )
        if m_disc:
            gpu["model"] = m_disc.group(1).strip()
            up = m_disc.group(1).upper()
            if "RTX" in up or "GEFORCE" in up or "MX" in up:
                gpu["manufacturer"] = "NVIDIA"
            elif "RADEON" in up:
                gpu["manufacturer"] = "AMD"
            elif "ARC" in up or "INTEL" in up:
                gpu["manufacturer"] = "Intel"
            gpu["integrated"] = False
        else:
            # Deterministic Integrated GPU Regex
            m_int = re.search(
                r"\b(Adreno(?:\s+GPU)?|"
                r"Radeon(?:\s+660M|\s+780M|\s+880M|\s+Graphics)?|"
                r"Intel\s+(?:Iris\s+X[ee]|UHD|Graphics)|"
                r"Iris\s+X[ee]|UHD\s+Graphics)\b",
                clean_gpu_text,
                re.I,
            )
            if m_int:
                int_model = m_int.group(1).strip()
                if int_model.lower() == "adreno":
                    int_model = "Adreno GPU"
                elif int_model.lower() == "radeon":
                    int_model = "Radeon Graphics"
                gpu["model"] = int_model
                up_int = clean_gpu_text.upper()
                if "QUALCOMM" in up_int or "ADRENO" in up_int:
                    gpu["manufacturer"] = "Qualcomm"
                elif "AMD" in up_int or "RADEON" in up_int:
                    gpu["manufacturer"] = "AMD"
                elif "INTEL" in up_int:
                    gpu["manufacturer"] = "Intel"
                gpu["integrated"] = True

        # Fallback to Title if table did not match GPU
        if not gpu["model"] and not gpu["integrated"] and title:
            clean_title = re.sub(r"[®™\u200e\u200f]", "", title).strip()
            m_disc_title = re.search(
                r"\b(GeForce\s+RTX\s+[0-9]{4}(?:\s*Ti|\s*Laptop\s+GPU)?|"
                r"RTX\s+[0-9]{4}(?:\s*Ti|\s*Laptop\s+GPU)?|"
                r"Radeon\s+(?:RX\s+)?[0-9A-Za-z]+|"
                r"(?:GeForce\s+)?MX[0-9]{3}|"
                r"Intel\s+Arc\s+\w+)\b",
                clean_title,
                re.I,
            )
            if m_disc_title:
                gpu["model"] = m_disc_title.group(1).strip()
                up = m_disc_title.group(1).upper()
                gpu["manufacturer"] = "NVIDIA" if "RTX" in up or "GEFORCE" in up or "MX" in up else "AMD"
                gpu["integrated"] = False
            else:
                m_int_title = re.search(
                    r"\b(Adreno(?:\s+GPU)?|Radeon(?:\s+Graphics)?|Intel\s+(?:Iris\s+X[ee]|UHD|Graphics))\b",
                    clean_title,
                    re.I,
                )
                if m_int_title:
                    gpu["model"] = m_int_title.group(1).strip()
                    gpu["integrated"] = True

        # Fallback: Infer integrated GPU from CPU / architecture if no discrete GPU exists
        if not gpu["model"] and not gpu["integrated"]:
            cpu_ctx = (sibling_context or {}).get("cpu", "") or ""
            target_all = f"{cpu_ctx} {title}".upper()
            if "QUALCOMM" in target_all or "SNAPDRAGON" in target_all or "ADRENO" in target_all:
                gpu["model"] = "Adreno GPU"
                gpu["manufacturer"] = "Qualcomm"
                gpu["integrated"] = True
            elif "AMD" in target_all or "RYZEN" in target_all or "RADEON" in target_all:
                gpu["model"] = "Radeon Graphics"
                gpu["manufacturer"] = "AMD"
                gpu["integrated"] = True
            elif "APPLE" in target_all:
                gpu["model"] = "Apple GPU"
                gpu["manufacturer"] = "Apple"
                gpu["integrated"] = True
            elif "INTEL" in target_all or "CORE" in target_all:
                gpu["model"] = "Intel Graphics"
                gpu["manufacturer"] = "Intel"
                gpu["integrated"] = True

        # Extract VRAM fallback if still missing
        if gpu["vram_gb"] is None and not gpu["integrated"]:
            if gpu_raw_rows:
                m_vr = re.search(r"\b([123468]|10|12|16|20|24)\s*GB\b", combined_text, re.I)
                if m_vr and any(k in combined_text.upper() for k in ["RTX", "GTX", "GEFORCE", "VRAM", "GRAPHICS", "DEDICATED", "MX", "RADEON", "ARC"]):
                    gpu["vram_gb"] = int(m_vr.group(1))
            if gpu["vram_gb"] is None and title:
                m_vrt = re.search(r"\b(?:RTX\s*\d{4}(?:\s*Ti)?|GTX\s*\d{4}(?:\s*Ti)?)\s*(\d{1,2})\s*GB\b", title, re.I)
                if m_vrt:
                    gpu["vram_gb"] = int(m_vrt.group(1))

        # Standard discrete laptop GPU hardware architecture VRAM mapping
        if gpu["vram_gb"] is None and not gpu["integrated"] and gpu["model"]:
            model_up = gpu["model"].upper()
            if any(m in model_up for m in ["5060", "4060", "5050", "4070", "5070"]):
                gpu["vram_gb"] = 8
            elif "4050" in model_up:
                gpu["vram_gb"] = 6
            elif "4080" in model_up:
                gpu["vram_gb"] = 12
            elif any(m in model_up for m in ["4090", "5090", "5080"]):
                gpu["vram_gb"] = 16

        # Extract TDP/TGP fallback if still missing
        if gpu["tdp_w"] is None:
            m_tgp = re.search(r"(?:TGP|TDP|Max(?:imum)?\s+Power)\s*[:\s]?\s*(\d{2,3})\s*W\b", combined_text, re.I)
            if not m_tgp:
                m_tgp = re.search(r"(\d{2,3})\s*W\s*(?:TGP|TDP|Max(?:imum)?\s+Power)?\b", combined_text, re.I)
            if m_tgp:
                gpu["tdp_w"] = int(m_tgp.group(1))

        # Limit Boundary Check: Trigger envelope if ANY discrete GPU field or model is missing
        missing_gpu = []
        if not gpu["model"]:
            missing_gpu.append("graphics model")
        if not gpu["manufacturer"]:
            missing_gpu.append("graphics manufacturer")
        if not gpu["integrated"]:
            if gpu["vram_gb"] is None:
                missing_gpu.append("graphics vram")
            if gpu["tdp_w"] is None:
                missing_gpu.append("graphics power wattage")

        if gpu_raw_rows and missing_gpu:
            envelopes.append(ContextEnvelope(
                target_area="gpu",
                target_labels=missing_gpu,
                raw_key=gpu_raw_rows[0][0],
                raw_value=gpu_raw_rows[0][1],
                product_title=title,
                sibling_context=sibling_context or {},
                reason=f"unresolved_gpu_fields:{','.join(missing_gpu)}",
            ))

        return gpu, envelopes

    def extract_memory(
        self,
        raw_specs: dict[str, Any],
        title: str,
        sibling_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract installed and maximum RAM configurations."""
        envelopes: list[ContextEnvelope] = []
        mem: dict[str, Any] = {
            "capacity_gb": None,
            "memory_type": None,
            "speed": None,
            "slot_count": None,
            "max_supported_gb": None,
        }

        mem_rows: list[tuple[str, str, str]] = []

        for raw_k, raw_v in raw_specs.items():
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            role = self.RAM_KEYWORDS.get(k_clean) or self.RAM_KEYWORDS.get(k_norm)
            if role and raw_v:
                mem_rows.append((raw_k, str(raw_v).strip(), role))

        combined_text = " ".join(v for _, v, _ in mem_rows) or title

        for raw_k, v_str, role in mem_rows:
            # Maximum Supported RAM
            if role in ("max_supported_gb", "maximum memory supported", "max memory"):
                m_max = re.search(r"(\d+)\s*(?:GB|G)\b", v_str, re.I)
                if m_max and mem["max_supported_gb"] is None:
                    mem["max_supported_gb"] = int(m_max.group(1))

            # Slots
            if role in ("slot_count", "memory slots", "memory capability") or "slot" in raw_k.lower():
                m_s = re.search(r"\b([1234])\s*(?:x|slots?|SODIMM|SO-DIMM)", v_str, re.I)
                if m_s and mem["slot_count"] is None:
                    mem["slot_count"] = int(m_s.group(1))
                m_s_max = re.search(r"(?:max(?:imum)?(?:\s+capacity|\s+memory)?|\bup\s+to)\s*:?\s*(\d+)\s*(?:GB|G)\b", v_str, re.I)
                if m_s_max and mem["max_supported_gb"] is None:
                    mem["max_supported_gb"] = int(m_s_max.group(1))

            # Speed
            if role in ("speed", "system memory speed mt s") and not mem["speed"]:
                m_sp = re.search(r"(\d{4})\s*(?:MHz|MT/s|GT/s)?", v_str, re.I)
                if m_sp:
                    mem["speed"] = int(m_sp.group(1))

            # Type
            if role in ("memory_type", "memory technology") and not mem["memory_type"]:
                m_t = re.search(r"\b(LPDDR5X|LPDDR5|DDR5|DDR4)\b", v_str, re.I)
                if m_t:
                    mem["memory_type"] = m_t.group(1).upper()

        # Parse Installed RAM Capacity
        # 1. Multi-module (2x 12GB -> 24GB, 2x 8GB -> 16GB)
        m_multi = re.search(r"\b([1-4])\s*[xX*×]\s*(\d+)\s*(GB|G)?\b", combined_text, re.I)
        if m_multi:
            qty = int(m_multi.group(1))
            size = int(m_multi.group(2))
            mem["capacity_gb"] = qty * size
        else:
            # 2. Direct capacity without "up to"
            clean_mem = re.sub(r"\b(?:up\s+to|supports?\s+up\s+to)\s+\d+\s*(?:GB|G)?\b", "", combined_text, flags=re.I)
            m_cap = re.search(r"\b([48]|12|16|24|32|48|64|96|128)\s*(?:GB|G)?\s*(?:DDR|LPDDR|RAM|Memory|SO-DIMM)?\b", clean_mem, re.I)
            if m_cap:
                mem["capacity_gb"] = int(m_cap.group(1))

        # Fallback to Title if table memory was missing
        if mem["capacity_gb"] is None and title:
            clean_title = re.sub(r"\b(?:RTX|GTX|GeForce|Radeon|Arc)\s+[0-9A-Za-z\s]+?\s+(\d+)\s*GB(?!\s*(?:RAM|DDR|SO-DIMM|Memory))\b", "", title, flags=re.I)
            m_ram_exp = re.search(r"\b([48]|12|16|24|32|48|64|96|128)\s*(?:GB|G)\s*(?:RAM|DDR[45]|LPDDR\w*|Memory|on board)\b", clean_title, re.I)
            if m_ram_exp:
                mem["capacity_gb"] = int(m_ram_exp.group(1))
            else:
                m_ram_t = re.search(r"\b([48]|12|16|24|32|64|128)\s*(?:GB|G)\s*(?:RAM|DDR[45]|LPDDR\w*|Memory|on board)?\b", clean_title, re.I)
                if m_ram_t:
                    mem["capacity_gb"] = int(m_ram_t.group(1))

        # Parse compound memory fields from all raw specs and title if still missing
        all_specs_mem = " ".join(f"{k}: {v}" for k, v in raw_specs.items()) + " " + title
        if mem["max_supported_gb"] is None:
            m_max_c = re.search(r"(?:max(?:imum)?(?:\s+supported|\s+memory|\s+capacity)?|\bup\s+to|\bmax\b)\s*:?\s*(\d+)\s*(?:GB|G)\b", all_specs_mem, re.I)
            if m_max_c:
                mem["max_supported_gb"] = int(m_max_c.group(1))

        if not mem["memory_type"]:
            m_t_c = re.search(r"\b(LPDDR5X|LPDDR5|DDR5|DDR4|LPDDR4X|LPDDR4)\b", all_specs_mem, re.I)
            if m_t_c:
                mem["memory_type"] = m_t_c.group(1).upper()

        if mem["speed"] is None:
            m_sp_c = re.search(r"\b(3200|4800|5200|5600|6400|7500|8533)\s*(?:MHz|MT/s)?\b", all_specs_mem, re.I)
            if not m_sp_c:
                m_sp_c = re.search(r"(?:DDR[45][-\s]*)?(\d{4})\s*(?:MHz|MT/s)?\b", all_specs_mem, re.I)
            if m_sp_c:
                mem["speed"] = int(m_sp_c.group(1))

        if mem["slot_count"] is None:
            m_s_c = re.search(r"\b([1234])\s*(?:x\s*Slots?|x\s*SO-?DIMM|SO-?DIMM\s*slots?|slots?)\b", combined_text, re.I)
            if m_s_c:
                mem["slot_count"] = int(m_s_c.group(1))

        # Limit Boundary Check: Trigger envelope if ANY memory field is missing
        missing_mem = []
        if mem["capacity_gb"] is None:
            missing_mem.append("ram capacity")
        if not mem["memory_type"]:
            missing_mem.append("ram type")
        if mem["speed"] is None:
            missing_mem.append("ram speed")
        if mem["max_supported_gb"] is None:
            missing_mem.append("max ram capacity")
        if mem["slot_count"] is None:
            missing_mem.append("ram slot count")

        if mem_rows and missing_mem:
            envelopes.append(ContextEnvelope(
                target_area="memory",
                target_labels=missing_mem,
                raw_key=mem_rows[0][0],
                raw_value=" | ".join(v for _, v, _ in mem_rows[:2]),
                product_title=title,
                sibling_context=sibling_context or {},
                reason=f"unresolved_memory_fields:{','.join(missing_mem)}",
            ))

        return mem, envelopes

    def extract_storage(
        self,
        raw_specs: dict[str, Any],
        title: str,
        sibling_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract installed storage capacity, expansion ceilings, and slot configurations."""
        envelopes: list[ContextEnvelope] = []
        storage: dict[str, Any] = {
            "capacity_gb": None,
            "storage_type": "SSD",
            "interface": None,
            "form_factor": None,
            "slot_count": None,
            "max_supported_gb": None,
            "summary": None,
        }

        storage_rows: list[tuple[str, str, str]] = []

        for raw_k, raw_v in raw_specs.items():
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            role = self.STORAGE_KEYWORDS.get(k_clean) or self.STORAGE_KEYWORDS.get(k_norm)
            if role and raw_v:
                storage_rows.append((raw_k, str(raw_v).strip(), role))

        combined_text = " ".join(v for _, v, _ in storage_rows) or title

        for raw_k, v_str, role in storage_rows:
            if role == "slot_count" and storage["slot_count"] is None:
                m_sl = re.search(r"\b([1234])\s*(?:x|\s*M\.2|\s*slots?)", v_str, re.I)
                if m_sl:
                    storage["slot_count"] = int(m_sl.group(1))

            if role == "interface" and not storage["interface"]:
                storage["interface"] = v_str

            if role == "max_supported_gb" and storage["max_supported_gb"] is None:
                m_mx = re.search(r"\b(?:up\s+to|supports?\s+up\s+to)\s*(\d+)\s*(TB|GB)\b", v_str, re.I)
                if m_mx:
                    sz = int(m_mx.group(1))
                    storage["max_supported_gb"] = sz * 1024 if "T" in m_mx.group(2).upper() else sz

            if role == "summary" and not storage["summary"]:
                storage["summary"] = v_str

        # Expansion ceiling extraction
        m_ceil = re.search(r"\b(?:up\s+to|supports?\s+up\s+to)\s*(\d+)\s*(TB|GB)\b", combined_text, re.I)
        if m_ceil and storage["max_supported_gb"] is None:
            sz = int(m_ceil.group(1))
            storage["max_supported_gb"] = sz * 1024 if "T" in m_ceil.group(2).upper() else sz

        # Installed Storage Parsing (ignore "up to" expansion clause)
        clean_storage = re.sub(r"\b(?:up\s+to|supports?\s+up\s+to)\s*\d+\s*(?:TB|GB)?\b", "", combined_text, flags=re.I)
        # Mask M.2 form factors (2280, 2242, 2230) and 2.5" drive bays
        clean_storage = re.sub(r"\bM\.2\s*(?:2230|2242|2280)\b", "M.2_SLOT", clean_storage, flags=re.I)
        clean_storage = re.sub(r"\b(?:[1-4]x\s*)?(?:2230|2242|2280)\b", "M.2_SLOT", clean_storage, flags=re.I)
        clean_storage = re.sub(r'\b(?:[1-4]x\s*)?2\.5(?:\"|\s*inch|\s*[- ]bay)\b', "SATA_BAY", clean_storage, flags=re.I)

        # Multi-module (e.g. 2x 1TB -> 2048GB) - requires explicit TB or GB unit
        m_multi_st = re.search(r"\b([1-4])\s*[xX*×]\s*(\d{1,4})\s*(TB|GB)\b", clean_storage, re.I)
        if m_multi_st:
            qty = int(m_multi_st.group(1))
            size = int(m_multi_st.group(2))
            unit = m_multi_st.group(3).upper()
            total = qty * size
            storage["capacity_gb"] = total * 1024 if "T" in unit else total
        else:
            m_cap = re.search(r"\b(128|256|512|1024|2048|4096)\s*(?:GB|G)?\b", clean_storage, re.I)
            if m_cap:
                storage["capacity_gb"] = int(m_cap.group(1))
            else:
                m_tb = re.search(r"\b([1248])\s*(?:TB|T)\b", clean_storage, re.I)
                if m_tb:
                    storage["capacity_gb"] = int(m_tb.group(1)) * 1024

        # Fallback to Title if table storage only specified expansion ceiling, was empty, or invalid (<128GB)
        if (storage["capacity_gb"] is None or storage["capacity_gb"] < 128) and title:
            clean_title = re.sub(r"\b(?:RTX|GTX|GeForce|Radeon|Arc)\s+[0-9A-Za-z\s]+?\s+(\d+)\s*GB(?!\s*(?:RAM|DDR|SO-DIMM|Memory))\b", "", title, flags=re.I)
            m_st_tb = re.search(r"\b([1248])\s*TB\b", clean_title, re.I)
            if m_st_tb:
                storage["capacity_gb"] = int(m_st_tb.group(1)) * 1024
            else:
                m_st_gb = re.search(r"\b(128|256|512|1024|2048|4096)\s*GB\b", clean_title, re.I)
                if m_st_gb:
                    storage["capacity_gb"] = int(m_st_gb.group(1))
                else:
                    m_st_t = re.search(r"\b(\d{1,4})\s*(?:TB|GB)\s*(?:SSD|PCIe|NVMe|M\.2|Storage)?\b", clean_title, re.I)
                    if m_st_t:
                        val = int(m_st_t.group(1))
                        storage["capacity_gb"] = val * 1024 if val in (1, 2, 4, 8) else val

        # Interface & Form factor detection
        if not storage["interface"]:
            if re.search(r"PCIe\s*(?:Gen\s*)?4|Gen4|PCIe\s*4\.0", combined_text, re.I):
                storage["interface"] = "PCIe 4.0 NVMe"
            elif re.search(r"PCIe\s*(?:Gen\s*)?3|Gen3", combined_text, re.I):
                storage["interface"] = "PCIe 3.0 NVMe"
            elif re.search(r"NVMe", combined_text, re.I):
                storage["interface"] = "NVMe"

        if not storage["form_factor"]:
            m_ff_c = re.search(r"M\.2\s*(2230|2242|2280)", combined_text, re.I)
            if m_ff_c:
                storage["form_factor"] = f"M.2 {m_ff_c.group(1)}"
            elif re.search(r"M\.2\s*2280", combined_text, re.I):
                storage["form_factor"] = "M.2 2280"

        if storage["slot_count"] is None:
            m_sl_c = re.search(r"\b([1234])\s*(?:x\s*M\.2|x\s*slots?|M\.2\s*slots?)\b", combined_text, re.I)
            if m_sl_c:
                storage["slot_count"] = int(m_sl_c.group(1))

        # Limit Boundary Check: Trigger envelope if ANY storage field is missing
        missing_st = []
        if storage["capacity_gb"] is None:
            missing_st.append("storage capacity")
        if not storage["storage_type"]:
            missing_st.append("storage type")
        if not storage["interface"]:
            missing_st.append("storage interface")
        if not storage["form_factor"]:
            missing_st.append("storage form factor")
        if storage["slot_count"] is None:
            missing_st.append("storage slot count")
        if storage["max_supported_gb"] is None:
            missing_st.append("max storage capacity")

        if storage_rows and missing_st:
            envelopes.append(ContextEnvelope(
                target_area="storage",
                target_labels=missing_st,
                raw_key=storage_rows[0][0],
                raw_value=" | ".join(v for _, v, _ in storage_rows[:2]),
                product_title=title,
                sibling_context=sibling_context or {},
                reason=f"unresolved_storage_fields:{','.join(missing_st)}",
            ))

        return storage, envelopes

    def extract_display(
        self,
        raw_specs: dict[str, Any],
        title: str,
        sibling_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract display dimensions, resolution, and refresh rate."""
        envelopes: list[ContextEnvelope] = []
        disp: dict[str, Any] = {
            "size_inches": None,
            "resolution": None,
            "resolution_width": None,
            "resolution_height": None,
            "panel_type": None,
            "refresh_rate_hz": None,
            "touchscreen": False,
            "aspect_ratio": None,
            "summary": None,
        }

        disp_rows: list[tuple[str, str, str]] = []

        for raw_k, raw_v in raw_specs.items():
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            role = self.DISPLAY_KEYWORDS.get(k_clean) or self.DISPLAY_KEYWORDS.get(k_norm)
            if role and raw_v:
                disp_rows.append((raw_k, str(raw_v).strip(), role))

        combined_text = " ".join(v for _, v, _ in disp_rows) or title

        for raw_k, v_str, role in disp_rows:
            if role == "refresh_rate_hz" and disp["refresh_rate_hz"] is None:
                m_hz = re.search(r"(\d{2,3})\s*Hz", v_str, re.I)
                if m_hz:
                    disp["refresh_rate_hz"] = int(m_hz.group(1))

            if role == "touchscreen":
                v_low = v_str.lower()
                if any(w in v_low for w in ["yes", "true", "touch", "multi-touch"]) and "non-touch" not in v_low:
                    disp["touchscreen"] = True
                elif any(w in v_low for w in ["no", "false", "non-touch", "none"]):
                    disp["touchscreen"] = False

            if role == "aspect_ratio" and not disp["aspect_ratio"]:
                m_ar = re.search(r"(\d{1,2}:\d{1,2})", v_str)
                if m_ar:
                    disp["aspect_ratio"] = m_ar.group(1)

            if role == "panel_type" and not disp["panel_type"]:
                m_p = re.search(r"\b(OLED|IPS|Mini[- ]LED|TN|VA)\b", v_str, re.I)
                if m_p:
                    disp["panel_type"] = m_p.group(1).upper()

            if role == "summary" and not disp["summary"]:
                disp["summary"] = v_str

        # Screen Size Parsing (supports inches, unicode prime quotes, cm conversions)
        m_inch = re.search(r'(\d{2}(?:\.\d+)?)\s*(?:["\u2033\u201d\u2019]|inch|\-inch|\s*in\b)', combined_text, re.I)
        if m_inch:
            disp["size_inches"] = float(m_inch.group(1))
        else:
            m_cm = re.search(r"(\d{2}(?:\.\d+)?)\s*cm", combined_text, re.I)
            if m_cm:
                disp["size_inches"] = round(float(m_cm.group(1)) / 2.54, 1)

        # Fallback to Title if table display size was missing
        if disp["size_inches"] is None and title:
            m_inch_t = re.search(r'(\d{2}(?:\.\d+)?)\s*(?:["\u2033\u201d\u2019]|inch|\-inch|\s*in\b|fhd|wuxga|qhd|uhd|oled)', title, re.I)
            if m_inch_t:
                disp["size_inches"] = float(m_inch_t.group(1))
            else:
                m_model_sz = re.search(r"\b(?:LOQ|Legion|Victus|Omen|AORUS|A|Alienware|Inspiron|XPS|Nitro\s+V|IdeaPad|Zenbook|Vivobook|HP\s+)?(13|14|15|16|17|18)\b", title, re.I)
                if not m_model_sz:
                    m_model_sz = re.search(r"\b(?:LOQ|Legion|Victus|Omen|AORUS|A|Alienware|Inspiron|XPS|Nitro\s+V|IdeaPad|Zenbook|Vivobook)\s*([1-9][0-9])", title, re.I)
                if m_model_sz:
                    sz_map = {"13": 13.3, "14": 14.0, "15": 15.6, "16": 16.0, "17": 17.3, "18": 18.0}
                    disp["size_inches"] = sz_map.get(m_model_sz.group(1))

        # Resolution Parsing
        m_res = re.search(r"(\d{3,4})\s*[xX*×]\s*(\d{3,4})", combined_text)
        if m_res:
            w, h = int(m_res.group(1)), int(m_res.group(2))
            disp["resolution"] = f"{w} x {h}"
            disp["resolution_width"] = w
            disp["resolution_height"] = h
        elif re.search(r"\bFHD\b|Full\s+HD", combined_text, re.I):
            disp["resolution"] = "1920 x 1080"
            disp["resolution_width"] = 1920
            disp["resolution_height"] = 1080
        elif re.search(r"\bWUXGA\b", combined_text, re.I):
            disp["resolution"] = "1920 x 1200"
            disp["resolution_width"] = 1920
            disp["resolution_height"] = 1200
        elif re.search(r"\bWQXGA\b|2\.5K|2K", combined_text, re.I):
            disp["resolution"] = "2560 x 1600"
            disp["resolution_width"] = 2560
            disp["resolution_height"] = 1600

        # Refresh Rate Fallback
        if disp["refresh_rate_hz"] is None:
            m_rf = re.search(r"\b(60|90|120|144|165|180|240|300|360)\s*Hz\b", combined_text, re.I)
            if m_rf:
                disp["refresh_rate_hz"] = int(m_rf.group(1))
            elif title:
                m_rf_t = re.search(r"\b(60|90|120|144|165|180|240|300|360)\s*Hz\b", title, re.I)
                if m_rf_t:
                    disp["refresh_rate_hz"] = int(m_rf_t.group(1))

        # Touchscreen detection across display text and title
        if not disp["touchscreen"]:
            all_disp = f"{combined_text} {title}"
            if re.search(r"\btouch\s*screen|touchscreen\b", all_disp, re.I) and not re.search(r"\bnon-touch|no touch\b", all_disp, re.I):
                disp["touchscreen"] = True

        # Compound panel type and aspect ratio fallback
        if not disp["panel_type"]:
            m_p_c = re.search(r"\b(OLED|IPS|Mini[- ]LED|TN|VA)\b", combined_text, re.I)
            if m_p_c:
                disp["panel_type"] = m_p_c.group(1).upper()

        if not disp["aspect_ratio"]:
            m_ar_c = re.search(r"\b(16:10|16:9|3:2|4:3)\b", combined_text)
            if m_ar_c:
                disp["aspect_ratio"] = m_ar_c.group(1)
            elif disp["resolution_width"] and disp["resolution_height"]:
                ratio = disp["resolution_width"] / disp["resolution_height"]
                if abs(ratio - 16 / 10) < 0.05:
                    disp["aspect_ratio"] = "16:10"
                elif abs(ratio - 16 / 9) < 0.05:
                    disp["aspect_ratio"] = "16:9"
                elif abs(ratio - 3 / 2) < 0.05:
                    disp["aspect_ratio"] = "3:2"

        # Limit Boundary Check: Trigger envelope if ANY display field is missing
        missing_disp = []
        if disp["size_inches"] is None:
            missing_disp.append("screen size")
        if not disp["resolution"]:
            missing_disp.append("screen resolution")
        if disp["refresh_rate_hz"] is None:
            missing_disp.append("display refresh rate")
        if not disp["panel_type"]:
            missing_disp.append("display panel type")
        if not disp["aspect_ratio"]:
            missing_disp.append("aspect ratio")

        if disp_rows and missing_disp:
            envelopes.append(ContextEnvelope(
                target_area="display",
                target_labels=missing_disp,
                raw_key=disp_rows[0][0],
                raw_value=" | ".join(v for _, v, _ in disp_rows[:2]),
                product_title=title,
                sibling_context=sibling_context or {},
                reason=f"unresolved_display_fields:{','.join(missing_disp)}",
            ))

        return disp, envelopes

    def extract_connectivity(
        self,
        raw_specs: dict[str, Any],
        title: str,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract I/O ports, Wi-Fi standard, Bluetooth, and Ethernet."""
        envelopes: list[ContextEnvelope] = []
        conn: dict[str, Any] = {
            "wifi": None,
            "bluetooth": None,
            "ethernet": None,
            "ports": [],
        }

        for raw_k, raw_v in raw_specs.items():
            if not raw_v:
                continue
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            v_str = str(raw_v).strip()

            # Direct Ports detection
            if re.search(r"\b(ports?|hdmi|usb|type[- ]?c|thunderbolt|ethernet|rj[- ]?45|displayport|audio[- ]?jack)\b", k_clean, re.I):
                if re.search(r"\b(ethernet|rj[- ]?45)\b", k_clean, re.I) and not conn["ethernet"]:
                    conn["ethernet"] = v_str
                if not any(ex in k_clean for ex in ["supported", "memory", "ram", "storage", "drive", "ssd", "interface", "card reader"]):
                    if v_str.lower() not in ("no", "0", "none"):
                        conn["ports"].append(f"{raw_k}: {v_str}")
                continue

            role = self.CONNECTIVITY_KEYWORDS.get(k_clean) or self.CONNECTIVITY_KEYWORDS.get(k_norm)
            if role in ("networking", "network and communication") or "networking" in k_clean:
                m_wf = re.search(r"(Killer\s+Wi-Fi[0-9A-Za-z\s]+(?:\([0-9A-Za-z\.]+\))?|Wi-Fi\s*[0-9A-Za-z\s]+(?:\([0-9A-Za-z\.]+\))?|802\.11[a-z]+)", v_str, re.I)
                if m_wf and not conn["wifi"]:
                    conn["wifi"] = m_wf.group(1).strip().rstrip(",")
                m_bt_net = re.search(r"(?:BT|Bluetooth)[®™\s\(\)R]*([0-9\.]+\+?)", v_str, re.I)
                if m_bt_net and not conn["bluetooth"]:
                    conn["bluetooth"] = f"Bluetooth {m_bt_net.group(1)}"
                m_eth_net = re.search(r"(\d+(?:\.\d+)?\s*Gigabit(?:\s*Ethernet)?|Gigabit(?:\s*Ethernet)?|RJ-?45)", v_str, re.I)
                if m_eth_net and not conn["ethernet"]:
                    conn["ethernet"] = m_eth_net.group(1).strip()
            elif role == "wifi" and not conn["wifi"]:
                conn["wifi"] = v_str
            elif role == "bluetooth" and not conn["bluetooth"]:
                conn["bluetooth"] = v_str
            elif role == "ethernet" and not conn["ethernet"]:
                conn["ethernet"] = v_str
            elif role == "wifi_bt":
                if not conn["wifi"]:
                    conn["wifi"] = v_str
                if not conn["bluetooth"]:
                    m_bt = re.search(r"(?:BT|Bluetooth)[®™\s\(\)R]*([0-9\.]+)", v_str, re.I)
                    if m_bt:
                        conn["bluetooth"] = f"Bluetooth {m_bt.group(1)}"
                    elif re.search(r"\b(?:Bluetooth|BT)\b", v_str, re.I):
                        conn["bluetooth"] = "Bluetooth"

        # Check all connectivity strings for bluetooth and ethernet if still missing
        all_conn_text = f"{conn.get('wifi') or ''} {' '.join(conn['ports'])}"
        if not conn["bluetooth"]:
            m_bt_c = re.search(r"(?:BT|Bluetooth)[®™\s\(\)R]*([0-9\.]+)", all_conn_text, re.I)
            if m_bt_c:
                conn["bluetooth"] = f"Bluetooth {m_bt_c.group(1)}"
            elif re.search(r"\b(?:Bluetooth|BT)\b", all_conn_text, re.I):
                conn["bluetooth"] = "Bluetooth"
            else:
                for raw_k, raw_v in raw_specs.items():
                    if raw_v and re.search(r"bluetooth|\bbt\b", f"{raw_k} {raw_v}", re.I):
                        m_bt_raw = re.search(r"(?:BT|Bluetooth)[®™\s\(\)R]*([0-9\.]+)", str(raw_v), re.I)
                        if m_bt_raw:
                            conn["bluetooth"] = f"Bluetooth {m_bt_raw.group(1)}"
                            break
                        elif re.search(r"\b(?:Bluetooth|BT)\b", str(raw_v), re.I):
                            conn["bluetooth"] = "Bluetooth"
                            break

        if not conn["ethernet"]:
            if re.search(r"\b(?:RJ-?45|Ethernet|LAN|Gigabit)\b", all_conn_text, re.I):
                m_eth_spd = re.search(r"\b(2\.5Gbps|1Gbps|1000Mbps|Gigabit)\b", all_conn_text, re.I)
                conn["ethernet"] = f"{m_eth_spd.group(1)} Ethernet (RJ-45)" if m_eth_spd else "Gigabit Ethernet (RJ-45)"

        missing_conn = []
        if not conn["wifi"]:
            missing_conn.append("wifi standard")
        if not conn["bluetooth"]:
            missing_conn.append("bluetooth version")
        if not conn["ethernet"]:
            missing_conn.append("ethernet speed")

        if missing_conn and (conn["ports"] or title):
            envelopes.append(ContextEnvelope(
                target_area="connectivity",
                target_labels=missing_conn,
                raw_key="connectivity",
                raw_value=" | ".join(conn["ports"][:3]) if conn["ports"] else title,
                product_title=title,
                sibling_context={},
                reason=f"unresolved_connectivity_fields:{','.join(missing_conn)}",
            ))

        return conn, envelopes

    def extract_power_battery(
        self,
        raw_specs: dict[str, Any],
        title: str,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract battery capacity Wh, cell counts, and adapter wattage."""
        envelopes: list[ContextEnvelope] = []
        pwr: dict[str, Any] = {
            "battery_capacity_wh": None,
            "battery_cells": None,
            "power_adapter_w": None,
            "summary": None,
        }

        for raw_k, raw_v in raw_specs.items():
            if not raw_v:
                continue
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            role = self.POWER_BATTERY_KEYWORDS.get(k_clean) or self.POWER_BATTERY_KEYWORDS.get(k_norm)
            v_str = str(raw_v).strip()

            if role == "battery_capacity_wh" and pwr["battery_capacity_wh"] is None:
                m_wh = re.search(r"(\d+(?:\.\d+)?)\s*Wh", v_str, re.I)
                if m_wh:
                    pwr["battery_capacity_wh"] = float(m_wh.group(1))
                pwr["summary"] = v_str

            elif role == "power_adapter_w" and pwr["power_adapter_w"] is None:
                m_w = re.search(r"(\d+)\s*W\b", v_str, re.I)
                if m_w:
                    pwr["power_adapter_w"] = int(m_w.group(1))

            elif role == "battery_cells" and pwr["battery_cells"] is None:
                m_c = re.search(r"(\d+)\s*cell", v_str, re.I)
                if m_c:
                    pwr["battery_cells"] = int(m_c.group(1))

        power_rows = [(k, str(v)) for k, v in raw_specs.items() if self.POWER_BATTERY_KEYWORDS.get(k.strip().lower()) or self.POWER_BATTERY_KEYWORDS.get(self._normalize_key(k))]
        all_pwr_text = " ".join(v for _, v in power_rows)
        if not all_pwr_text:
            all_pwr_text = " ".join(str(v) for v in raw_specs.values() if re.search(r"battery|adapter|wh\b|\b\d+w\b", str(v), re.I))

        if pwr["battery_capacity_wh"] is None:
            m_wh_c = re.search(r"(\d+(?:\.\d+)?)\s*Wh\b", all_pwr_text, re.I)
            if m_wh_c:
                pwr["battery_capacity_wh"] = float(m_wh_c.group(1))

        if pwr["power_adapter_w"] is None:
            m_w_c = re.search(r"(\d+)\s*W\b(?:\s*(?:Adapter|Slim|Power|charger|ac\s+adapter))?", all_pwr_text, re.I)
            if m_w_c:
                pwr["power_adapter_w"] = int(m_w_c.group(1))

        if pwr["battery_cells"] is None:
            m_c_c = re.search(r"(\d+)\s*[- ]?cells?\b", all_pwr_text, re.I)
            if m_c_c:
                pwr["battery_cells"] = int(m_c_c.group(1))

        missing_power = []
        if pwr["battery_capacity_wh"] is None:
            missing_power.append("battery capacity wh")
        if pwr["power_adapter_w"] is None:
            missing_power.append("power adapter wattage")
        if pwr["battery_cells"] is None:
            missing_power.append("battery cells")

        if missing_power and (power_rows or all_pwr_text):
            envelopes.append(ContextEnvelope(
                target_area="power_battery",
                target_labels=missing_power,
                raw_key=power_rows[0][0] if power_rows else "Battery & Power",
                raw_value=" | ".join(f"{k}: {v}" for k, v in power_rows[:2]) if power_rows else all_pwr_text[:120],
                product_title=title,
                sibling_context={},
                reason=f"unresolved_power_fields:{','.join(missing_power)}",
            ))

        return pwr, envelopes

    def extract_physical(
        self,
        raw_specs: dict[str, Any],
        title: str,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract weight, dimensions, and chassis color."""
        envelopes: list[ContextEnvelope] = []
        phys: dict[str, Any] = {
            "weight_kg": None,
            "color": None,
            "width_mm": None,
            "depth_mm": None,
            "height_mm": None,
        }

        for raw_k, raw_v in raw_specs.items():
            if not raw_v:
                continue
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            role = self.PHYSICAL_KEYWORDS.get(k_clean) or self.PHYSICAL_KEYWORDS.get(k_norm)
            v_str = str(raw_v).strip()

            if role in ("weight_kg", "physical_characteristics") and phys["weight_kg"] is None:
                m_kg = re.search(r"(\d+(?:\.\d+)?)\s*kg", v_str, re.I)
                if m_kg:
                    phys["weight_kg"] = float(m_kg.group(1))
                else:
                    m_lb = re.search(r"(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)\b", v_str, re.I)
                    if m_lb:
                        phys["weight_kg"] = round(float(m_lb.group(1)) * 0.45359237, 2)

            if role in ("color", "physical_characteristics") and not phys["color"]:
                m_col = re.search(r"\b(Black|White|Silver|Gray|Grey|Dark Shadow Gray|Eclipse Black|Mica Silver|Blue|Platinum)\b", v_str, re.I)
                if m_col:
                    phys["color"] = m_col.group(1).strip()
                elif role == "color":
                    phys["color"] = v_str

            if (role == "height_mm" or "height" in k_clean) and phys["height_mm"] is None:
                m_h = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|cm)\b", v_str, re.I)
                if m_h:
                    val = float(m_h.group(1))
                    phys["height_mm"] = val * 10 if "cm" in v_str.lower() else val

            if (role == "width_mm" or "width" in k_clean) and phys["width_mm"] is None:
                m_w = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|cm)\b", v_str, re.I)
                if m_w:
                    val = float(m_w.group(1))
                    phys["width_mm"] = val * 10 if "cm" in v_str.lower() else val

            if (role == "depth_mm" or "depth" in k_clean) and phys["depth_mm"] is None:
                m_d = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|cm)\b", v_str, re.I)
                if m_d:
                    val = float(m_d.group(1))
                    phys["depth_mm"] = val * 10 if "cm" in v_str.lower() else val

            if role in ("dimensions", "physical_characteristics"):
                m_hwd = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*\(H\)\s*[xX*×]\s*(\d+(?:\.\d+)?)\s*mm\s*\(W\)\s*[xX*×]\s*(\d+(?:\.\d+)?)\s*mm\s*\(D\)", v_str, re.I)
                if m_hwd:
                    phys["height_mm"] = float(m_hwd.group(1))
                    phys["width_mm"] = float(m_hwd.group(2))
                    phys["depth_mm"] = float(m_hwd.group(3))
                else:
                    m_dim = re.search(r"(\d+(?:\.\d+)?)\s*[xX*×]\s*(\d+(?:\.\d+)?)\s*[xX*×]\s*(\d+(?:\.\d+)?)", v_str)
                    if m_dim:
                        if phys["width_mm"] is None:
                            phys["width_mm"] = float(m_dim.group(1))
                        if phys["depth_mm"] is None:
                            phys["depth_mm"] = float(m_dim.group(2))
                        if phys["height_mm"] is None:
                            phys["height_mm"] = float(m_dim.group(3))

        if phys["weight_kg"] is None:
            for k, v in raw_specs.items():
                if "weight" in k.lower() and v:
                    m_kg = re.search(r"(\d+(?:\.\d+)?)\s*kg", str(v), re.I)
                    if m_kg:
                        phys["weight_kg"] = float(m_kg.group(1))
                        break
                    m_lb = re.search(r"(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)\b", str(v), re.I)
                    if m_lb:
                        phys["weight_kg"] = round(float(m_lb.group(1)) * 0.45359237, 2)
                        break

        missing_phys = []
        if phys["weight_kg"] is None:
            missing_phys.append("laptop weight")
        if not phys["color"]:
            missing_phys.append("laptop color")
        if phys["width_mm"] is None:
            missing_phys.append("laptop width")
        if phys["depth_mm"] is None:
            missing_phys.append("laptop depth")
        if phys["height_mm"] is None:
            missing_phys.append("laptop height")

        phys_rows = [(k, str(v)) for k, v in raw_specs.items() if self.PHYSICAL_KEYWORDS.get(k.strip().lower()) or self.PHYSICAL_KEYWORDS.get(self._normalize_key(k))]
        if missing_phys and phys_rows:
            envelopes.append(ContextEnvelope(
                target_area="physical",
                target_labels=missing_phys,
                raw_key=phys_rows[0][0],
                raw_value=" | ".join(f"{k}: {v}" for k, v in phys_rows),
                product_title=title,
                sibling_context={},
                reason=f"unresolved_physical_fields:{','.join(missing_phys)}",
            ))

        return phys, envelopes

    def extract_operating_system(
        self,
        raw_specs: dict[str, Any],
        title: str,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract operating system."""
        envelopes: list[ContextEnvelope] = []
        os_info: dict[str, Any] = {"name": None}

        for raw_k, raw_v in raw_specs.items():
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            role = self.OS_KEYWORDS.get(k_clean) or self.OS_KEYWORDS.get(k_norm)
            if role == "name" and raw_v and not os_info["name"]:
                v_str = str(raw_v).strip()
                # Skip nonsensical store typos like 'Up to 10 MHz'
                if not re.search(r"MHz|GHz", v_str, re.I):
                    os_info["name"] = v_str

        os_rows = [(k, str(v)) for k, v in raw_specs.items() if self.OS_KEYWORDS.get(k.strip().lower()) or self.OS_KEYWORDS.get(self._normalize_key(k))]
        if not os_info["name"] and os_rows:
            envelopes.append(ContextEnvelope(
                target_area="operating_system",
                target_labels=["operating system name"],
                raw_key=os_rows[0][0],
                raw_value=" | ".join(f"{k}: {v}" for k, v in os_rows),
                product_title=title,
                sibling_context={},
                reason="unresolved_os_name",
            ))

        return os_info, envelopes

    def extract_build_security(
        self,
        raw_specs: dict[str, Any],
        title: str,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Extract keyboard, backlight, and security hardware."""
        envelopes: list[ContextEnvelope] = []
        build: dict[str, Any] = {
            "has_backlit_keyboard": None,
            "has_fingerprint": None,
            "pointing_device": None,
            "security_features": None,
        }

        for raw_k, raw_v in raw_specs.items():
            if not raw_v:
                continue
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            role = self.BUILD_SECURITY_KEYWORDS.get(k_clean) or self.BUILD_SECURITY_KEYWORDS.get(k_norm)
            v_str = str(raw_v).strip()

            if role in ("keyboard", "backlit_keyboard", "has_backlit_keyboard") or any(w in k_clean for w in ["keyboard", "input devices"]):
                if re.search(r"backlit|backlight|rgb|white\s+backlit", v_str, re.I):
                    build["has_backlit_keyboard"] = True
                elif v_str.lower() in ("yes", "true"):
                    build["has_backlit_keyboard"] = True
                elif re.search(r"non-backlit|no backlight", v_str, re.I) or v_str.lower() in ("no", "false"):
                    build["has_backlit_keyboard"] = False

            if role in ("fingerprint", "built_in_devices") or any(w in k_clean for w in ["fingerprint", "built-in devices", "built in devices"]):
                if re.search(r"no\s+fingerprint|without\s+fingerprint|\bn/a\b", v_str, re.I):
                    build["has_fingerprint"] = False
                elif re.search(r"\bfingerprint\b", v_str, re.I) and not re.search(r"\bno\b|\bn/a\b", v_str, re.I):
                    build["has_fingerprint"] = True
                elif v_str.lower() in ("no", "non-touch", "none", "n/a"):
                    build["has_fingerprint"] = False

            if "special feature" in k_clean or role == "special_features":
                if re.search(r"backlit|backlight|rgb", v_str, re.I) and not re.search(r"non-backlit|no backlight", v_str, re.I):
                    build["has_backlit_keyboard"] = True
                if re.search(r"\bfingerprint\b", v_str, re.I) and not re.search(r"\bno\b|\bn/a\b", v_str, re.I):
                    build["has_fingerprint"] = True

            elif role == "security_features" and not build["security_features"]:
                build["security_features"] = v_str

        # Fallback to Title for backlit keyboard if still unresolved
        if build["has_backlit_keyboard"] is None and title:
            if re.search(r"\b(?:backlit|backlight|rgb\s+backlit|4z\s+rgb|rgb\s+keyboard)\b", title, re.I) and not re.search(r"non-backlit|no backlight", title, re.I):
                build["has_backlit_keyboard"] = True

        missing_build = []
        if build["has_backlit_keyboard"] is None:
            missing_build.append("backlit keyboard")
        if build["has_fingerprint"] is None:
            missing_build.append("fingerprint reader")

        build_rows = [(k, str(v)) for k, v in raw_specs.items() if self.BUILD_SECURITY_KEYWORDS.get(k.strip().lower()) or self.BUILD_SECURITY_KEYWORDS.get(self._normalize_key(k))]
        if missing_build and build_rows:
            envelopes.append(ContextEnvelope(
                target_area="build",
                target_labels=missing_build,
                raw_key=build_rows[0][0],
                raw_value=" | ".join(f"{k}: {v}" for k, v in build_rows),
                product_title=title,
                sibling_context={},
                reason=f"unresolved_build_fields:{','.join(missing_build)}",
            ))

        return build, envelopes

    def extract_audio_webcam(
        self,
        raw_specs: dict[str, Any],
        title: str,
    ) -> tuple[dict[str, Any], dict[str, Any], list[ContextEnvelope]]:
        """Extract audio tech, microphones, and camera specifications."""
        envelopes: list[ContextEnvelope] = []
        audio: dict[str, Any] = {"speaker_count": None, "microphone": None}
        webcam: dict[str, Any] = {"resolution": None}

        for raw_k, raw_v in raw_specs.items():
            if not raw_v:
                continue
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            role = self.AUDIO_WEBCAM_KEYWORDS.get(k_clean) or self.AUDIO_WEBCAM_KEYWORDS.get(k_norm)
            v_str = str(raw_v).strip()

            if role == "webcam" and not webcam["resolution"]:
                webcam["resolution"] = v_str
            elif role in ("microphone", "built_in_devices") and not audio["microphone"]:
                if re.search(r"\bmicrophone|mic\b", v_str, re.I):
                    audio["microphone"] = "Built-in Microphone"
                elif role == "microphone":
                    audio["microphone"] = v_str

            if role in ("speakers", "built_in_devices") and audio["speaker_count"] is None:
                m_sp = re.search(r"(\d+)\s*(?:x\s*\d+W|speakers?)", v_str, re.I)
                if m_sp:
                    audio["speaker_count"] = int(m_sp.group(1))
                elif re.search(r"\b(?:dual|two|2x)\b", v_str, re.I):
                    audio["speaker_count"] = 2
                elif re.search(r"\b(?:quad|four|4x)\b", v_str, re.I):
                    audio["speaker_count"] = 4

        if audio["speaker_count"] is None:
            for k, v in raw_specs.items():
                if v and any(w in k.lower() for w in ["audio", "sound", "speaker"]):
                    v_s = str(v)
                    m_sp = re.search(r"(\d+)\s*(?:x\s*\d+W|speakers?)", v_s, re.I)
                    if m_sp:
                        audio["speaker_count"] = int(m_sp.group(1))
                        break
                    elif re.search(r"\b(?:dual|two|2x)\b", v_s, re.I):
                        audio["speaker_count"] = 2
                        break
                    elif re.search(r"\b(?:quad|four|4x)\b", v_s, re.I):
                        audio["speaker_count"] = 4
                        break

        missing_audio = []
        if not webcam["resolution"]:
            missing_audio.append("webcam resolution")
        if not audio["microphone"]:
            missing_audio.append("microphone")
        if audio["speaker_count"] is None:
            missing_audio.append("speaker count")

        audio_rows = [(k, str(v)) for k, v in raw_specs.items() if self.AUDIO_WEBCAM_KEYWORDS.get(k.strip().lower()) or self.AUDIO_WEBCAM_KEYWORDS.get(self._normalize_key(k))]
        if missing_audio and audio_rows:
            envelopes.append(ContextEnvelope(
                target_area="audio_webcam",
                target_labels=missing_audio,
                raw_key=audio_rows[0][0],
                raw_value=" | ".join(f"{k}: {v}" for k, v in audio_rows),
                product_title=title,
                sibling_context={},
                reason=f"unresolved_audio_fields:{','.join(missing_audio)}",
            ))

        return audio, webcam, envelopes

    # -------------------------------------------------------------------------
    # LAYER 2: PHYSICAL HARDWARE SANITY GATE
    # -------------------------------------------------------------------------

    VALID_CPU_CORES = {2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 32}
    VALID_CPU_THREADS = {2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 48}
    VALID_VRAM_GB = {1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24}
    VALID_RAM_CAPACITIES = {4, 6, 8, 12, 16, 20, 24, 32, 48, 64, 96, 128, 192, 256}
    VALID_RAM_TYPES = {"DDR3", "DDR4", "DDR5", "LPDDR4", "LPDDR4X", "LPDDR5", "LPDDR5X"}
    VALID_STORAGE_MIN_GB = 64
    VALID_DISPLAY_SIZES = (10.0, 18.5)
    VALID_REFRESH_RATES = {60, 90, 120, 144, 165, 180, 240, 300, 360, 480}

    def apply_sanity_gate(
        self,
        structured: dict[str, Any],
        envelopes: list[ContextEnvelope],
        clean_specs: dict[str, Any],
        title: str,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Layer 2: Physical Hardware Sanity Gate.
        
        Validates parsed fields against physical hardware contracts.
        Any physically impossible value is discarded to None and triggers a micro-envelope.
        """
        # 1. GPU VRAM Validation
        gpu = structured.get("gpu", {})
        if gpu.get("vram_gb") is not None:
            if gpu["vram_gb"] not in self.VALID_VRAM_GB:
                gpu["vram_gb"] = None
                gpu_rows = [f"{k}: {v}" for k, v in clean_specs.items() if any(w in k.lower() for w in ["graphic", "gpu", "vga", "video"])]
                envelopes.append(ContextEnvelope(
                    target_area="gpu",
                    target_labels=["graphics vram"],
                    raw_key="Graphics",
                    raw_value=" | ".join(gpu_rows) if gpu_rows else title,
                    product_title=title,
                    sibling_context={"gpu_model": gpu.get("model")},
                    reason="sanity_invalid_vram",
                ))

        # 2. CPU Cores Validation
        cpu = structured.get("cpu", {})
        if cpu.get("cores") is not None:
            if cpu["cores"] not in self.VALID_CPU_CORES:
                cpu["cores"] = None
                cpu_rows = [f"{k}: {v}" for k, v in clean_specs.items() if any(w in k.lower() for w in ["processor", "cpu", "chip", "cache"])]
                envelopes.append(ContextEnvelope(
                    target_area="cpu",
                    target_labels=["cpu core count"],
                    raw_key="Processor",
                    raw_value=" | ".join(cpu_rows) if cpu_rows else title,
                    product_title=title,
                    sibling_context={"cpu_model": cpu.get("model")},
                    reason="sanity_invalid_cores",
                ))

        # 3. CPU Threads Validation
        if cpu.get("threads") is not None:
            if cpu["threads"] not in self.VALID_CPU_THREADS:
                cpu["threads"] = None
                cpu_rows = [f"{k}: {v}" for k, v in clean_specs.items() if any(w in k.lower() for w in ["processor", "cpu", "chip", "cache"])]
                envelopes.append(ContextEnvelope(
                    target_area="cpu",
                    target_labels=["cpu thread count"],
                    raw_key="Processor",
                    raw_value=" | ".join(cpu_rows) if cpu_rows else title,
                    product_title=title,
                    sibling_context={"cpu_model": cpu.get("model")},
                    reason="sanity_invalid_threads",
                ))

        # 4. Memory Validation
        mem = structured.get("memory", {})
        if mem.get("capacity_gb") is not None:
            if mem["capacity_gb"] not in self.VALID_RAM_CAPACITIES:
                mem["capacity_gb"] = None
                mem_rows = [f"{k}: {v}" for k, v in clean_specs.items() if any(w in k.lower() for w in ["memory", "ram"])]
                envelopes.append(ContextEnvelope(
                    target_area="memory",
                    target_labels=["ram capacity"],
                    raw_key="Memory",
                    raw_value=" | ".join(mem_rows) if mem_rows else title,
                    product_title=title,
                    sibling_context={},
                    reason="sanity_invalid_ram_capacity",
                ))
        if mem.get("memory_type"):
            m_matched_type = None
            for t in sorted(self.VALID_RAM_TYPES, key=len, reverse=True):
                if re.search(rf"\b{re.escape(t)}\b", mem["memory_type"], re.I):
                    m_matched_type = t
                    break
            mem["memory_type"] = m_matched_type

        # 5. Storage Validation
        st = structured.get("storage", {})
        if st.get("capacity_gb") is not None:
            if st["capacity_gb"] < self.VALID_STORAGE_MIN_GB:
                st["capacity_gb"] = None
                st_rows = [f"{k}: {v}" for k, v in clean_specs.items() if any(w in k.lower() for w in ["storage", "hard disk", "ssd", "drive"])]
                envelopes.append(ContextEnvelope(
                    target_area="storage",
                    target_labels=["storage capacity"],
                    raw_key="Storage",
                    raw_value=" | ".join(st_rows) if st_rows else title,
                    product_title=title,
                    sibling_context={},
                    reason="sanity_invalid_storage_capacity",
                ))

        if st.get("form_factor"):
            if re.search(r"\b(?:DDR|RAM|GDDR)\b", st["form_factor"], re.I) or not any(x in st["form_factor"].upper() for x in ["M.2", "2.5", "PCIE", "NVME"]):
                st["form_factor"] = None

        # 6. Display Screen Size Validation
        disp = structured.get("display", {})
        if disp.get("size_inches") is not None:
            if not (self.VALID_DISPLAY_SIZES[0] <= disp["size_inches"] <= self.VALID_DISPLAY_SIZES[1]):
                disp["size_inches"] = None

        if disp.get("refresh_rate_hz") is not None:
            if disp["refresh_rate_hz"] not in self.VALID_REFRESH_RATES:
                disp["refresh_rate_hz"] = None

        return structured, envelopes

    # -------------------------------------------------------------------------
    # MASTER EXTRACTOR ENTRYPOINT
    # -------------------------------------------------------------------------

    def extract(
        self,
        raw_specs: dict[str, Any],
        title: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[ContextEnvelope]]:
        """Execute full extraction workflow across all modular spec areas.

        Returns:
            Tuple of:
            - structured: Populated dictionary matching catalog-service database schema.
            - envelopes: List of ContextEnvelope items requiring contextual GLiNER extraction.
        """
        # Layer 0: Text Sanitizer (strip invisible Unicode direction marks, zero-width chars, non-breaking spaces)
        clean_specs: dict[str, Any] = {}
        for k, v in raw_specs.items():
            k_clean = re.sub(r"[\u200e\u200f\u200b\xa0]", " ", str(k)).strip()
            v_clean = re.sub(r"[\u200e\u200f\u200b\xa0]", " ", str(v)).strip() if v is not None else v
            clean_specs[k_clean] = v_clean
        clean_title = re.sub(r"[\u200e\u200f\u200b\xa0]", " ", title).strip() if title else ""

        all_envelopes: list[ContextEnvelope] = []

        # 1. Identity & Brand
        ident, env_ident = self.extract_identity(clean_specs, clean_title, metadata)
        all_envelopes.extend(env_ident)

        # 2. CPU / Processor
        cpu, env_cpu = self.extract_cpu(clean_specs, clean_title)
        all_envelopes.extend(env_cpu)

        # 3. GPU / Graphics
        gpu, env_gpu = self.extract_gpu(clean_specs, clean_title, sibling_context={"cpu": cpu.get("full_name")})
        all_envelopes.extend(env_gpu)

        # 4. Memory / RAM
        mem, env_mem = self.extract_memory(clean_specs, clean_title, sibling_context={"gpu": gpu.get("model")})
        all_envelopes.extend(env_mem)

        # 5. Storage / SSD
        storage, env_storage = self.extract_storage(clean_specs, clean_title, sibling_context={"ram": mem.get("capacity_gb")})
        all_envelopes.extend(env_storage)

        # 6. Display / Screen
        display, env_disp = self.extract_display(clean_specs, clean_title)
        all_envelopes.extend(env_disp)

        # 7. Connectivity & Ports
        conn, env_conn = self.extract_connectivity(clean_specs, clean_title)
        all_envelopes.extend(env_conn)

        # 8. Power & Battery
        power, env_power = self.extract_power_battery(clean_specs, clean_title)
        all_envelopes.extend(env_power)

        # 9. Physical Chassis
        phys, env_phys = self.extract_physical(clean_specs, clean_title)
        all_envelopes.extend(env_phys)

        # 10. Operating System
        os_info, env_os = self.extract_operating_system(clean_specs, clean_title)
        all_envelopes.extend(env_os)

        # 11. Build & Security
        build, env_build = self.extract_build_security(clean_specs, clean_title)
        all_envelopes.extend(env_build)

        # 12. Audio & Webcam
        audio, webcam, env_audio = self.extract_audio_webcam(clean_specs, clean_title)
        all_envelopes.extend(env_audio)

        # 13. Unmapped Keys Catch-All Envelope
        all_known = (
            set(self.IDENTITY_KEYWORDS.keys())
            | set(self.CPU_KEYWORDS.keys())
            | set(self.GPU_KEYWORDS.keys())
            | set(self.RAM_KEYWORDS.keys())
            | set(self.STORAGE_KEYWORDS.keys())
            | set(self.DISPLAY_KEYWORDS.keys())
            | set(self.POWER_BATTERY_KEYWORDS.keys())
            | set(self.CONNECTIVITY_KEYWORDS.keys())
            | set(self.PHYSICAL_KEYWORDS.keys())
            | set(self.OS_KEYWORDS.keys())
            | set(self.BUILD_SECURITY_KEYWORDS.keys())
            | set(self.AUDIO_WEBCAM_KEYWORDS.keys())
            | self.IGNORED_METADATA_KEYWORDS
        )

        unmapped_rows = []
        for raw_k, raw_v in clean_specs.items():
            k_clean = raw_k.strip().lower()
            k_norm = self._normalize_key(raw_k)
            if k_clean not in all_known and k_norm not in all_known:
                unmapped_rows.append((raw_k, str(raw_v).strip()))

        if unmapped_rows:
            chunk_size = 2
            for i in range(0, min(len(unmapped_rows), 6), chunk_size):
                chunk = unmapped_rows[i:i + chunk_size]
                chunk_str = " | ".join(f"{k}: {v}" for k, v in chunk)
                all_envelopes.append(ContextEnvelope(
                    target_area="unmapped_specs",
                    target_labels=[
                        "ram capacity", "max ram capacity", "storage capacity", "storage interface",
                        "screen resolution", "refresh rate", "panel type", "aspect ratio",
                        "battery capacity wh", "power adapter wattage", "laptop weight", "laptop color",
                        "operating system name"
                    ],
                    raw_key=chunk[0][0],
                    raw_value=chunk_str,
                    product_title=clean_title,
                    sibling_context={},
                    reason="unmapped_specs_chunk",
                ))

        structured: dict[str, Any] = {
            "identity": ident,
            "cpu": cpu,
            "gpu": gpu,
            "memory": mem,
            "storage": storage,
            "display": display,
            "power_battery": power,
            "connectivity": conn,
            "operating_system": os_info,
            "physical": phys,
            "build": build,
            "audio": audio,
            "webcam": webcam,
        }

        # Layer 2: Hardware Physical Sanity Gate
        structured, all_envelopes = self.apply_sanity_gate(structured, all_envelopes, clean_specs, clean_title)

        return structured, all_envelopes
