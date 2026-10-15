import json
import os
import time
from typing import Any
import httpx
from pydantic import ValidationError

from .schema import LaptopSpecExtraction
from .table_extractor import reconcile_specs


class LocalModelExtractor:
    """Extracts structured laptop specifications from unstructured text using a local LLM.
    
    Supports:
      1. Ollama local daemon (default: http://localhost:11434)
      2. OpenAI-compatible local servers (LM Studio, llama-server, vLLM)
    """

    SYSTEM_PROMPT = (
        "You are an expert hardware specification extractor for laptops. "
        "Your task is to map technical specifications from the provided specifications table and product text into the JSON schema without dropping any technical specifications.\n\n"
        "STRICT MAPPING INSTRUCTIONS:\n"
        "1. CORE HARDWARE:\n"
        "   - processor: Map from 'CPU', 'PROCESSOR', 'Processor Model'.\n"
        "   - graphics: Map from 'GPU', 'GRAPHICS', 'Graphics Card', VRAM.\n"
        "   - ram: Map from 'MEMORY', 'RAM', 'System Memory'.\n"
        "   - storage: Map from 'STORAGE', 'SSD', 'Hard Drive'.\n"
        "   - display: Map from 'DISPLAY', 'Screen', 'Resolution', 'Panel', 'Refresh Rate'. Combine screen size, resolution, and refresh rate.\n\n"
        "2. SECONDARY SPECIFICATIONS (Map every available row - NEVER omit):\n"
        "   - battery: Extract battery capacity/cells (Wh, cell count) from 'BATTERY' or 'POWER'.\n"
        "   - power_adapter: Extract power supply/adapter wattage from 'POWER ADAPTER' or 'POWER'.\n"
        "   - operating_system: Map from 'OS', 'OPERATING SYSTEM'. Keep exact OS (e.g. Windows 11, FreeDOS, DOS, None).\n"
        "   - ports: Map from 'CONNECTIVITY', 'PORTS', 'I/O Ports', 'USB Ports', HDMI, etc.\n"
        "   - wireless: Map from 'NETWORK', 'WIRELESS', 'WLAN + BLUETOOTH', Wi-Fi, Bluetooth, etc.\n"
        "   - camera: Map from 'CAMERA', 'WEBCAM'.\n"
        "   - audio: Map from 'AUDIO', 'SPEAKER'.\n"
        "   - keyboard: Map from 'KEYBOARD', 'KEYBOARD & TOUCHPAD'.\n"
        "   - weight: Map from 'WEIGHT'.\n"
        "   - warranty: Map from 'WARRANTY'.\n"
        "   - cpu_cores: Map from 'CPU CORES / THREADS'.\n"
        "   - gpu_power: Map from 'GPU Power', 'Max Graphics Power', TGP.\n"
        "   - ram_slots: Map from 'MEMORY SLOTS', 'MAX MEMORY'.\n"
        "   - storage_slots: Map from 'STORAGE SLOTS', 'STORAGE EXPANSION'.\n"
        "   - series_model: Map from 'MODEL', 'Series'.\n"
        "   - part_number_or_sku: Map from 'Part Number', 'Product Number', SKU.\n"
        "   - brand: Laptop brand.\n\n"
        "STRICT RULES:\n"
        "1. ONLY extract information that is explicitly stated in the input text or table.\n"
        "2. If an attribute does NOT appear in the input text, set its value to null.\n"
        "3. NEVER invent, guess, or output placeholder values."
    )

    def __init__(
        self,
        model_name: str = "qwen2.5:1.5b",
        base_url: str | None = None,
        timeout: float = 120.0,
    ):
        self.model_name = model_name
        self.base_url = base_url or os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
        self.timeout = timeout

    def check_health(self) -> dict[str, Any]:
        """Check if local LLM server is accessible."""
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    models = [m.get("name") for m in res.json().get("models", [])]
                    return {"status": "ok", "backend": "ollama", "models": models}
        except Exception:
            pass

        # Try OpenAI-compatible health
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.base_url}/v1/models")
                if res.status_code == 200:
                    models = [m.get("id") for m in res.json().get("data", [])]
                    return {"status": "ok", "backend": "openai_compatible", "models": models}
        except Exception:
            pass

        return {
            "status": "offline",
            "message": f"No local LLM server found at {self.base_url}. Ensure Ollama or llama-server is running.",
        }

    def extract(self, text: str) -> tuple[LaptopSpecExtraction | None, float, str | None]:
        """Extract structured specifications from text string.
        
        Returns:
            (extraction_result, latency_seconds, error_message)
        """
        if not text or not text.strip():
            return None, 0.0, "Input text is empty"

        start_time = time.perf_counter()

        # Attempt Ollama native structured extraction
        try:
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Extract specs from this product text:\n\n{text}"},
                ],
                "stream": False,
                "format": LaptopSpecExtraction.model_json_schema(),
                "options": {
                    "temperature": 0.0,  # Zero temperature for deterministic extraction
                },
            }

            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(f"{self.base_url}/api/chat", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data.get("message", {}).get("content", "").strip()
                    parsed_json = json.loads(content)
                    specs = LaptopSpecExtraction.model_validate(parsed_json)
                    latency = time.perf_counter() - start_time
                    return specs, latency, None

        except httpx.ConnectError:
            # Server not running
            return None, 0.0, f"Local model server offline at {self.base_url}"
        except (ValidationError, json.JSONDecodeError) as e:
            latency = time.perf_counter() - start_time
            return None, latency, f"Schema validation error: {e}"
        except Exception as e:
            latency = time.perf_counter() - start_time
            return None, latency, f"Extraction failed: {e}"

        return None, time.perf_counter() - start_time, "Unhandled server response"

    def extract_specs(
        self,
        text: str,
        raw_table: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], LaptopSpecExtraction | None, float, str | None]:
        """Extract structured specifications and reconcile with raw table data.
        
        Guarantees that 100% of technical specifications from the table are
        preserved without dropping anything.
        
        Returns:
            (reconciled_specs_dict, raw_llm_model, latency_seconds, error_message)
        """
        model_specs, latency, err = self.extract(text)
        reconciled = reconcile_specs(model_specs, raw_table or {})
        return reconciled, model_specs, latency, err
