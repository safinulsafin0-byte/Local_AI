"""
JARVIS Offline Image Generation Engine — image_generation/image_generator.py
=============================================================================
High-performance, memory-safe offline text-to-image pipeline:
- Auto-detects hardware: SDXL-Turbo on GPU (>=6GB VRAM) or SD-Turbo on CPU
- Strict offline support (local_files_only=True)
- Memory safety: Unloads Ollama chat model before generation
- Lazy pipeline loading + 5-minute idle auto-unload
- Built-in safety filter (NSFW, living politicians, violence/gore)
- Saves to D:/personal-ai-full/data/generated/<uuid>.png
"""

from __future__ import annotations

import gc
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import requests
import torch

logger = logging.getLogger("jarvis.image")

# ── Paths & Hardware Configuration ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "generated"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CPU_MODEL_DIR = BASE_DIR / "models" / "image" / "sd-turbo"
GPU_MODEL_DIR = BASE_DIR / "models" / "image" / "sdxl-turbo"

# State & Locks
_pipe = None
_pipe_lock = threading.Lock()
_idle_timer: Optional[threading.Timer] = None
_IDLE_TIMEOUT_SEC = 300.0  # 5 minutes


# ── Hardware & Backend Detection ────────────────────────────────────────────
def get_hardware_backend() -> Tuple[str, Path, str]:
    """
    Detect hardware and select appropriate model backend:
    Returns: (device_str, model_dir_path, model_type_name)
    """
    has_cuda = torch.cuda.is_available()
    if has_cuda:
        try:
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            if vram_gb >= 6.0 and GPU_MODEL_DIR.exists():
                return "cuda", GPU_MODEL_DIR, "SDXL-Turbo (fp16)"
        except Exception as e:
            logger.warning(f"Error querying CUDA VRAM: {e}")

    # Fallback / Default: SD-Turbo on CPU
    return "cpu", CPU_MODEL_DIR, "SD-Turbo (CPU)"


def is_model_installed() -> bool:
    """Check if the selected image model exists on disk with model files."""
    _, model_dir, _ = get_hardware_backend()
    if not model_dir.exists():
        return False
    # Check for index or unet config
    has_index = (model_dir / "model_index.json").exists()
    return has_index


def is_available() -> Tuple[bool, str]:
    """Check readiness for health endpoint."""
    try:
        import diffusers
        import transformers
    except ImportError as e:
        return False, f"Missing dependencies: {e}"

    _, model_dir, backend_name = get_hardware_backend()
    if not is_model_installed():
        return False, f"Model not installed at {model_dir.name}. Run: python scripts/download_image_model.py"

    return True, f"Ready ({backend_name})"


# ── Safety Filter ────────────────────────────────────────────────────────────
BANNED_PATTERNS = [
    # NSFW / sexually explicit
    r"\b(nsfw|nude|nudity|naked|porn|pornography|sex|sexual|erotic|vagina|penis|breasts|orgasm|hentai)\b",
    # Real living political figures / celebrities
    r"\b(donald trump|trump|joe biden|biden|vladimir putin|putin|sheikh hasina|hasina|narendra modi|modi|kamala harris|barack obama|obama|george bush|bill clinton)\b",
    # Graphic violence / extreme gore / terrorism
    r"\b(gore|behead|beheading|bloody decapitation|mutilated body|torture|massacre|terrorist attack|suicide)\b",
]

def check_safety(prompt: str) -> Optional[str]:
    """
    Returns an error refusal string if the prompt violates safety standards,
    or None if safe.
    """
    prompt_lower = prompt.lower()
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            return (
                "I cannot generate this image as it violates JARVIS safety guidelines "
                "(prohibiting NSFW content, real living politicians, or graphic violence/gore)."
            )
    return None


DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, bad anatomy, deformed, mutated, extra limbs, "
    "ugly, disfigured, text, watermark, signature, artifacts, oversaturated"
)


def enhance_image_prompt(prompt: str) -> str:
    """
    Enhances a user image prompt using the local LLM or deterministic aesthetic enrichment.
    Produces vivid descriptions of subject, lighting, environment, and visual quality.
    """
    clean = (prompt or "").strip().strip('"\'')
    if not clean:
        return ""

    # 1. Attempt LLM prompt enhancement if Ollama is accessible
    try:
        from llm.ollama_client import chat as llm_chat
        sys_msg = (
            "You are an expert prompt engineer for local Stable Diffusion models. "
            "Expand the user's prompt into a vivid, descriptive visual prompt (15-30 words). "
            "Focus on the visual subject, artistic lighting, composition, texture, and crisp detail. "
            "Output ONLY the improved prompt, without markdown quotes, commentary, or conversational filler."
        )
        res = llm_chat([{"role": "system", "content": sys_msg}, {"role": "user", "content": clean}])
        enhanced = str(res).strip().strip('"\'')
        if len(enhanced) > len(clean) and not any(w in enhanced.lower() for w in ["sure", "here is", "prompt:", "i cannot"]):
            return enhanced
    except Exception as e:
        logger.debug(f"[IMAGE] LLM prompt enhancement skipped: {e}")

    # 2. Deterministic high-aesthetic enrichment fallback
    enhancers = [
        "high resolution", "sharp focus", "soft studio lighting",
        "detailed texture", "8k photography", "cinematic composition"
    ]
    clean_lower = clean.lower()
    needed = [e for e in enhancers if e not in clean_lower]
    return f"{clean}, {', '.join(needed[:4])}"


# ── Memory Safety: Ollama Unload & Pipeline Timer ───────────────────────────
def unload_ollama_memory(model_name: str = "qwen2.5:7b") -> bool:
    """
    Unload the Ollama model from RAM by sending keep_alive: 0.
    """
    ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        r = requests.post(
            f"{ollama_host}/api/generate",
            json={"model": model_name, "keep_alive": 0},
            timeout=2.0
        )
        logger.info(f"[IMAGE] Unloaded Ollama model '{model_name}' memory: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        logger.debug(f"[IMAGE] Ollama unload ping skipped or failed: {e}")
        return False


def _schedule_idle_unload():
    """Schedules or resets the 5-minute idle unload timer."""
    global _idle_timer
    if _idle_timer is not None:
        try:
            _idle_timer.cancel()
        except Exception:
            pass
    _idle_timer = threading.Timer(_IDLE_TIMEOUT_SEC, unload_pipeline)
    _idle_timer.daemon = True
    _idle_timer.start()


def unload_pipeline():
    """Unloads the diffusion pipeline from memory and triggers garbage collection."""
    global _pipe
    with _pipe_lock:
        if _pipe is not None:
            logger.info("[IMAGE] Idle timeout reached. Unloading diffusion pipeline from RAM...")
            _pipe = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("[IMAGE] Diffusion pipeline successfully unloaded.")


# ── Model Loading ───────────────────────────────────────────────────────────
def load_image_pipeline(progress_callback: Optional[Callable[[str], None]] = None):
    """
    Lazily loads the diffusion pipeline using local_files_only=True.
    """
    global _pipe
    with _pipe_lock:
        if _pipe is not None:
            return _pipe

        if not is_model_installed():
            raise FileNotFoundError(
                "Image model not installed. Run: python scripts/download_image_model.py"
            )

        from diffusers import AutoPipelineForText2Image

        device, model_dir, backend_name = get_hardware_backend()
        logger.info(f"[IMAGE] Loading {backend_name} from {model_dir} on {device}...")
        if progress_callback:
            progress_callback(f"Loading {backend_name} model from local cache...")

        dtype = torch.float16 if device == "cuda" else torch.float32

        pipe = AutoPipelineForText2Image.from_pretrained(
            str(model_dir),
            torch_dtype=dtype,
            local_files_only=True,
            safety_checker=None,
        )
        pipe = pipe.to(device)

        if device == "cuda":
            try:
                pipe.enable_attention_slicing()
            except Exception:
                pass

        _pipe = pipe
        logger.info(f"[IMAGE] {backend_name} ready on {device.upper()}.")
        return _pipe


# ── Generation Function ─────────────────────────────────────────────────────
def generate_image(
    prompt: str,
    width: int = 512,
    height: int = 512,
    steps: int = 4,
    negative_prompt: Optional[str] = DEFAULT_NEGATIVE_PROMPT,
    seed: Optional[int] = None,
    enhance: bool = False,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Generate an image from prompt using offline SD-Turbo / SDXL-Turbo.

    Returns dict:
      {
        "ok": bool,
        "id": str,
        "path": str,
        "url": str,
        "prompt": str,
        "original_prompt": str,
        "seed": int,
        "steps": int,
        "width": int,
        "height": int,
        "time_taken": float,
        "error": Optional[str]
      }
    """
    orig_prompt = (prompt or "").strip()
    if not orig_prompt:
        return {"ok": False, "error": "Prompt cannot be empty"}

    # 1. Safety Check
    safety_violation = check_safety(orig_prompt)
    if safety_violation:
        return {"ok": False, "error": safety_violation}

    # Optional prompt enhancement
    if enhance:
        if progress_callback:
            progress_callback("Enhancing prompt for high-fidelity generation...")
        effective_prompt = enhance_image_prompt(orig_prompt)
    else:
        effective_prompt = orig_prompt

    # 2. Check model availability
    if not is_model_installed():
        return {
            "ok": False,
            "error": "Image model not installed. Run: python scripts/download_image_model.py"
        }

    # 3. Memory Safety: Unload Ollama
    if progress_callback:
        progress_callback("Unloading LLM memory to free RAM...")
    unload_ollama_memory()

    t_start = time.time()
    try:
        pipe = load_image_pipeline(progress_callback=progress_callback)

        device, _, _ = get_hardware_backend()

        # Seed configuration
        if seed is None:
            seed = int(torch.randint(0, 2**32 - 1, (1,)).item())
        generator = torch.Generator(device=device).manual_seed(seed)

        # Steps sanity check: 1 to 8 steps
        steps = max(1, min(steps, 8))

        if progress_callback:
            progress_callback(f"Generating image ({steps} step{'s' if steps > 1 else ''})...")

        pipe_kwargs: Dict[str, Any] = {
            "prompt": effective_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "generator": generator,
        }

        # Apply guidance and negative prompt if multi-step
        if steps > 1 and negative_prompt:
            pipe_kwargs["negative_prompt"] = negative_prompt
            pipe_kwargs["guidance_scale"] = 1.0
        else:
            pipe_kwargs["guidance_scale"] = 0.0

        with _pipe_lock:
            result = pipe(**pipe_kwargs)

        image = result.images[0]

        # Save output
        img_id = uuid.uuid4().hex[:12]
        file_name = f"{img_id}.png"
        file_path = OUTPUT_DIR / file_name
        image.save(str(file_path))

        time_taken = round(time.time() - t_start, 2)
        logger.info(f"[IMAGE] Generated {file_name} in {time_taken}s (steps={steps})")

        # Schedule idle unload (5 min)
        _schedule_idle_unload()

        return {
            "ok": True,
            "id": img_id,
            "path": str(file_path),
            "url": f"/generated/{file_name}",
            "prompt": effective_prompt,
            "original_prompt": orig_prompt,
            "seed": seed,
            "steps": steps,
            "width": width,
            "height": height,
            "time_taken": time_taken,
        }

    except Exception as exc:
        logger.error(f"[IMAGE] Generation failed: {exc}", exc_info=True)
        return {
            "ok": False,
            "error": f"Image generation failed: {exc}",
            "time_taken": round(time.time() - t_start, 2)
        }


# ── Tool Registry Adaptor ────────────────────────────────────────────────────
def image_generate_tool(prompt: str, steps: int = 4, seed: Optional[int] = None) -> str:
    """Tool wrapper for registry execution."""
    res = generate_image(prompt=prompt, steps=steps, seed=seed, enhance=True)
    if res.get("ok"):
        return f"SUCCESS: Generated image at {res['url']}. Path: {res['path']}. Prompt: {res['prompt']}"
    return f"ERROR: {res.get('error', 'Unknown generation error')}"