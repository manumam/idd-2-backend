#!/usr/bin/env python3
"""Usa API_HOST y API_PORT de .env o del proceso, sin recarga automática."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from app.config.settings import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port)
