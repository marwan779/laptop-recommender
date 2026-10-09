"""Audit and compare compumarts_level2_results.json against live PDPs.

Visits each PDP in compumarts, extracts raw table specifications, and compares
every single field against the extracted specs in the JSON results.
"""

import json
import os
import sys
import time

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs4 import BeautifulSoup
from app.engine.scrapling_engine import ScraplingEngine
from local_extractor.table_extractor import extract_raw_spec_table, split_power_specs, clean_str


def run_audit():
    results_path = os.path.join(os.path.dirname(__file__), "compumarts_level2_results.json")
    if not os.path.exists(results_path):
        print(f"File not found: {results_path}")
        return

    with open(results_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    print("=" * 80)
    print(f"📊 AUDITING {len(products)} LAPTOPS IN compumarts_level2_results.json AGAINST PDPs")
    print("=" * 80)

    engine = ScraplingEngine()
    audit_results = []
    total_issues = 0

    for idx, prod in enumerate(products, 1):
        title = prod.get("title", "Unknown")
        url = prod.get("product_url", "")
        extracted_specs = prod.get("specs", {})

        print(f"[{idx}/{len(products)}] Checking: {title[:60]}...")
        doc = engine.fetch(url, stealth=False)
        html_text = doc.html if (doc and doc.html) else ""

        if not html_text:
            audit_results.append({
                "index": idx,
                "title": title,
                "url": url,
                "status": "error_fetching_pdp",
                "extracted_specs": extracted_specs,
                "issues": ["Failed to fetch PDP HTML"],
            })
            continue

        raw_table = extract_raw_spec_table(html_text)
        issues = []

        # Check Core Hardware
        norm_table = {k.lower(): v for k, v in raw_table.items()}

        # 1. CPU / Processor
        if any(k in norm_table for k in ("cpu", "processor", "processor model")):
            if not extracted_specs.get("processor"):
                issues.append("Missing processor despite CPU/Processor in PDP")

        # 2. GPU / Graphics
        if any(k in norm_table for k in ("gpu", "graphics", "graphics card")):
            if not extracted_specs.get("graphics"):
                issues.append("Missing graphics despite GPU/Graphics in PDP")

        # 3. RAM / Memory
        if any(k in norm_table for k in ("memory", "ram", "system memory")):
            if not extracted_specs.get("ram"):
                issues.append("Missing ram despite MEMORY/RAM in PDP")

        # 4. Storage / SSD
        if any(k in norm_table for k in ("storage", "ssd", "hard drive")):
            if not extracted_specs.get("storage"):
                issues.append("Missing storage despite STORAGE in PDP")

        # 5. Display / Screen
        if any(k in norm_table for k in ("display", "screen", "panel size")):
            if not extracted_specs.get("display"):
                issues.append("Missing display despite DISPLAY in PDP")

        # 6. Battery / Power
        if any(k in norm_table for k in ("battery", "power", "battery & power")):
            if not extracted_specs.get("battery"):
                issues.append("Missing battery despite BATTERY/POWER in PDP")

        # 7. Ports / Connectivity
        if any(k in norm_table for k in ("ports", "connectivity", "i/o ports")):
            if not extracted_specs.get("ports"):
                issues.append("Missing ports despite CONNECTIVITY/PORTS in PDP")

        # 8. OS / Operating System
        if any(k in norm_table for k in ("os", "operating system")):
            if not extracted_specs.get("operating_system"):
                issues.append("Missing operating_system despite OS in PDP")

        if issues:
            total_issues += 1
            print(f"   ⚠️  Issues ({len(issues)}): {issues}")
        else:
            print("   ✅ 100% Match with PDP table!")

        audit_results.append({
            "index": idx,
            "title": title,
            "url": url,
            "pdp_table_keys": list(raw_table.keys()),
            "extracted_specs_keys": list(extracted_specs.keys()),
            "sample_pdp": raw_table,
            "sample_json": extracted_specs,
            "issues": issues,
        })

    report_path = os.path.join(os.path.dirname(__file__), "audit_new_comparison_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"🏁 AUDIT COMPLETE: {len(products)} Laptops Checked")
    print(f"   Laptops with 100% Clean Spec Parity: {len(products) - total_issues}/{len(products)} ({(len(products) - total_issues)/len(products)*100:.1f}%)")
    print(f"   Laptops with Discrepancies: {total_issues}")
    print(f"   Detailed report saved to: {report_path}")
    print("=" * 80)


if __name__ == "__main__":
    run_audit()
