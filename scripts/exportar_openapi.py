#!/usr/bin/env python3
"""Contrato generado de la aplicación, sin acceder a las bases."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml
from app.main import app

if __name__ == "__main__":
    destino = Path(__file__).resolve().parents[1] / "openapi/openapi.yaml"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(yaml.safe_dump(app.openapi(), allow_unicode=True, sort_keys=False))
    print(destino)
