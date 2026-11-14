from collections import Counter, defaultdict
from itertools import combinations
from unittest.mock import MagicMock
import pytest
from scripts.cargar_inicio_mundial import preparar, cargar


def test_inicio_64_equipo_grupos_completos_y_eliminatorias_sin_ganadores():
    teams, matches = preparar()
    assert len(teams) == 64
    assert Counter(t['grupo'] for t in teams) == Counter({chr(65 + i): 4 for i in range(16)})
    by_group = defaultdict(list)
    assert len(matches) == 127
    for m in matches:
        assert m['estado'] == 'proximo' and m['resultado'] is None
        if m['fase'] == 'Grupos':
            by_group[m['grupo']].append(frozenset([m['local']['codigo'], m['visitante']['codigo']]))
        else:
            assert m['local'] is None and m['visitante'] is None
    for group, pairs in by_group.items():
        expected = {frozenset(pair) for pair in combinations([t['_id'] for t in teams if t['grupo'] == group], 2)}
        assert len(pairs) == 6 and set(pairs) == expected


def test_no_reinicia_torneo_ni_escribe_ante_partidos_existentes():
    db = MagicMock()
    db.partidos.count_documents.return_value = 1
    with pytest.raises(ValueError, match='Ya existen partidos'):
        cargar(db, *preparar())
    db.equipos.bulk_write.assert_not_called()
    db.partidos.bulk_write.assert_not_called()
