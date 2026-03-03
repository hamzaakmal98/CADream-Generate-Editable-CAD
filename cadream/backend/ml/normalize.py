from __future__ import annotations


def normalize_dxf_bytes(source_dxf_bytes: bytes) -> bytes:
    """Normalization hook for future DXF cleanup stages.

    Current implementation is identity to keep pipeline deterministic.
    """
    return source_dxf_bytes
