"""Empirical Evaluation of GLiNER ONNX on Unstructured Semantic Fields:
1. connectivity.ports
2. audio_webcam (speaker_count, microphone, webcam_resolution)
3. build_security (has_backlit_keyboard, has_fingerprint, pointing_device, security_features)
4. physical.dimensions (width_mm, depth_mm, height_mm)

Tests zero-shot NER extraction capabilities, entity span detection, confidence scores,
and determines what post-processing/limitations exist.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List

# Add scraper-service root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gliner import GLiNER

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("gliner_benchmark")

# ---------------------------------------------------------
# 1. Representative Real PDP Samples from CompuMarts & Retailers
# ---------------------------------------------------------

PORT_SAMPLES = [
    {
        "laptop": "Lenovo LOQ 15IRX9",
        "text": "1x Slim tip (rectangle) power connector; 3x USB-A (USB 5Gbps / USB 3.2 Gen 1); 1x USB-C® (USB 10Gbps / USB 3.2 Gen 2), with USB PD 65-100W and DisplayPort™ 1.4; 1x HDMI® 2.1, up to 8K/60Hz; 1x Headphone / microphone combo jack (3.5mm); 1x Ethernet (RJ-45)",
    },
    {
        "laptop": "MSI Katana 15 HX B14WGK",
        "text": "1x Type-C (USB3.2 Gen2 / DisplayPort / Power Delivery 3.0), 3x Type-A USB3.2 Gen2, 1x HDMI 2.1 (8K@60Hz / 4K@120Hz), 1x Mic-in/Headphone-out Combo Jack, 1x RJ45 LAN Port",
    },
    {
        "laptop": "HP Victus 16",
        "text": "1 USB Type-C 5Gbps signaling rate (DisplayPort 1.4, HP Sleep and Charge); 1 USB Type-A 5Gbps signaling rate (HP Sleep and Charge); 2 USB Type-A 5Gbps signaling rate; 1 AC smart pin; 1 HDMI 2.1; 1 headphone/microphone combo; 1 RJ-45",
    },
    {
        "laptop": "MSI Cyborg 15",
        "text": "1× RJ45, 1× USB-C 3.2 Gen2 (DisplayPort & Power Delivery 3.0), 1× USB-A 3.2 Gen1, 2× USB-A 3.2 Gen2, 1× HDMI 2.1 (4K@60Hz)",
    },
    {
        "laptop": "Dell Alienware m16 R2",
        "text": "1 Type-C (Thunderbolt 4 / USB4 / 15W Power Delivery / DisplayPort 1.4), 1 USB 3.2 Gen 2 Type-C (DisplayPort 1.4, Power Delivery 15W), 1 USB 3.2 Gen 1 Type-A with PowerShare, 1 USB 3.2 Gen 1 Type-A, 1 HDMI 2.1, 1 Global Headset Jack, 1 RJ-45 Ethernet, 1 MicroSD Card Reader",
    },
]

AUDIO_WEBCAM_SAMPLES = [
    {
        "laptop": "Lenovo LOQ 15IRX9",
        "text": "Speakers: Stereo speakers, 2W x2, optimized with Nahimic Audio. Microphone: 2x, Array. Camera: HD 720p with E-shutter",
    },
    {
        "laptop": "HP Victus 16",
        "text": "HP True Vision 1080p FHD camera with temporal noise reduction and integrated dual array digital microphones; Audio: DTS:X Ultra; Dual speakers; HP Audio Boost; HyperX",
    },
    {
        "laptop": "MSI Cyborg 15",
        "text": "Audio: 2×2W Speakers, Array Microphone. Audio Jack: 1× Mic-in/Headphone-out Combo Jack. Webcam: HD (720p, 30fps) with 3D Noise Reduction (3DNR)",
    },
    {
        "laptop": "ASUS ROG Zephyrus G16",
        "text": "Audio: 4-speaker (dual-force woofer) system with Smart Amplifier Technology, 2 Tweeters, Dolby Atmos. Mic: Built-in 3-microphone array. Camera: 1080P FHD IR Camera for Windows Hello",
    },
    {
        "laptop": "Dell XPS 13",
        "text": "Webcam: 1080p at 30 fps FHD RGB-Ir camera, dual-array microphones. Speakers: Quad-speaker design with 2W woofer x 2 and 2W tweeter x 2, total 8W",
    },
]

BUILD_SECURITY_SAMPLES = [
    {
        "laptop": "Lenovo LOQ 15IRX9",
        "text": "Keyboard: White Backlit, English (UK). Touchpad: Buttonless Mylar surface multi-touch touchpad, supports Precision TouchPad (PTP), 75 x 120 mm. Security Chip: Firmware TPM 2.0 Enabled. Fingerprint Reader: No Fingerprint Reader. Other Security: E-shutter",
    },
    {
        "laptop": "HP Victus 16",
        "text": "Full-size, 1-zone RGB backlit, moonstone grey keyboard with numeric keypad; HP Imagepad; Security: Trusted Platform Module (Firmware TPM) support, Camera privacy shutter",
    },
    {
        "laptop": "MSI Katana 15",
        "text": "Keyboard: 4-Zone RGB Gaming Keyboard with Copilot Key. Touchpad: Multi-touch gesture touchpad. Security: Firmware TPM 2.0, Kensington Nano Security Slot",
    },
    {
        "laptop": "Lenovo ThinkPad E16",
        "text": "Keyboard: Backlit, Arabic/English with TrackPoint and 3+2 buttons Mylar surface multi-touch touchpad. Fingerprint Reader: Touch style, integrated in power button. Security: Discrete TPM 2.0, Kensington Nano Security Slot, Camera privacy shutter",
    },
    {
        "laptop": "Acer Swift Go 14",
        "text": "Backlit keyboard with multi-gesture OceanGlass Touchpad; Fingerprint reader on power key with Windows Hello certification; Kensington lock slot, Firmware TPM",
    },
]

DIMENSION_SAMPLES = [
    {
        "laptop": "Lenovo LOQ 15IRX9",
        "text": "Dimensions (WxDxH): 359.86 x 258.7 x 21.9-23.9 mm (14.17 x 10.19 x 0.86-0.94 inches)",
    },
    {
        "laptop": "MSI Katana 15",
        "text": "Dimensions and Weight: 359 x 262 x 25.5 mm, 2.4 kg",
    },
    {
        "laptop": "HP Victus 16",
        "text": "Dimensions (W x D x H): 36.9 x 25.94 x 2.29 cm (front); 36.9 x 25.94 x 2.39 cm (rear)",
    },
    {
        "laptop": "MSI Cyborg 15",
        "text": "Dimensions: 359 × 249 × 21–22.9 mm",
    },
    {
        "laptop": "Apple MacBook Pro 16",
        "text": "Height: 1.68 cm (0.66 inch), Width: 35.57 cm (14.01 inches), Depth: 24.81 cm (9.77 inches), Weight: 2.14 kg",
    },
    {
        "laptop": "Dell XPS 14",
        "text": "Height: 18.0 mm (0.71 in.), Width: 320.0 mm (12.60 in.), Depth: 216.0 mm (8.50 in.)",
    },
]


def test_category(
    category_name: str,
    samples: List[Dict[str, str]],
    model: GLiNER,
    label_sets: Dict[str, List[str]],
    threshold: float = 0.35,
) -> None:
    print("\n" + "=" * 80)
    print(f" CATEGORY: {category_name.upper()}")
    print("=" * 80)

    for prompt_strategy, labels in label_sets.items():
        print(f"\n--- Strategy: {prompt_strategy} ---")
        print(f"Target Labels: {labels} (threshold={threshold})")

        for item in samples:
            text = item["text"]
            laptop = item["laptop"]
            predictions = model.predict_entities(text, labels, threshold=threshold)

            print(f"\n[{laptop}]")
            print(f"Input: {text}")
            if not predictions:
                print("  -> (No entities detected)")
            else:
                for ent in predictions:
                    print(
                        f"  -> [{ent['label']}] '{ent['text']}' (score: {ent['score']:.3f}, span: {ent['start']}:{ent['end']})"
                    )


def main():
    checkpoint_dir = os.path.join(
        os.path.expanduser("~"),
        ".cache",
        "huggingface",
        "hub",
        "models--onnx-community--gliner_large-v2.1",
        "snapshots",
    )
    # Check if local checkpoint exists
    local_path = None
    if os.path.exists(checkpoint_dir):
        subdirs = [os.path.join(checkpoint_dir, d) for d in os.listdir(checkpoint_dir) if os.path.isdir(os.path.join(checkpoint_dir, d))]
        if subdirs:
            local_path = subdirs[0]

    model_target = local_path if local_path else "onnx-community/gliner_large-v2.1"
    print(f"Loading GLiNER ONNX from: {model_target}")

    model = GLiNER.from_pretrained(
        model_target,
        load_onnx_model=True,
        onnx_model_file="onnx/model_int8.onnx",
    )
    print("GLiNER ONNX Model Loaded Successfully!")

    # 1. Connectivity / Ports
    port_label_sets = {
        "Granular Port Types": [
            "usb-c port",
            "usb-a port",
            "hdmi port",
            "ethernet port",
            "audio jack",
            "power connector",
            "sd card reader",
        ],
        "Generic Port Entity": [
            "port",
            "connector",
            "jack",
        ],
        "Capabilities & Features": [
            "displayport",
            "power delivery",
            "thunderbolt",
            "port transfer speed",
        ],
    }
    test_category("Connectivity / Ports", PORT_SAMPLES, model, port_label_sets, threshold=0.30)

    # 2. Audio & Webcam
    audio_label_sets = {
        "Hardware Component Spans": [
            "webcam resolution",
            "camera",
            "speaker count",
            "speakers",
            "microphone",
            "audio technology",
        ],
        "Detailed Attributes": [
            "camera resolution",
            "speaker wattage",
            "microphone type",
            "privacy shutter",
            "dolby atmos",
        ],
    }
    test_category("Audio & Webcam", AUDIO_WEBCAM_SAMPLES, model, audio_label_sets, threshold=0.30)

    # 3. Build & Security
    build_label_sets = {
        "Hardware Specs": [
            "backlit keyboard",
            "keyboard backlight",
            "touchpad",
            "pointing device",
            "fingerprint reader",
            "security chip",
            "privacy shutter",
            "kensington lock slot",
        ],
        "High-level Categories": [
            "security feature",
            "biometric sensor",
            "pointing device",
            "keyboard feature",
        ],
    }
    test_category("Build & Security", BUILD_SECURITY_SAMPLES, model, build_label_sets, threshold=0.30)

    # 4. Physical Dimensions
    dimension_label_sets = {
        "Discrete Dimension Coordinates": [
            "width",
            "depth",
            "height",
            "thickness",
            "laptop dimensions",
        ],
        "Raw Measurement Spans": [
            "dimension string",
            "measurement in mm",
            "measurement in cm",
            "weight",
        ],
    }
    test_category("Physical Dimensions", DIMENSION_SAMPLES, model, dimension_label_sets, threshold=0.30)


if __name__ == "__main__":
    main()

