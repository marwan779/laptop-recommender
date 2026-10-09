from pydantic import BaseModel, Field


class LaptopSpecExtraction(BaseModel):
    """Pydantic schema capturing all technical hardware specifications."""

    # Core Hardware Attributes (Required - Enforced by Grammar to prevent dropping)
    processor: str = Field(
        description="CPU processor model (e.g. Intel Core i7-13650HX, AMD Ryzen 5 7535U, Core i3-1315U, 1315U). Look for CPU, Processor.",
    )
    graphics: str = Field(
        description="GPU name and VRAM (e.g. NVIDIA GeForce RTX 5070 8GB, RTX 4050 6GB, Radeon 660M, UHD Graphics). Look for GPU, Graphics.",
    )
    ram: str = Field(
        description="Total RAM capacity and speed (e.g. 16GB DDR5-4800, 32GB DDR5, 16). Look for MEMORY, RAM.",
    )
    storage: str = Field(
        description="Primary storage capacity and type (e.g. 512GB SSD M.2 NVMe, 1TB SSD, 512). Look for STORAGE, Storage, SSD.",
    )
    display: str = Field(
        description="Display screen size, resolution, and refresh rate (e.g. 15.6 FHD 144Hz, 15.3-inch WUXGA 1920x1200, 1920 x 1080). Look for DISPLAY, Screen.",
    )

    # Identifiers & Physical Specs (Optional)
    brand: str | None = Field(
        default=None,
        description="Laptop brand name (e.g. Lenovo, Dell, Asus, HP, Apple, XPG).",
    )
    series_model: str | None = Field(
        default=None,
        description="Chassis model name or code (e.g. Legion 5 15IRX10, LOQ 15IRX9, HP 255 G10). Never put GPU/component names here.",
    )
    part_number_or_sku: str | None = Field(
        default=None,
        description="Manufacturer part number or model SKU (e.g. 83LY00R8ED, 83DV01HRPS, B39STAT#A2N).",
    )
    cpu_cores: str | None = Field(
        default=None,
        description="Processor core and thread count (e.g. 14 cores (6P + 8E) / 20 threads, 20 Cores).",
    )
    ram_slots: str | None = Field(
        default=None,
        description="RAM expansion slots and upgradability (e.g. Two DDR5 SODIMM slots, dual-channel capable, up to 32GB).",
    )
    storage_slots: str | None = Field(
        default=None,
        description="Storage expansion slots (e.g. Two M.2 2280 PCIe 4.0 x4 slots).",
    )
    gpu_power: str | None = Field(
        default=None,
        description="GPU TGP / wattage and boost clock (e.g. 115W TGP 2347MHz, 105W).",
    )
    battery: str | None = Field(
        default=None,
        description="Battery capacity and cell count (e.g. 80Wh, 41 Wh Li-ion).",
    )
    power_adapter: str | None = Field(
        default=None,
        description="Power supply adapter wattage (e.g. 245W Slim Tip AC adapter, 65W USB-C).",
    )
    operating_system: str | None = Field(
        default=None,
        description="Operating system (e.g. DOS, FreeDOS, Windows 11 Home).",
    )
    ports: str | None = Field(
        default=None,
        description="I/O ports and connectivity summary.",
    )
    wireless: str | None = Field(
        default=None,
        description="Wireless networking (e.g. Wi-Fi 6 802.11ax + BT 5.2).",
    )
    camera: str | None = Field(
        default=None,
        description="Webcam specs (e.g. HD 720p with privacy shutter, 1080p FHD).",
    )
    audio: str | None = Field(
        default=None,
        description="Audio tech (e.g. HARMAN stereo speakers 2Wx2 Nahimic Audio, Dolby Atmos).",
    )
    keyboard: str | None = Field(
        default=None,
        description="Keyboard details (e.g. White backlit Arabic with numeric keypad).",
    )
    weight: str | None = Field(
        default=None,
        description="Laptop weight (e.g. 2.1kg, 2.38 kg).",
    )
    warranty: str | None = Field(
        default=None,
        description="Warranty period (e.g. 2 Years Lenovo Warranty, 1 Year Local Warranty).",
    )
