"""
devtools/lcca_codec.py

Pure encode/decode for .lcca binary chunk files.
No SafeChunkEngine dependency — standalone codec.

Binary format:
  MAGIC (4 bytes: 0x4C 0x43 0x43 0x41 = "LCCA")
  + zlib-compressed UTF-8 JSON (level 6)
"""

import json
import zlib
from pathlib import Path

MAGIC = b"\x4c\x43\x43\x41"


def decode_bytes(raw: bytes) -> dict:
    """Decode raw .lcca bytes → dict. Supports binary and plain-JSON formats."""
    if raw[:4] == MAGIC:
        try:
            return json.loads(zlib.decompress(raw[4:]).decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Corrupt LCCA binary data: {e}")
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Not a valid LCCA or JSON file: {e}")


def decode_lcca(path: Path) -> dict:
    """Read a .lcca file and return its data as a dict."""
    return decode_bytes(path.read_bytes())


def encode_dict(data: dict) -> bytes:
    """Encode a dict → MAGIC + zlib-compressed JSON bytes (always binary)."""
    compressed = zlib.compress(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        level=6,
    )
    return MAGIC + compressed


def encode_json_str(json_str: str) -> bytes:
    """
    Parse a JSON string and encode to binary .lcca format.
    Raises ValueError if invalid JSON or root is not a dict.
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"Root must be a JSON object, not {type(data).__name__}.")
    return encode_dict(data)


def is_binary(path: Path) -> bool:
    """Return True if the file uses LCCA binary format."""
    try:
        return path.read_bytes()[:4] == MAGIC
    except Exception:
        return False


