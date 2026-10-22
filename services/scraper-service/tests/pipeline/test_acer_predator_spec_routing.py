from app.pipeline.deterministic import DeterministicExtractor, TableKeyRouter
from app.pipeline.llm_auditor import LLMAuditor, FieldCorrection


def test_marketing_keys_not_routed_to_hardware_subsystems():
    router = TableKeyRouter()

    # 1. Marketing headlines ending with period or containing promotional prose
    assert router.route_key("Every Frame Looks Unbelievable.") == "unrouted"
    assert router.route_key("RTX 5090 Power. No Half Measures.") == "unrouted"
    assert router.route_key("Built to Dominate.") == "unrouted"
    assert router.route_key("Performance That Stays Unlocked.") == "unrouted"
    assert router.route_key("Ready for Your Complete Setup.") == "unrouted"
    assert router.route_key("Built Around the Player.") == "unrouted"
    assert router.route_key("The Ultimate Predator Has Arrived.") == "unrouted"

    # 2. Legitimate technical keys are properly routed
    assert router.route_key("Standard Memory") == "memory_type"
    assert router.route_key("Maximum Supported System Memory") == "max_memory"
    assert router.route_key("Memory") == "memory"
    assert router.route_key("Screen Size") == "display"
    assert router.route_key("Display Screen Type") == "display"
    assert router.route_key("Battery") == "power"
    assert router.route_key("Power Adapter") == "power"
    assert router.route_key("Total Solid State Drive Capacity") == "storage"


def test_acer_predator_memory_and_power_raw_specs():
    table = {
        "Processor Manufacturer": "Intel",
        "Processor Type": "Core Ultra 9",
        "Standard Memory": "16 GB",
        "Maximum Supported System Memory": "64 GB",
        "System Memory Technology": "DDR5 SDRAM",
        "Total Solid State Drive Capacity": "1 TB",
        "Solid State Drive Interface": "PCI Express NVMe 5.0",
        "SSD Form Factor": "M.2",
        "Screen Size": '40.6 cm (16")',
        "Display Screen Type": "OLED",
        "Memory": "16GB DDR5 6400MT/s, supports up to 64GB",
        "Storage": "1TB PCIe Gen 5 NVMe M.2 SSD",
        "Battery": "90Wh Lithium-ion",
        "Power Adapter": "330W",
        "Weight": "Approximately 2.65kg",
        "Built to Dominate.": "Desktop-class gaming power...",
        "Intel Core Ultra 9 275HX": "24 cores with Intel AI Boost",
        "GeForce RTX 5090": "24GB GDDR7 • Up to 175W",
        "16-inch WQXGA OLED": "240Hz • 100% DCI-P3 • G-SYNC",
        "32GB DDR5 + 1TB SSD": "DDR5 6400MT/s • PCIe Gen 5 NVMe",
        "RTX 5090 Power. No Half Measures.": "Powered by NVIDIA Blackwell architecture...",
        "Every Frame Looks Unbelievable.": "The 16-inch OLED display combines a sharp 2560 x 1600 resolution with a fluid 240Hz refresh rate...",
        "Performance That Stays Unlocked.": "The advanced thermal system...",
        "Ready for Your Complete Setup.": "Dual Thunderbolt...",
        "Built Around the Player.": "Customize every detail...",
        "The Ultimate Predator Has Arrived.": "Get the Acer Predator...",
    }
    title = 'Acer Predator Helios 16 AI PH16-73-92V4 16" WQXGA OLED 240Hz Intel Core Ultra 9 275HX 32GB RAM 1TB SSD GeForce RTX 5090 24GB Black NH.QW2EM.001'

    extractor = DeterministicExtractor()
    specs, envs = extractor.extract(title=title, sanitized_table=table, sanitized_sections={})

    # Memory checks
    assert specs["memory"]["capacity_gb"] == 16
    assert "Every Frame Looks Unbelievable" not in specs["memory"]["raw_spec"]
    assert "2560" not in specs["memory"]["raw_spec"]
    assert "Standard Memory: 16 GB" in specs["memory"]["raw_spec"]

    # Power & battery checks
    assert specs["power_battery"]["power_adapter_w"] == 330
    assert specs["power_battery"]["battery_capacity_wh"] == 90.0
    assert "RTX 5090 Power" not in specs["power_battery"]["raw_spec"]
    assert "Blackwell" not in specs["power_battery"]["raw_spec"]


def test_llm_auditor_preserves_table_memory_capacity():
    auditor = LLMAuditor(endpoints=[])

    laptop = {
        "title": 'Acer Predator Helios 16 AI PH16-73-92V4 16" WQXGA OLED 240Hz Intel Core Ultra 9 275HX 32GB RAM 1TB SSD GeForce RTX 5090 24GB Black NH.QW2EM.001',
        "source_table": {
            "Standard Memory": "16 GB",
            "Memory": "16GB DDR5 6400MT/s, supports up to 64GB",
            "32GB DDR5 + 1TB SSD": "DDR5 6400MT/s • PCIe Gen 5 NVMe",
        },
        "specs": {"memory": {"capacity_gb": 16, "memory_type": "DDR5"}},
    }

    # Simulate an LLM attempting to override 16 with 32 due to title / promo banner
    correction = FieldCorrection(
        field_path="memory.capacity_gb",
        current_value=16,
        corrected_value=32,
        reason="Title explicitly states 32GB RAM and banner states 32GB DDR5",
        evidence_quote="32GB RAM",
    )

    applied = auditor.apply_corrections(laptop, [correction])

    # The programmatic table precedence guard must reject the 32GB override
    assert len(applied) == 0
    assert laptop["specs"]["memory"]["capacity_gb"] == 16


def test_table_key_router_default_loads_specs_alias_dict():
    """Verify TableKeyRouter defaults to loading specs_alias_dict.json with full coverage."""
    router = TableKeyRouter()
    assert len(router.label_to_bucket) > 500
    assert router.route_key("solid state drive interface") == "storage_interface"


def test_generic_multi_store_routing_arabic_keys():
    """Verify TableKeyRouter properly routes Arabic keys from Egyptian retailers."""
    router = TableKeyRouter()

    # Core components in Arabic
    assert router.route_key("المعالج") == "cpu"
    assert router.route_key("نوع المعالج") == "cpu"
    assert router.route_key("كارت الشاشة") == "gpu"
    assert router.route_key("بطاقة الرسومات") == "gpu"
    assert router.route_key("الذاكرة") == "memory"
    assert router.route_key("سعة الرام") == "memory"
    assert router.route_key("أقصى سعة للذاكرة") == "max_memory"
    assert router.route_key("سعة التخزين") == "storage"
    assert router.route_key("القرص الصلب") == "storage"
    assert router.route_key("الشاشة") == "display"
    assert router.route_key("حجم الشاشة") == "display"
    assert router.route_key("البطارية") == "power"
    assert router.route_key("الوزن") == "weight"
    assert router.route_key("المنافذ") == "ports"


def test_unstructured_specs_parser():
    """Verify TableKeyRouter.parse_unstructured_specs correctly converts bullets and text blocks."""
    # 1. Bullet list
    bullets = [
        "• Processor: Intel Core i7-13700H",
        "• RAM: 16 GB DDR5",
        "• Storage - 1TB NVMe SSD",
        "• Display: 15.6 inch FHD 144Hz",
        "Just a random marketing sentence without key value",
    ]
    parsed = TableKeyRouter.parse_unstructured_specs(bullets)
    assert parsed.get("Processor") == "Intel Core i7-13700H"
    assert parsed.get("RAM") == "16 GB DDR5"
    assert parsed.get("Storage") == "1TB NVMe SSD"
    assert parsed.get("Display") == "15.6 inch FHD 144Hz"

    # 2. Text block
    text_block = """
    CPU: AMD Ryzen 7 7840HS
    Memory: 32GB
    GPU: NVIDIA GeForce RTX 4070
    """
    parsed_text = TableKeyRouter.parse_unstructured_specs(text_block)
    assert parsed_text.get("CPU") == "AMD Ryzen 7 7840HS"
    assert parsed_text.get("Memory") == "32GB"
    assert parsed_text.get("GPU") == "NVIDIA GeForce RTX 4070"
