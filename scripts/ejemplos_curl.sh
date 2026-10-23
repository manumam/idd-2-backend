#!/usr/bin/env bash
set -euo pipefail
base="${API_URL:-http://127.0.0.1:8000}"
curl --fail-with-body -sS "$base/equipos/ARG"
curl --fail-with-body -sS "$base/jugadores?equipo=ARG&limit=2&skip=0"
curl --fail-with-body -sS "$base/jugadores/ARG-10"
curl --fail-with-body -sS "$base/partidos/P-001"
curl --fail-with-body -sS "$base/partidos/P-001/eventos?limit=2"
curl --fail-with-body -sS "$base/sedes/S-04/goleadores?confederacion=CONMEBOL&limit=2"
curl --fail-with-body -sS "$base/sesiones/SES-DEMO"
curl --fail-with-body -sS "$base/partidos/P-001/estadisticas?desde=2030-06-24T20:00:00Z&hasta=2030-06-24T20:05:00Z&ventana=1m"
curl --fail-with-body -sS "$base/health"
# Escenarios esperados de error: no usar --fail para poder inspeccionar el cuerpo.
curl -sS -i "$base/equipos/arg"                  # 400 antes de consultar
curl -sS -i "$base/sesiones/SES-HITO10AUSENTE"   # 404 si Redis está disponible
# Invalidación reproducible sobre una sesión de prueba (204 en ambas ejecuciones):
curl -sS -i -X DELETE "$base/sesiones/SES-HITO10TEST"
curl -sS -i -X DELETE "$base/sesiones/SES-HITO10TEST"
