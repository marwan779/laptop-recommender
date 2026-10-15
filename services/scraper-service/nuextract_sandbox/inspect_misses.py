"""Deep Miss Analysis Script: Compare extracted nulls against raw PDP DOM content."""

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATA_FILE = Path(__file__).resolve().parent / "output" / "compumarts_all_laptops_nuextract.json"

def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"Loaded {len(records)} records.\n")

    # 1. CPU Cores / Threads nulls
    print("=== 1. CPU CORES / THREADS NULLS ===")
    for r in records:
        cpu = r["structured"]["cpu"]
        if cpu.get("cores") is None or cpu.get("threads") is None:
            print(f"#{r['index']} {r['title']}")
            print(f"    Model: {cpu.get('model')}, Cores: {cpu.get('cores')}, Threads: {cpu.get('threads')}")
            print(f"    Raw PDP URL: {r['url']}")
            print()

    # 2. Display Resolution nulls
    print("=== 2. DISPLAY RESOLUTION NULLS ===")
    for r in records:
        disp = r["structured"]["display"]
        if disp.get("resolution") is None:
            print(f"#{r['index']} {r['title']}")
            print(f"    Size: {disp.get('size_inches')}, Res: {disp.get('resolution')}")
            print(f"    Raw PDP URL: {r['url']}")
            print()

    # 3. CPU Cache nulls: Check if cache was actually present in raw specs
    print("=== 3. CPU CACHE: CHECKING IF RAW PDP CONTAINED CACHE FOR NULLS ===")
    cache_miss_with_keyword = []
    for r in records:
        cpu = r["structured"]["cpu"]
        if cpu.get("cache_mb") is None:
            title = r.get("title", "")
            # Check if title or raw_description mentioned cache
            desc = r.get("raw_description", "")
            if "cache" in title.lower() or "cache" in desc.lower():
                cache_miss_with_keyword.append((r["index"], title, r["url"]))
    print(f"Laptops with null cache_mb where title/desc had 'cache': {len(cache_miss_with_keyword)}")
    for idx, t, u in cache_miss_with_keyword[:10]:
        print(f"  #{idx}: {t[:60]} -> {u}")

    # 4. Physical Dimensions & Weight nulls
    print("\n=== 4. PHYSICAL DIMENSIONS & WEIGHT NULLS ===")
    null_weight = [r for r in records if r["structured"]["physical"].get("weight_kg") is None]
    null_dims = [r for r in records if r["structured"]["physical"].get("height_mm") is None]
    print(f"Null weight_kg: {len(null_weight)} / {len(records)}")
    print(f"Null dimensions (height_mm): {len(null_dims)} / {len(records)}")

    # 5. Build & Security: has_fingerprint & backlit keyboard
    print("\n=== 5. BUILD & SECURITY NULLS ===")
    null_fp = [r for r in records if r["structured"]["build"].get("has_fingerprint") is None]
    null_backlit = [r for r in records if r["structured"]["build"].get("has_backlit_keyboard") is None]
    print(f"Null has_fingerprint: {len(null_fp)} / {len(records)}")
    print(f"Null has_backlit_keyboard: {len(null_backlit)} / {len(records)}")

    # 6. Audio & Webcam
    print("\n=== 6. AUDIO & WEBCAM NULLS ===")
    null_mic = [r for r in records if not r["structured"]["audio"].get("microphone")]
    null_cam = [r for r in records if not r["structured"]["webcam"].get("resolution")]
    null_spk = [r for r in records if r["structured"]["audio"].get("speaker_count") is None]
    print(f"Null microphone: {len(null_mic)} / {len(records)}")
    print(f"Null webcam.resolution: {len(null_cam)} / {len(records)}")
    print(f"Null speaker_count: {len(null_spk)} / {len(records)}")

if __name__ == "__main__":
    main()
