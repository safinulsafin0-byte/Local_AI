"""JARVIS Ingestion Module for Documents and Images."""
from .extractor import extract, is_binary_or_corrupt

__all__ = ["extract", "is_binary_or_corrupt"]

