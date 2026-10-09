# Isolated Local Model Extractor (`local_extractor`)

An isolated sandbox to test and benchmark the **Local Model Information Extraction** approach before generalizing across the scraping service.

---

## 1. What's in this folder?

- `schema.py`: Strict Pydantic model (`LaptopSpecExtraction`) defining the target hardware slots (Processor, Cores, RAM, Dual Storage, GPU, Display, OS, Warranty).
- `extractor.py`: Local LLM extraction client with zero-temperature enforcement and strict JSON schema adherence. Works out of the box with **Ollama** or any local OpenAI-compatible endpoint.
- `test_runner.py`: Benchmarks the 5 real-world edge cases that broke regex in past runs (Dual storage, missing screen sizes, high RAM speeds, separated touch displays, and unformatted PDP text).

---

## 2. Quick Setup (1 Minute)

### Step 1: Install Ollama (If not already installed)
Download and install [Ollama for Windows](https://ollama.com/download/windows).

### Step 2: Download the Ultra-Light Model (1.3 GB)
Open PowerShell or CMD and run:
```bash
ollama run qwen2.5:1.5b
```
*(This downloads the 1.5B model once and starts the local background server on `http://localhost:11434`)*.

---

## 3. Run the Isolated Test

From the `scraper-service` root directory:
```bash
.\.venv\Scripts\python.exe local_extractor/test_runner.py
```

The script will evaluate:
1. **Extraction Accuracy:** Confirms dual storage (`1TB HDD + 256GB SSD`), RAM speeds (`5600`), and zero screen-size hallucinations.
2. **Inference Latency:** Measures the exact milliseconds required per laptop on your hardware.
3. **Schema Compliance:** Validates that output is 100% typed Python data.
