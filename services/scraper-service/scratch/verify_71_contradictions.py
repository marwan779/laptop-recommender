import json
import re

with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Define the user's exact 71 confirmed contradictions:
# List of (record_idx, field_path, check_fn, description)
CHECKS = [
    # Record 0
    (0, "specs.audio_webcam.webcam_resolution", lambda s, r: s.get("audio_webcam", {}).get("webcam_resolution") == "720p" and "Full HD" in r.get("audio_webcam", {}).get("raw_spec", ""), "Stored 720p vs Full HD"),
    # Record 3
    (3, "specs.audio_webcam.webcam_resolution", lambda s, r: s.get("audio_webcam", {}).get("webcam_resolution") == "720p" and "Full HD" in r.get("audio_webcam", {}).get("raw_spec", ""), "Stored 720p vs Full HD"),
    (3, "specs.build_security.has_backlit_keyboard", lambda s, r: s.get("build_security", {}).get("has_backlit_keyboard") is False and "Backlight: Yes" in r.get("build_security", {}).get("raw_spec", ""), "Stored false vs Backlight Yes"),
    (3, "specs.identity.laptop_model", lambda s, r: "WIFI" in str(s.get("identity", {}).get("laptop_model", "")), "Stored WiFi model instead of Aspire Go 16"),
    (3, "specs.identity.manufacturer_part_number", lambda s, r: str(s.get("identity", {}).get("manufacturer_part_number", "")).endswith(".007") and ".006" in r.get("identity", {}).get("raw_spec", ""), "Stored .007 vs raw .006"),
    (3, "specs.operating_system.name", lambda s, r: s.get("operating_system", {}).get("name") == "FreeDOS" and "No operating system" in r.get("operating_system", {}).get("raw_spec", ""), "Stored FreeDOS vs No OS"),
    # Record 4
    (4, "specs.build_security.has_backlit_keyboard", lambda s, r: s.get("build_security", {}).get("has_backlit_keyboard") is False and "Backlight: Yes" in r.get("build_security", {}).get("raw_spec", ""), "Stored false vs Backlight Yes"),
    # Record 5
    (5, "specs.build_security.has_backlit_keyboard", lambda s, r: s.get("build_security", {}).get("has_backlit_keyboard") is False and "Backlight: Yes" in r.get("build_security", {}).get("raw_spec", ""), "Stored false vs Backlight Yes"),
    (5, "specs.identity.laptop_model", lambda s, r: "Killer" in str(s.get("identity", {}).get("laptop_model", "")), "Stored Killer Wi-Fi model"),
    # Record 6
    (6, "specs.identity.manufacturer_part_number", lambda s, r: s.get("identity", {}).get("manufacturer_part_number") == "83DV01HRPS" and "Part Number: 198154823109" in r.get("identity", {}).get("raw_spec", ""), "Stored 83DV01HRPS vs raw Part Number 198154823109"),
    # Record 7
    (7, "specs.cpu.clock_boost_ghz", lambda s, r: s.get("cpu", {}).get("clock_boost_ghz") == 4.55 and "4.5 GHz" in r.get("cpu", {}).get("raw_spec", ""), "Stored 4.55 vs raw 4.5 GHz"),
    (7, "specs.memory.slot_count", lambda s, r: s.get("memory", {}).get("slot_count") == 1 and "2 SODIMM" in r.get("memory", {}).get("raw_spec", ""), "Stored 1 slot vs raw 2 SODIMM"),
    # Record 8
    (8, "specs.physical.weight_kg", lambda s, r: s.get("physical", {}).get("weight_kg") == 2.44 and "Device Weight, kg: 1.52" in r.get("physical", {}).get("raw_spec", ""), "Stored 2.44 vs raw 1.52"),
    # Record 9
    (9, "specs.operating_system.name", lambda s, r: s.get("operating_system", {}).get("name") == "FreeDOS" and "DOS / No Preloaded" in r.get("operating_system", {}).get("raw_spec", ""), "Stored FreeDOS vs raw DOS/No Preloaded"),
    # Record 14
    (14, "specs.operating_system.name", lambda s, r: s.get("operating_system", {}).get("name") == "FreeDOS" and "DOS / No Preinstalled" in r.get("operating_system", {}).get("raw_spec", ""), "Stored FreeDOS vs raw DOS/No Preinstalled"),
    # Record 18
    (18, "specs.storage.slot_count", lambda s, r: s.get("storage", {}).get("slot_count") == 4 and "One M.2" in r.get("storage", {}).get("raw_spec", ""), "Stored 4 vs raw One M.2"),
    # Record 19
    (19, "specs.storage.slot_count", lambda s, r: s.get("storage", {}).get("slot_count") == 1 and "1 × M.2 NVMe PCIe Gen4 Slot and 1 × M.2 NVMe PCIe Gen5" in r.get("storage", {}).get("raw_spec", ""), "Stored 1 vs raw 2 slots"),
    # Record 22
    (22, "specs.identity.warranty", lambda s, r: "Dropbox" in str(s.get("identity", {}).get("warranty", "")), "Stored Dropbox as warranty"),
    # Record 24
    (24, "specs.build_security.has_backlit_keyboard", lambda s, r: s.get("build_security", {}).get("has_backlit_keyboard") is True and "Non-Backlit" in r.get("build_security", {}).get("raw_spec", ""), "Stored true vs Non-Backlit"),
    (24, "specs.build_security.keyboard_backlight_type", lambda s, r: s.get("build_security", {}).get("keyboard_backlight_type") == "Backlit" and "Non-Backlit" in r.get("build_security", {}).get("raw_spec", ""), "Stored Backlit vs Non-Backlit"),
    # Record 27
    (27, "specs.audio_webcam.speaker_count", lambda s, r: s.get("audio_webcam", {}).get("speaker_count") == 2 and "4 stereo speakers" in r.get("audio_webcam", {}).get("raw_spec", ""), "Stored 2 vs raw 4 stereo speakers"),
    # Record 28
    (28, "specs.build_security.has_fingerprint", lambda s, r: s.get("build_security", {}).get("has_fingerprint") is False and "FingerPrint: Available" in r.get("build_security", {}).get("raw_spec", ""), "Stored false vs FingerPrint Available"),
    (28, "specs.storage.slot_count", lambda s, r: s.get("storage", {}).get("slot_count") == 2 and "supports only one M.2" in r.get("storage", {}).get("raw_spec", ""), "Stored 2 vs raw supports only one"),
    # Record 39
    (39, "specs.identity.laptop_model", lambda s, r: "Killer" in str(s.get("identity", {}).get("laptop_model", "")), "Stored Killer Wi-Fi model"),
    # Record 40
    (40, "specs.identity.laptop_model", lambda s, r: "Killer" in str(s.get("identity", {}).get("laptop_model", "")), "Stored Killer Wi-Fi model"),
    (40, "specs.operating_system.name", lambda s, r: s.get("operating_system", {}).get("name") == "FreeDOS" and "No OS / Acer EShell" in r.get("operating_system", {}).get("raw_spec", ""), "Stored FreeDOS vs No OS"),
    # Record 47
    (47, "specs.audio_webcam.speaker_count", lambda s, r: s.get("audio_webcam", {}).get("speaker_count") == 2 and "4 stereo speakers" in r.get("audio_webcam", {}).get("raw_spec", ""), "Stored 2 vs raw 4 stereo speakers"),
    (47, "specs.identity.is_bundle", lambda s, r: s.get("identity", {}).get("is_bundle") is False and "Bundled Accessories:" in r.get("identity", {}).get("raw_spec", ""), "Stored is_bundle=false vs Bundled Accessories"),
    # Record 53
    (53, "specs.memory.is_soldered", lambda s, r: s.get("memory", {}).get("is_soldered") is False and "8GB DDR5 on board" in r.get("memory", {}).get("raw_spec", ""), "Stored false vs on board memory"),
    # Record 55
    (55, "specs.cpu.cache_mb", lambda s, r: s.get("cpu", {}).get("cache_mb") == 8 and "14MB Cache" in r.get("cpu", {}).get("raw_spec", ""), "Stored 8MB vs raw 14MB Cache"),
    # Record 56
    (56, "specs.cpu.cache_mb", lambda s, r: s.get("cpu", {}).get("cache_mb") == 8 and "12MB Cache" in r.get("cpu", {}).get("raw_spec", ""), "Stored 8MB vs raw 12MB Cache"),
    (56, "specs.memory.is_soldered", lambda s, r: s.get("memory", {}).get("is_soldered") is False and "16GB DDR5 on board" in r.get("memory", {}).get("raw_spec", ""), "Stored false vs on board memory"),
    # Record 60
    (60, "specs.operating_system.name", lambda s, r: s.get("operating_system", {}).get("name") == "FreeDOS" and "No OS" in r.get("operating_system", {}).get("raw_spec", ""), "Stored FreeDOS vs No OS"),
    # Record 62
    (62, "specs.cpu.cache_mb", lambda s, r: s.get("cpu", {}).get("cache_mb") == 16 and "Cache: 20 MB" in r.get("cpu", {}).get("raw_spec", ""), "Stored 16MB vs raw 20 MB"),
    # Record 64
    (64, "specs.build_security.has_backlit_keyboard", lambda s, r: s.get("build_security", {}).get("has_backlit_keyboard") is False and "Keyboard Backlight: Yes" in r.get("build_security", {}).get("raw_spec", ""), "Stored false vs Backlight Yes"),
    # Record 69
    (69, "specs.build_security.has_backlit_keyboard", lambda s, r: s.get("build_security", {}).get("has_backlit_keyboard") is True and "Non-backlit" in r.get("build_security", {}).get("raw_spec", ""), "Stored true vs Non-backlit"),
    (69, "specs.build_security.keyboard_backlight_type", lambda s, r: s.get("build_security", {}).get("keyboard_backlight_type") == "Backlit" and "Non-backlit" in r.get("build_security", {}).get("raw_spec", ""), "Stored Backlit vs Non-backlit"),
    (69, "specs.identity.is_bundle", lambda s, r: s.get("identity", {}).get("is_bundle") is False and "Bundled Accessories:" in r.get("identity", {}).get("raw_spec", ""), "Stored is_bundle=false vs Bundled Accessories"),
    (69, "specs.memory.capacity_gb", lambda s, r: s.get("memory", {}).get("capacity_gb") == 8 and "8GB Soldered DDR5-4800 + 8GB SODIMM" in r.get("memory", {}).get("raw_spec", ""), "Stored 8GB vs raw 8GB+8GB"),
    (69, "specs.memory.slot_count", lambda s, r: s.get("memory", {}).get("slot_count") == 0 and "one DDR5 SODIMM slot" in r.get("memory", {}).get("raw_spec", ""), "Stored 0 slots vs raw one SODIMM slot"),
    # Record 70
    (70, "specs.memory.capacity_gb", lambda s, r: s.get("memory", {}).get("capacity_gb") == 8 and "8GB DDR4 onboard + 8GB DDR4 SO-DIMM" in r.get("memory", {}).get("raw_spec", ""), "Stored 8GB vs raw 8GB+8GB"),
    # Record 71
    (71, "specs.build_security.has_backlit_keyboard", lambda s, r: s.get("build_security", {}).get("has_backlit_keyboard") is False and "Amber Backlight" in r.get("build_security", {}).get("raw_spec", ""), "Stored false vs Amber Backlight"),
    # Record 72
    (72, "specs.cpu.clock_boost_ghz", lambda s, r: s.get("cpu", {}).get("clock_boost_ghz") == 5.1 and "Up to 4.8 GHz" in r.get("cpu", {}).get("raw_spec", ""), "Stored 5.1 vs raw Up to 4.8 GHz"),
    (72, "specs.cpu.performance_cores.boost_clock_ghz", lambda s, r: s.get("cpu", {}).get("performance_cores", {}).get("boost_clock_ghz") == 5.1 and "Up to 4.8 GHz" in r.get("cpu", {}).get("raw_spec", ""), "Stored 5.1 vs raw Up to 4.8 GHz"),
    # Record 74
    (74, "specs.cpu.clock_boost_ghz", lambda s, r: s.get("cpu", {}).get("clock_boost_ghz") == 5.8 and "Up to 5.40 GHz" in r.get("cpu", {}).get("raw_spec", ""), "Stored 5.8 vs raw Up to 5.40 GHz"),
    (74, "specs.cpu.performance_cores.boost_clock_ghz", lambda s, r: s.get("cpu", {}).get("performance_cores", {}).get("boost_clock_ghz") == 5.8 and "Up to 5.40 GHz" in r.get("cpu", {}).get("raw_spec", ""), "Stored 5.8 vs raw Up to 5.40 GHz"),
    # Record 75
    (75, "specs.cpu.clock_boost_ghz", lambda s, r: s.get("cpu", {}).get("clock_boost_ghz") == 5.8 and "Up to 5.40 GHz" in r.get("cpu", {}).get("raw_spec", ""), "Stored 5.8 vs raw Up to 5.40 GHz"),
    (75, "specs.cpu.performance_cores.boost_clock_ghz", lambda s, r: s.get("cpu", {}).get("performance_cores", {}).get("boost_clock_ghz") == 5.8 and "Up to 5.40 GHz" in r.get("cpu", {}).get("raw_spec", ""), "Stored 5.8 vs raw Up to 5.40 GHz"),
    # Record 76
    (76, "specs.build_security.has_backlit_keyboard", lambda s, r: s.get("build_security", {}).get("has_backlit_keyboard") is True and "Non-backlit" in r.get("build_security", {}).get("raw_spec", ""), "Stored true vs Non-backlit"),
    (76, "specs.build_security.keyboard_backlight_type", lambda s, r: s.get("build_security", {}).get("keyboard_backlight_type") == "Backlit" and "Non-backlit" in r.get("build_security", {}).get("raw_spec", ""), "Stored Backlit vs Non-backlit"),
    # Record 78
    (78, "specs.cpu.cache_mb", lambda s, r: s.get("cpu", {}).get("cache_mb") == 36 and "80MB Cache" in r.get("cpu", {}).get("raw_spec", ""), "Stored 36 vs raw 80MB"),
    (78, "specs.cpu.clock_boost_ghz", lambda s, r: s.get("cpu", {}).get("clock_boost_ghz") == 5.4 and "5.3GHz" in r.get("cpu", {}).get("raw_spec", ""), "Stored 5.4 vs raw 5.3GHz"),
    (78, "specs.cpu.cores", lambda s, r: s.get("cpu", {}).get("cores") == 24 and "16 Cores" in r.get("cpu", {}).get("raw_spec", ""), "Stored 24 vs raw 16 Cores"),
    (78, "specs.cpu.full_name", lambda s, r: "Intel" in str(s.get("cpu", {}).get("full_name", "")) and "AMD" in r.get("cpu", {}).get("raw_spec", ""), "Stored Intel full_name vs AMD"),
    (78, "specs.cpu.line", lambda s, r: "Core Ultra" in str(s.get("cpu", {}).get("line", "")) and "Ryzen 9" in r.get("cpu", {}).get("raw_spec", ""), "Stored Core Ultra vs Ryzen 9"),
    (78, "specs.cpu.manufacturer", lambda s, r: s.get("cpu", {}).get("manufacturer") == "Intel" and "AMD" in r.get("cpu", {}).get("raw_spec", ""), "Stored Intel vs AMD"),
    (78, "specs.cpu.model", lambda s, r: "Core Ultra" in str(s.get("cpu", {}).get("model", "")) and "Ryzen" in r.get("cpu", {}).get("raw_spec", ""), "Stored Core Ultra vs Ryzen"),
    (78, "specs.cpu.performance_cores.boost_clock_ghz", lambda s, r: (s.get("cpu", {}).get("performance_cores") or {}).get("boost_clock_ghz") == 5.4 and "5.3GHz" in r.get("cpu", {}).get("raw_spec", ""), "Stored 5.4 vs 5.3GHz"),
    (78, "specs.cpu.threads", lambda s, r: s.get("cpu", {}).get("threads") == 24 and "32 Threads" in r.get("cpu", {}).get("raw_spec", ""), "Stored 24 threads vs 32 Threads"),
    # Record 80
    (80, "specs.identity.is_bundle", lambda s, r: s.get("identity", {}).get("is_bundle") is False and "Bundle" in r.get("identity", {}).get("raw_spec", ""), "Stored false vs Bundle"),
    # Record 82
    (82, "specs.build_security.has_backlit_keyboard", lambda s, r: s.get("build_security", {}).get("has_backlit_keyboard") is True and "Non-backlit" in r.get("build_security", {}).get("raw_spec", ""), "Stored true vs Non-backlit"),
    (82, "specs.build_security.keyboard_backlight_type", lambda s, r: s.get("build_security", {}).get("keyboard_backlight_type") == "Backlit" and "Non-backlit" in r.get("build_security", {}).get("raw_spec", ""), "Stored Backlit vs Non-backlit"),
    # Record 84
    (84, "specs.audio_webcam.webcam_resolution", lambda s, r: s.get("audio_webcam", {}).get("webcam_resolution") == "720p" and "Full HD" in r.get("audio_webcam", {}).get("raw_spec", ""), "Stored 720p vs Full HD"),
    # Record 92
    (92, "specs.audio_webcam.webcam_resolution", lambda s, r: s.get("audio_webcam", {}).get("webcam_resolution") == "720p" and "Full HD" in r.get("audio_webcam", {}).get("raw_spec", ""), "Stored 720p vs Full HD"),
    # Record 95
    (95, "specs.identity.is_bundle", lambda s, r: s.get("identity", {}).get("is_bundle") is False and "Bundle" in r.get("identity", {}).get("raw_spec", ""), "Stored false vs Bundle"),
    # Record 99
    (99, "specs.cpu.cache_mb", lambda s, r: s.get("cpu", {}).get("cache_mb") == 16 and "22MB Cache" in r.get("cpu", {}).get("raw_spec", ""), "Stored 16 vs raw 22MB"),
    # Record 111
    (111, "specs.storage.capacity_gb", lambda s, r: s.get("storage", {}).get("capacity_gb") == 4096 and "1TB" in r.get("storage", {}).get("raw_spec", ""), "Stored 4096 vs raw 1TB"),
    # Record 114
    (114, "specs.identity.is_bundle", lambda s, r: s.get("identity", {}).get("is_bundle") is False and "Bundled Accessories:" in r.get("identity", {}).get("raw_spec", ""), "Stored false vs Bundled Accessories"),
    # Record 118
    (118, "specs.identity.is_bundle", lambda s, r: s.get("identity", {}).get("is_bundle") is False and "Bundled Accessories:" in r.get("identity", {}).get("raw_spec", ""), "Stored false vs Bundled Accessories"),
    # Record 120
    (120, "specs.storage.storage_type", lambda s, r: s.get("storage", {}).get("storage_type") == "SSD" and "HDD" in r.get("storage", {}).get("raw_spec", ""), "Stored SSD vs raw HDD"),
    # Record 122
    (122, "specs.storage.slot_count", lambda s, r: s.get("storage", {}).get("slot_count") == 1 and "extra M.2 slot" in r.get("storage", {}).get("raw_spec", ""), "Stored 1 vs extra M.2 slot"),
]

print(f"Total check definitions: {len(CHECKS)}")

detected = 0
for idx, field, test_fn, desc in CHECKS:
    rec = data[idx]
    specs = rec.get("specs", {})
    if test_fn(specs, specs):
        detected += 1
        print(f"[{idx}] {field}: {desc} -> CONFIRMED CONTRADICTION")

print(f"\nTotal Confirmed Contradictions in current pipeline_results: {detected} / {len(CHECKS)}")
