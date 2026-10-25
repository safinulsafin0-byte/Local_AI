# JARVIS Stark Edition — Third-Party Licenses & Model Attributions

Every model, SDK, and third-party library used in JARVIS is verified against its upstream repository.
**Compliance Status**: 100% Permissive Commercial / Open Source (MIT, Apache 2.0, BSD-3, or Mozilla Public License 2.0).
**No copyleft AGPL or restrictive non-commercial licenses are bundled.**

---

## 1. Machine Learning Models & Speech Weights

| Component / Model | Upstream Developer | Architecture / Quantization | Official License | Permissibility Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Qwen 2.5 7B Instruct** | Alibaba Cloud / Qwen Team | GGUF Q4_K_M (via Ollama) | **Apache 2.0** | Permissive commercial and research use. Fully offline. |
| **Moondream 2** | Vikhyat / Moondream.ai | 1.86B Vision-Language (GGUF via Ollama) | **Apache 2.0** | Permissive open model for offline visual understanding. |
| **faster-whisper** | Systran / OpenAI Whisper | CTranslate2 INT8 (`small`) | **MIT License** | High-efficiency speech-to-text inference on CPU. |
| **bge-small-en-v1.5** | Beijing Academy of AI (BAAI) | ONNX Quantized Embeddings | **MIT License** | Zero-latency local document vectorization. |
| **Piper TTS (English)** | Michael Hansen (Rhasspy) | ONNX VITS Voice Engine | **MIT License** | Ultra-fast local neural text-to-speech. |
| **SD-Turbo** *(Documented)* | Stability AI | Single-Step Diffusion (PyTorch) | **Stability AI Non-Commercial Research Community License** | *Documented only, not active in default submission pipeline.* |

---

## 2. Core Python Runtime Dependencies

| Library / Package | Version Range | Upstream Source | License | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **FastAPI** | `>=0.110.0` | tiangolo/fastapi | **MIT** | High-performance asynchronous REST & SSE server |
| **Uvicorn** | `>=0.29.0` | encode/uvicorn | **BSD-3-Clause** | ASGI production server |
| **Pydantic** | `>=2.6.0` | pydantic/pydantic | **MIT** | Data schema validation and settings |
| **pycaw** | `>=20240210` | AndreMiras/pycaw | **MIT** | Windows Core Audio APIs (Hardware volume readback) |
| **psutil** | `>=5.9.0` | giampaolo/psutil | **BSD-3-Clause** | Cross-platform hardware & process telemetry |
| **pywin32** | `>=306` | mhammond/pywin32 | **PSF / BSD** | Windows Win32 GUI, process flags, and window handles |
| **RapidOCR-ONNXRuntime** | `>=1.3.0` | RapidAI/RapidOCR | **Apache 2.0** | Local optical character recognition on images/PDFs |
| **Pillow (PIL)** | `>=10.2.0` | python-pillow/Pillow | **HPND** | Image processing, STL visualization, screenshots |
| **Requests** | `>=2.31.0` | psf/requests | **Apache 2.0** | HTTP client for RSS and geocoding |
| **httpx** | `>=0.27.0` | encode/httpx | **BSD-3-Clause** | Asynchronous HTTP client |
| **Playwright** | `>=1.42.0` | microsoft/playwright-python | **Apache 2.0** | Automated E2E verification & UI screenshot rendering |
| **numpy** | `>=1.26.0` | numpy/numpy | **BSD-3-Clause** | Vector calculations and CAD mesh synthesis |
| **scipy** | `>=1.12.0` | scipy/scipy | **BSD-3-Clause** | Simulation numerical integration |

---

## 3. Web UI Libraries & Fonts

| Asset / Library | Origin | License | Purpose |
| :--- | :--- | :--- | :--- |
| **Clay.css** | code-boxx / Custom Clay UI | **MIT** | Soft neumorphic tactile design system |
| **Three.js** | mrdoob/three.js | **MIT** | WebGL 3D rendering for CAD STL viewer |
| **OrbitControls** | Three.js Examples | **MIT** | Interactive 3D camera pan, rotate, and zoom |
| **Inter Font** | Rasmus Andersson | **SIL Open Font License 1.1** | Clean UI typography |
| **JetBrains Mono** | JetBrains | **SIL Open Font License 1.1** | Code and terminal monospace font |

