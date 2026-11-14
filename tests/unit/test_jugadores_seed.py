"""Importación de planteles: válida antes de escribir y no altera el torneo."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('jugadores_seed', ROOT / 'scripts/cargar_jugadores.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def test_snapshot_cubre_planteles_con_fechas_bson_y_nombres_de_fuente():
    docs = seed.preparar()
    assert len(docs) == 1248
    assert len({d['equipo']['_id'] for d in docs}) == 48
    assert len({d['_id'] for d in docs}) == 1248
    arg = next(d for d in docs if d['_id'] == 'ARG-10')
    assert 'MESSI' in arg['apellido'].upper()
    assert arg['fecha_nacimiento'].year == 1987


def test_rechaza_snapshot_modificado_antes_de_conectar(tmp_path):
    shutil.copytree(seed.DATA, tmp_path / 'snapshot')
    source = tmp_path / 'snapshot/source/players.tsv'
    source.write_text(source.read_text() + '\n')
    with pytest.raises(ValueError, match='snapshot'):
        seed.preparar(tmp_path / 'snapshot')


def test_rechaza_dorsales_duplicados_aun_con_hash_correcto(tmp_path):
    data = tmp_path / 'snapshot'
    shutil.copytree(seed.DATA, data)
    source = data / 'source/players.tsv'
    with source.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        fields, rows = reader.fieldnames, list(reader)
    rows[1]['#'] = rows[0]['#']
    with source.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    provenance = json.loads((data / 'players-provenance.json').read_text())
    provenance['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    (data / 'players-provenance.json').write_text(json.dumps(provenance))
    with pytest.raises(ValueError, match='duplicado'):
        seed.preparar(data)


def test_carga_solo_jugadores_sin_borrar_ni_importar_resultados():
    db = MagicMock()
    seed.cargar(db, seed.preparar())
    db.equipos.assert_not_called()
    db.partidos.assert_not_called()
    assert set(call[0].split('.')[0] for call in db.mock_calls) == {'jugadores'}
    db.jugadores.delete_many.assert_not_called()
    db.jugadores.drop.assert_not_called()
