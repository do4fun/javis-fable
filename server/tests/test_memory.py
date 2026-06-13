"""Tests de la mémoire SQLite (F4.2). Base temporaire, isolée."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from modules.memory import Memory  # noqa: E402


@pytest.fixture
def mem(tmp_path):
    m = Memory(tmp_path / "mem.sqlite")
    yield m
    m.close()


def test_turns_roundtrip(mem):
    mem.add_turn("user", "Bonjour")
    mem.add_turn("assistant", "Salut !")
    recent = mem.recent_turns(12)
    assert recent == [
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Salut !"},
    ]


def test_profile_persists_across_instances(tmp_path):
    path = tmp_path / "mem.sqlite"
    m1 = Memory(path)
    m1.set_profile("prenom", "Camille")
    m1.close()
    # Réouverture (simule un redémarrage du serveur).
    m2 = Memory(path)
    assert m2.get_profile().get("prenom") == "Camille"
    m2.close()


def test_purge_all(mem):
    mem.add_turn("user", "x")
    mem.set_profile("prenom", "Alex")
    mem.set_summary("résumé")
    mem.purge_all()
    assert mem.recent_turns() == []
    assert mem.get_profile() == {}
    assert mem.get_summary() == ""


def test_prune_keeps_last(mem):
    for i in range(20):
        mem.add_turn("user", f"msg {i}")
    mem.prune_to(5)
    recent = mem.recent_turns(100)
    assert len(recent) == 5
    assert recent[-1]["content"] == "msg 19"


def test_memory_commands(mem):
    from app import handle_memory_command

    # Mémorise le prénom puis le restitue.
    r = handle_memory_command("Je m'appelle Camille", mem)
    assert "Camille" in r
    assert mem.get_profile()["prenom"] == "Camille"

    ask = handle_memory_command("Comment je m'appelle ?", mem)
    assert "Camille" in ask

    # « oublie tout » purge la base.
    forget = handle_memory_command("Oublie tout", mem)
    assert "effacé" in forget
    assert mem.get_profile() == {}
