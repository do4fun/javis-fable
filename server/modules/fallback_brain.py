"""Cerveau de repli rule-based (F4.1).

Utilisé quand Ollama est injoignable : il ne « pense » pas, mais reste poli et
utile sur quelques intentions de base (salutations, heure/date, capacités).
Toutes les réponses respectent le balisage d'expression ``[emo:...]``.

Volontairement minimal et déterministe ; aucune dépendance réseau.
"""

from __future__ import annotations

import datetime as _dt
import re


def _now_phrase() -> str:
    now = _dt.datetime.now()
    return now.strftime("Il est %H heures %M.").replace(" 0", " ")


def respond(text: str) -> str:
    """Renvoie une réponse balisée à partir d'une heuristique simple."""
    t = text.lower().strip()

    if re.search(r"\b(bonjour|salut|coucou|hello|bonsoir)\b", t):
        return "[emo:joie][geste:salut] Salut ! Je tourne en mode dégradé là, mais je suis là. On fait quoi ?"

    if re.search(r"\b(quelle heure|l'heure|il est quelle)\b", t):
        return f"[emo:reflexion] {_now_phrase()}"

    if re.search(r"\b(quel jour|la date|on est quel)\b", t):
        jour = _dt.datetime.now().strftime("%A %d %B")
        return f"[emo:reflexion] On est {jour}."

    if re.search(r"\b(que sais-tu faire|tes capacités|tu peux faire quoi|aide)\b", t):
        return (
            "[emo:neutre] Je peux te parler, t'écouter et t'aider au quotidien. "
            "Mais mon cerveau principal est hors-ligne pour l'instant."
        )

    if re.search(r"\b(merci|super|génial|parfait)\b", t):
        return "[emo:joie] Avec plaisir !"

    if re.search(r"\b(au revoir|à plus|bye|salut)\b", t):
        return "[emo:joie][geste:salut] À bientôt !"

    # Réponse générique honnête.
    return (
        "[emo:tristesse] Désolé, mon cerveau principal n'est pas disponible là. "
        "Lance Ollama et réessaie."
    )
