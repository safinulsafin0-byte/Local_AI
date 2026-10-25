from pathlib import Path
import os


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent


# ============================================================
# OLLAMA
# ============================================================

OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://127.0.0.1:11434"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:7b"
)

# Trust mode: "full" (autonomous PC control) or "confirm_destructive"
TRUST_MODE = os.getenv("JARVIS_TRUST_MODE", "full")


# ============================================================
# ALLOWED FILESYSTEM ROOTS
# ============================================================

# JARVIS can access these folders (in full trust mode, all standard local drives)
ALLOWED_ROOT_DIRS = [
    BASE_DIR,
    Path(r"D:\personal-ai"),
    Path(r"D:\personal-ai-full"),
    Path("D:/"),
    Path("C:/"),
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
]


# ============================================================
# INTERNAL DIRECTORIES
# ============================================================

MEMORY_DB = (
    BASE_DIR
    / "memory"
    / "memory.db"
)

RAG_DIR = (
    BASE_DIR
    / "rag"
    / "data"
)

CHROMA_DIR = (
    BASE_DIR
    / "rag"
    / "chroma"
)

BROWSER_PROFILE = (
    BASE_DIR
    / "browser"
    / "profile"
)

SCREENSHOTS_DIR = (
    BASE_DIR
    / "screenshots"
)


# ============================================================
# VOICE
# ============================================================

WAKE_WORD = "jarvis"


# ============================================================
# CONFIRMATION
# ============================================================

REQUIRE_CONFIRMATION_FOR = {
    "shutdown",
    "restart",
    "send_message",
    "post_content",
    "purchase",
}
