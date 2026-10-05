import re


class TitleSpecExtractor:
    """Deterministic entity regex extractor that extracts core laptop hardware specifications

    directly from product titles.
    Acts as a zero-rate-limit safety net when DOM specifications are missing or image-only.
    """

    @classmethod
    def extract(cls, title: str, specs_image_url: str | None = None) -> dict[str, str]:
        """Extract hardware specs from a laptop title.

        Returns dictionary with standardized keys:
          - Processor
          - Memory
          - Storage
          - Graphics
          - Display
          - Operating System
        """
        if not title:
            return {}

        specs: dict[str, str] = {}

        # 1. GPU (Extracted first to capture VRAM so system RAM doesn't accidentally match VRAM)
        gpu_m = re.search(
            r"(RTX\s*\d{4}(?:\s*Ti)?(?:\s*\d{1,2}GB(?:\s*GDDR[67])?)?|"
            r"GTX\s*\d{4}(?:\s*Ti)?(?:\s*\d{1,2}GB)?|"
            r"GeForce\s*RTX\s*\d{4}(?:\s*Ti)?(?:\s*\d{1,2}GB(?:\s*GDDR[67])?)?|"
            r"MX\s*\d{3}(?:\s*\d{1,2}GB)?|"
            r"Intel\s*(?:Iris\s*Xe|Arc\s*\w+|Graphics)|"
            r"Iris\s*Xe|"
            r"Radeon\s*\w+)",
            title,
            re.I,
        )
        if gpu_m:
            specs["Graphics"] = gpu_m.group(0).strip()

        # 2. CPU / Processor (supports Core iX, Ultra X, Core X, Ryzen with/without model, Celeron, Athlon)
        cpu_m = re.search(
            r"(?:Intel\s*)?(?:Ci|Core\s*i|\bi)\s*([3579])[\s-]*(\d{4,5}[A-Z0-9]*)|"
            r"(?:Intel\s*)?(?:Core\s*)?Ultra\s*([579])\s*(\d{3,4}[A-Z0-9]*)|"
            r"(?:Intel\s*)?Core\s*([357])\s*-?(\d{3,4}[A-Z0-9]*)|"
            r"(?:AMD\s*)?Ryzen\s*(?:AI\s*[79]\s*(?:HX\s*)?|\d\s*|[3579]\s*)(\d{4}[A-Z0-9]*|\w+)?|"
            r"(?:AMD\s*)?R([79])\s*(\d{4}[A-Z0-9]*)|"
            r"(?:Intel\s*)?(Celeron\s*[A-Z0-9]+)|"
            r"(?:AMD\s*)?(Athlon\s*[A-Z0-9]+)",
            title,
            re.I,
        )
        if cpu_m:
            specs["Processor"] = cpu_m.group(0).strip()

        # 3. RAM / Memory (supports 16GB, 16G DDR5, soldered, LPDDR)
        ram_explicit = re.search(r"\b(\d{1,2})\s*G(?:B)?\b\s*(?:DDR[45]|LPDDR\w*|RAM)\b", title, re.I)
        if ram_explicit:
            specs["Memory"] = ram_explicit.group(0).strip()
        else:
            for rm in re.finditer(r"\b(\d{1,2})\s*G(?:B)?\b", title, re.I):
                start = rm.start()
                preceding = title[max(0, start - 20) : start].lower()
                following = title[rm.end() : min(len(title), rm.end() + 15)].lower()
                if any(x in preceding for x in ["rtx", "gtx", "geforce", "mx", "vram"]) or "gddr" in following:
                    continue
                specs["Memory"] = rm.group(0).strip()
                break

        # 4. Storage (supports dual-drive setups e.g. 1TB HDD + 256GB SSD)
        storage_matches = list(re.finditer(
            r"\b(\d{1,2}(?:\.\d+)?\s*(?:TB|GB))\s*(?:SSD|HDD|HHD|NVMe|PCIe|M\.2|Gen\d)\b",
            title,
            re.I
        ))
        if storage_matches:
            specs["Storage"] = " + ".join(m.group(0).strip() for m in storage_matches)
        else:
            st_fallback = re.search(r"\b(\d{1,2}\s*TB|\d{3,4}\s*GB)\s*(?:SSD|HDD|NVMe)?\b", title, re.I)
            if st_fallback and "ram" not in st_fallback.group(0).lower():
                specs["Storage"] = st_fallback.group(0).strip()

        # 5. Display / Screen (handles 15.6 FHD, 16" 165Hz, 15.6 HD, 18'' QHD+, 40.6 cm (16) WUXGA)
        disp_m = re.search(
            r"(\b\d{2}(?:\.\d)?\s*(?:[\"']{1,2}|inch|-inch)\s*(?:(?:FHD\+?|QHD\+?|WUXGA|WQXGA|UHD|HD|2\.5K|4K|OLED|IPS|Touch|(?:60|120|144|165|240|360)\s*Hz)\b[^\s,–—()]*)*|"
            r"\b\d{2}(?:\.\d)?\s*(?:FHD\+?|QHD\+?|WUXGA|WQXGA|UHD|HD|2\.5K|4K|OLED|IPS|Touch|(?:60|120|144|165|240|360)\s*Hz)\b(?:[^\s,–—()]+|\s+(?:FHD\+?|QHD\+?|WUXGA|WQXGA|UHD|HD|2\.5K|4K|OLED|IPS|Touch|\d+Hz|sRGB|G-SYNC|100%))*|"
            r"\b\d{2}(?:\.\d)?\s*(?:[\"']{1,2}|inch|-inch)\b|"
            r"\b\d{2}(?:\.\d)?\s*HD\b|"
            r"\b(?:QHD\+?|WUXGA|WQXGA|FHD\+?)\s*(?:Display|Screen)\b|"
            r"\b\d{2}(?:\.\d)?\s*cm\s*\(\d{2}\)\s*\w+)",
            title,
            re.I,
        )
        if disp_m:
            specs["Display"] = disp_m.group(0).strip().rstrip("-")
        else:
            # Dell numbering fallback (e.g. Dell 3510 / 5510 / 3520 where middle digit 5 indicates 15.6")
            if re.search(r"\bDELL\s*(?:[A-Za-z]+\s*)?[357]5\d{2}\b", title, re.I):
                specs["Display"] = "15.6 Inch"
            elif specs_image_url and re.search(r"\b(?:vostro|inspiron|latitude)-?15\b", specs_image_url, re.I):
                specs["Display"] = "15.6 Inch"

        # 6. Operating System
        os_m = re.search(r"\b(Win(?:dows)?\s*(?:11|10)(?:\s*(?:Home|Pro))?|DOS)\b", title, re.I)
        if os_m:
            specs["Operating System"] = os_m.group(0).strip()

        # 7. Integrated GPU fallback if no discrete GPU was present in title
        if "Graphics" not in specs:
            proc = specs.get("Processor", "").lower()
            if any(w in proc for w in ["celeron", "pentium", "core", "ci", "intel"]):
                specs["Graphics"] = "Intel Integrated Graphics"
            elif any(w in proc for w in ["athlon", "ryzen", "amd"]):
                specs["Graphics"] = "AMD Radeon Graphics"

        return specs

    @classmethod
    def detect_core_slots(cls, specs: dict[str, str]) -> dict[str, str | None]:
        """Detect the presence of the 5 canonical hardware slots in an arbitrary specs dictionary.

        Returns mapping:
          {
            'cpu': value or None,
            'ram': value or None,
            'storage': value or None,
            'gpu': value or None,
            'display': value or None,
          }
        """
        cpu: str | None = None
        ram: str | None = None
        storage: str | None = None
        gpu: str | None = None
        display: str | None = None

        # 1. CPU Slot
        for k, v in specs.items():
            ks = str(k).strip()
            vs = str(v).strip()
            k_low = ks.lower()
            v_low = vs.lower()
            comb = f"{ks}: {vs}".lower()
            if not cpu:
                if any(w in k_low for w in ["cpu", "processor", "cores/threads", "base clock speed"]) and not any(w in k_low for w in ["gpu", "graphics", "audio"]):
                    cpu = vs
                elif k_low == "type" and any(w in v_low for w in ["core", "ryzen", "celeron", "athlon"]):
                    cpu = vs
                elif any(w in comb for w in ["p-core", "turbo frequency", "amd ryzen", "intel core"]):
                    cpu = vs

        # 2. RAM Slot (ignores OS and VRAM false positives)
        for k, v in specs.items():
            ks = str(k).strip()
            vs = str(v).strip()
            k_low = ks.lower()
            v_low = vs.lower()
            if not ram:
                if any(w in k_low for w in ["vram", "graphics", "video", "os", "software", "login", "webcam"]):
                    continue
                if any(w in v_low for w in ["windows", "dos", "linux", "ubuntu"]):
                    continue
                if any(w in k_low for w in ["installed ram", "system memory", "ram", "memory"]):
                    ram = vs
                elif k_low in ("installed", "capacity", "type") and any(w in v_low for w in ["ddr", "so-dimm", "2x8gb", "2x16gb", "16gb", "32gb", "64gb", "8gb", "4gb", "lpddr", "16g", "32g", "64g"]):
                    ram = vs

        # 3. Storage Slot
        for k, v in specs.items():
            ks = str(k).strip()
            vs = str(v).strip()
            k_low = ks.lower()
            v_low = vs.lower()
            if not storage:
                if any(w in k_low for w in ["slots", "expansion", "support", "interface", "form factor"]):
                    continue
                if any(w in k_low for w in ["storage", "primary drive", "ssd", "hard drive", "storage capacity"]):
                    if any(c in v_low for c in ["gb", "tb", "512", "256", "1tb", "2tb", "ssd", "hdd"]):
                        storage = vs
                elif "capacity" in k_low and any(w in v_low for w in ["ssd", "nvme", "hdd", "pcie", "1tb", "2tb", "512gb", "256gb"]) and "wh" not in v_low:
                    storage = vs

        # 4. GPU Slot
        for k, v in specs.items():
            ks = str(k).strip()
            vs = str(v).strip()
            k_low = ks.lower()
            v_low = vs.lower()
            comb = f"{ks}: {vs}".lower()
            if not gpu:
                if any(w in comb for w in ["gpu", "graphic", "graphics", "video card", "vga", "geforce", "rtx", "gtx", "radeon", "intel iris", "intel arc", "intel graphics", "integrated graphics"]):
                    gpu = vs
                elif k_low == "controller" and any(w in v_low for w in ["intel", "nvidia", "amd"]):
                    gpu = vs

        # 5. Display Slot (prioritizes screen size & resolution over generic Display Support / DisplayPort)
        for k, v in specs.items():
            ks = str(k).strip()
            vs = str(v).strip()
            k_low = ks.lower()
            v_low = vs.lower()
            if not display:
                if any(w in k_low for w in ["support", "port", "output"]):
                    continue
                if any(w in k_low for w in ["screen size", "display size", "display", "resolution", "panel type", "screen"]):
                    if any(c in v_low or c in k_low for c in ['"', "inch", "cm", "15", "16", "14", "17", "18", "13", "11", "12", "fhd", "qhd", "wqxga", "wuxga", "oled", "ips", "hz", "touch"]):
                        display = vs
                elif k_low == "size" and any(w in v_low for w in ['"', "inch", "cm", "15", "16", "14", "17", "18", "13", "11", "12"]):
                    display = vs
                elif any(w in k_low for w in ["15.6", "16-inch", "14-inch", "17.3", "18-inch", "13.3", "13.4"]):
                    display = f"{ks} {vs}".strip()

        return {
            "cpu": cpu,
            "ram": ram,
            "storage": storage,
            "gpu": gpu,
            "display": display,
        }


