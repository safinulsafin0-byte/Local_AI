"""
Downloads the offline SD-Turbo diffusion model into models/image/sd-turbo.
"""

import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_DIR = BASE_DIR / "models" / "image" / "sd-turbo"
TARGET_DIR.mkdir(parents=True, exist_ok=True)

MODEL_REPO = "stabilityai/sd-turbo"

print(f"Downloading model '{MODEL_REPO}' into: {TARGET_DIR}")
start_time = time.time()

try:
    from huggingface_hub import snapshot_download

    # Exclude single-file checkpoint, fp16 duplicates, and docs/images to keep download minimal
    ignore_patterns = [
        "*.png", "*.jpg", "*.jpeg", "*.md", "*.txt",
        "sd_turbo.safetensors", "*.fp16.safetensors"
    ]
    # We need tokenizer files like merges.txt though!
    # So let's allow *.txt for tokenizer
    ignore_patterns = [
        "*.png", "*.jpg", "*.jpeg", "*.md", "sd_turbo.safetensors", "*.fp16.safetensors"
    ]

    path = snapshot_download(
        repo_id=MODEL_REPO,
        local_dir=str(TARGET_DIR),
        ignore_patterns=ignore_patterns,
        resume_download=True
    )

    elapsed = time.time() - start_time
    total_size = sum(f.stat().st_size for f in TARGET_DIR.rglob("*") if f.is_file())
    total_mb = total_size / (1024 * 1024)
    total_gb = total_size / (1024 * 1024 * 1024)

    print(f"\n[SUCCESS] Model downloaded in {elapsed:.1f}s.")
    print(f"Path: {TARGET_DIR}")
    print(f"Total Size: {total_mb:.1f} MB ({total_gb:.2f} GB)")

except Exception as exc:
    print(f"[ERROR] Failed to download model: {exc}")
    sys.exit(1)

