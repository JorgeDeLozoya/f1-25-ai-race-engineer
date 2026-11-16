"""Empaqueta el addon en un archivo .swoftyaddon listo para arrastrar a Swofty Launcher."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_FILE = ROOT.parent / "jorgedelo.ai-race-engineer.swoftyaddon"

INCLUDE_FILES = [
    "swofty.json",
    "swofty_helper.py",
    "config.json",
    "run_engineer.bat",
    "stop_engineer.bat",
    "simulate_udp.py",
    "README.md",
    "bin/engineer-helper.exe",
    "bin/engineer-helper",
    "bin/HelperShim.cs",
]


def build_package() -> Path:
    with zipfile.ZipFile(OUT_FILE, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE_FILES:
            p = ROOT / rel
            if p.exists():
                zf.write(p, arcname=rel)
        for f in (ROOT / "engineer").rglob("*"):
            if f.is_file() and not f.name.endswith(".pyc") and "__pycache__" not in str(f):
                zf.write(f, arcname=str(f.relative_to(ROOT)).replace("\\", "/"))
    print(f"Addon empaquetado en: {OUT_FILE} ({OUT_FILE.stat().st_size:,} bytes)")
    return OUT_FILE


if __name__ == "__main__":
    build_package()
