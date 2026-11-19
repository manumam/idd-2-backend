#!/usr/bin/env python3
"""Seed de prueba: convocatorias simuladas de Argentina; conserva las existentes."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.cargar_alineaciones import main


if __name__ == '__main__':
    try:
        main(ROOT / 'data/fixture/alineaciones-argentina-demo.json')
    except Exception as exc:
        print(f'Seed interrumpido: {type(exc).__name__}. Revisar fixture, plantel y conectividad.', file=sys.stderr)
        sys.exit(1)
