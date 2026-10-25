# ======================================
# JARVIS RAG INGEST v4
# FUNCTION-LEVEL CODE INDEXER
# ======================================

import ast
from pathlib import Path

import chromadb
from rag.embedder import get_embedder

from config import CHROMA_DIR


BASE_DIR = Path(__file__).resolve().parent.parent


print("[RAG] Loading local ONNX embedding model...")

model = get_embedder()

print("[RAG] Embedding model ready.")


client = chromadb.PersistentClient(
    path=str(CHROMA_DIR)
)

collection = client.get_or_create_collection(
    name="local_docs"
)


IGNORE_DIRS = {
    "venv",
    "__pycache__",
    "models",
    "chroma",
    "profile",
    "CacheStorage",
    "generated_images",
    "screenshots",
    "node_modules",
    ".git"
}


SUPPORTED_TEXT_FILES = {
    ".py",
    ".js",
    ".ts",
    ".json",
    ".html",
    ".css",
    ".md",
    ".txt"
}


def relative_source(path: Path):
    try:
        return str(
            path.relative_to(BASE_DIR)
        )
    except Exception:
        return str(path)


def read_text(path: Path):
    try:
        return path.read_text(
            encoding="utf-8",
            errors="ignore"
        )
    except Exception:
        return ""


def chunk_generic_text(
    text,
    chunk_lines=80
):
    lines = text.splitlines()

    chunks = []

    for start in range(
        0,
        len(lines),
        chunk_lines
    ):
        end = min(
            start + chunk_lines,
            len(lines)
        )

        content = "\n".join(
            lines[start:end]
        )

        if not content.strip():
            continue

        chunks.append({
            "type": "chunk",
            "name": "",
            "start_line": start + 1,
            "end_line": end,
            "content": content
        })

    return chunks


def extract_python_units(
    path: Path,
    text: str
):
    try:
        tree = ast.parse(text)
    except Exception:
        return chunk_generic_text(text)

    lines = text.splitlines()

    units = []

    # ----------------------------------
    # module-level imports/context
    # ----------------------------------

    header_end = min(
        100,
        len(lines)
    )

    header = "\n".join(
        lines[:header_end]
    )

    if header.strip():
        units.append({
            "type": "module_header",
            "name": path.name,
            "start_line": 1,
            "end_line": header_end,
            "content": header
        })

    # ----------------------------------
    # functions/classes
    # ----------------------------------

    for node in ast.walk(tree):

        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef
            )
        ):
            continue

        start_line = getattr(
            node,
            "lineno",
            None
        )

        end_line = getattr(
            node,
            "end_lineno",
            None
        )

        if not start_line:
            continue

        if not end_line:
            end_line = min(
                start_line + 80,
                len(lines)
            )

        content = "\n".join(
            lines[
                start_line - 1:
                end_line
            ]
        )

        if not content.strip():
            continue

        if isinstance(
            node,
            ast.ClassDef
        ):
            unit_type = "class"
        else:
            unit_type = "function"

        units.append({
            "type": unit_type,
            "name": getattr(
                node,
                "name",
                ""
            ),
            "start_line": start_line,
            "end_line": end_line,
            "content": content
        })

    return units


def build_chunks_for_file(
    path: Path
):
    text = read_text(path)

    if not text.strip():
        return []

    if path.suffix.lower() == ".py":
        return extract_python_units(
            path,
            text
        )

    return chunk_generic_text(
        text
    )


def ingest_path(target_path=None):
    base = Path(target_path).resolve() if target_path else BASE_DIR
    print()
    print(f"🔥 JARVIS RAG INGEST STARTED on {base}")
    print()

    total_chunks = 0
    total_files = 0

    target_files = []
    if base.is_file():
        target_files.append((base.parent, [], [base.name]))
    else:
        target_files = list(base.walk())

    for root, dirs, files in target_files:

        dirs[:] = [
            d
            for d in dirs
            if d not in IGNORE_DIRS
        ]

        for filename in files:

            path = root / filename

            if (
                path.suffix.lower()
                not in SUPPORTED_TEXT_FILES
            ):
                continue

            chunks = build_chunks_for_file(
                path
            )

            if not chunks:
                continue

            docs = []
            ids = []
            metas = []

            rel_source = relative_source(path)

            for index, chunk in enumerate(
                chunks
            ):

                content = chunk["content"]

                docs.append(content)

                chunk_id = (
                    f"{rel_source}"
                    f"::{chunk['type']}"
                    f"::{chunk['name']}"
                    f"::{chunk['start_line']}"
                )

                ids.append(chunk_id)

                metas.append({
                    "source": str(path),
                    "relative_source": rel_source,
                    "file": path.name,
                    "extension": path.suffix.lower(),
                    "chunk": index,
                    "unit_type": chunk["type"],
                    "symbol": chunk["name"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"]
                })

            embeddings = model.encode(
                docs,
                show_progress_bar=False
            ).tolist()

            collection.upsert(
                ids=ids,
                documents=docs,
                embeddings=embeddings,
                metadatas=metas
            )

            total_files += 1
            total_chunks += len(docs)

            print(
                f"Indexed: {rel_source} "
                f"({len(docs)} units)"
            )

    print()
    print(
        f"COMPLETE: {total_files} files, "
        f"{total_chunks} chunks"
    )
    return {"files": total_files, "chunks": total_chunks}


def ingest():
    return ingest_path(BASE_DIR)


if __name__ == "__main__":
    ingest()