from __future__ import annotations


def page_layer(page_number: int, role: str) -> str:
    role_norm = role.strip().upper().replace(" ", "_")
    return f"CADREAM-P{int(page_number):02d}-{role_norm}"
