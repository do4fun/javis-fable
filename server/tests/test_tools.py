"""Tests des outils locaux (F4.2)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import tools  # noqa: E402


def test_calcul():
    assert tools.execute("calcul(2 + 3 * 4)") == "Ça fait 14."
    assert tools.execute("calcul(10 / 4)") == "Ça fait 2.5."


def test_calcul_rejects_code():
    # Pas d'exécution de code arbitraire.
    assert tools.execute("calcul(__import__('os'))") == "Je n'ai pas réussi à faire ce calcul."


def test_heure_date():
    out = tools.execute("heure_date()")
    assert out and "heures" in out


def test_meteo_blocked_by_default():
    out = tools.execute("meteo(Paris)", allow_network=False)
    assert "réseau" in out.lower()


def test_minuteur_parsing():
    assert tools.parse_minuteur_seconds("minuteur(3 minutes)") == 180
    assert tools.parse_minuteur_seconds("minuteur(45 secondes)") == 45
    assert tools.parse_minuteur_seconds("minuteur(2 h)") == 7200
    assert tools.parse_minuteur_seconds("calcul(2+2)") is None
