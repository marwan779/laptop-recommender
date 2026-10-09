"""Interactive Tester: Feed raw specs from my_raw_specs.json to local Ollama model.

Usage:
    # Test laptop #0 (default)
    python local_extractor/test_user_llm.py

    # Test laptop at a specific index (0 to 118)
    python local_extractor/test_user_llm.py --index 5
"""

import argparse
import json
import os
import sys
import time
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA_PATH = os.path.join(os.path.dirname(__file__), "my_raw_specs.json")


def main():
    parser = argparse.ArgumentParser(description="Test local LLM on raw specs from my_raw_specs.json")
    parser.add_argument("--index", type=int, default=0, help="Laptop index (0 to 118)")
    parser.add_argument("--model", type=str, default="qwen2.5:1.5b", help="Ollama model name")
    args = parser.parse_args()

    if not os.path.exists(DATA_PATH):
        print(f"File not found: {DATA_PATH}")
        return

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        laptops = json.load(f)

    if args.index < 0 or args.index >= len(laptops):
        print(f"Invalid index {args.index}. Valid range: 0 to {len(laptops)-1}")
        return

    laptop = laptops[args.index]
    title = laptop.get("title", "")
    raw_specs = laptop.get("specs", {})

    print("=" * 80)
    print(f"[*] TESTING LAPTOP [{args.index}/{len(laptops)-1}]: {title}")
    print(f"    Raw Table Fields Count: {len(raw_specs)}")
    print("=" * 80)

    # Format the prompt
    spec_lines = [f"{k}: {v}" for k, v in raw_specs.items()]
    specs_text = "\n".join(spec_lines[:30])  # Clean top 30 spec lines

    user_prompt = f"""Product Title: {title}

RAW SPECIFICATIONS:
{specs_text}

Task: Map and normalize these specifications into standard JSON keys:
{{
  "processor": "...",
  "graphics": "...",
  "ram": "...",
  "storage": "...",
  "display": "...",
  "battery": "...",
  "power_adapter": "...",
  "operating_system": "...",
  "ports": "..."
}}
Output pure JSON only."""

    print("\n--- PROMPT SENT TO MODEL ---")
    print(user_prompt[:500] + "\n... [truncated for display]")

    print(f"\n[...] Sending to Ollama ({args.model})...")
    start = time.perf_counter()

    try:
        payload = {
            "model": args.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a hardware spec normalizer. Extract specs into standardized JSON.",
                },
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }

        with httpx.Client(timeout=60.0) as client:
            res = client.post("http://localhost:11434/api/chat", json=payload)
            latency = time.perf_counter() - start

            if res.status_code == 200:
                data = res.json()
                content = data.get("message", {}).get("content", "")
                print(f"\n[OK] RESPONSE RECEIVED in {latency:.2f}s:")
                print("-" * 80)
                try:
                    parsed = json.loads(content)
                    print(json.dumps(parsed, indent=2))
                except Exception:
                    print(content)
                print("-" * 80)
            else:
                print(f"[ERROR] Ollama returned status {res.status_code}: {res.text}")

    except Exception as e:
        latency = time.perf_counter() - start
        print(f"[ERROR] Failed after {latency:.2f}s: {e}")


if __name__ == "__main__":
    main()
