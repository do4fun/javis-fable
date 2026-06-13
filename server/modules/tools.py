"""Outils locaux exposés au LLM (F4.2).

Appelés via la balise ``[tool:nom(args)]`` (cf. ``tags.ToolEvent``). Tous
locaux : ``heure_date``, ``calcul``, ``minuteur``. La météo (``meteo``) et toute
requête réseau sont **désactivées par défaut**, derrière le drapeau
``allow_network``.

Chaque outil renvoie une chaîne courte, prête à être dite à l'oral.
"""

from __future__ import annotations

import ast
import datetime as _dt
import operator
import re

_CALL_RE = re.compile(r"\s*([a-zA-Z_]+)\s*\((.*)\)\s*$", re.DOTALL)

# Opérateurs autorisés pour le calcul (évaluation sûre, pas de eval()).
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expr: str) -> float:
    """Évalue une expression arithmétique simple sans exécuter de code."""
    node = ast.parse(expr, mode="eval").body
    return _eval_node(node)


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("expression non autorisée")


def _say_number(n: float) -> str:
    """Format oral d'un nombre (entier si possible)."""
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f"{n:.2f}".rstrip("0").rstrip(".")


def heure_date(arg: str = "") -> str:
    now = _dt.datetime.now()
    return now.strftime("Il est %H heures %M.").replace(" 0", " ")


def date_du_jour(arg: str = "") -> str:
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = [
        "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre",
    ]
    now = _dt.datetime.now()
    return f"On est {jours[now.weekday()]} {now.day} {mois[now.month - 1]}."


def calcul(expr: str) -> str:
    try:
        result = _safe_eval(expr)
        return f"Ça fait {_say_number(result)}."
    except Exception:
        return "Je n'ai pas réussi à faire ce calcul."


def meteo(arg: str = "", allow_network: bool = False) -> str:
    if not allow_network:
        return "La météo a besoin du réseau, et il est désactivé pour ta vie privée."
    # Implémentation réseau volontairement absente (hors-ligne par défaut).
    return "La météo en ligne n'est pas configurée."


# Table des outils (hors minuteur, traité à part car asynchrone/planifié).
_REGISTRY = {
    "heure_date": heure_date,
    "date": date_du_jour,
    "date_du_jour": date_du_jour,
    "calcul": calcul,
}


def parse_call(raw: str) -> tuple[str, str] | None:
    """Extrait ``(nom, args)`` d'un contenu de balise ``nom(args)``."""
    m = _CALL_RE.match(raw.strip())
    if not m:
        # Tolère « nom » sans parenthèses.
        name = raw.strip()
        return (name, "") if name else None
    return m.group(1), m.group(2).strip().strip("\"'")


def execute(raw: str, allow_network: bool = False) -> str | None:
    """Exécute un appel d'outil et renvoie une réponse orale (ou None).

    ``minuteur`` n'est pas géré ici (planification asynchrone côté pipeline) ;
    on renvoie None pour le déléguer à l'appelant.
    """
    parsed = parse_call(raw)
    if not parsed:
        return None
    name, args = parsed

    if name == "minuteur":
        return None  # géré par le pipeline (F4.2/F5.1)
    if name == "meteo":
        return meteo(args, allow_network=allow_network)

    fn = _REGISTRY.get(name)
    if fn is None:
        return None
    return fn(args)


def parse_minuteur_seconds(raw: str) -> float | None:
    """Interprète l'argument d'un ``minuteur(...)`` en secondes."""
    parsed = parse_call(raw)
    if not parsed or parsed[0] != "minuteur":
        return None
    args = parsed[1].lower()
    total = 0.0
    for value, unit in re.findall(r"(\d+)\s*(h|min|m|s|sec|secondes?|minutes?|heures?)", args):
        v = int(value)
        if unit.startswith("h"):
            total += v * 3600
        elif unit.startswith("s"):
            total += v
        else:  # minutes
            total += v * 60
    if total == 0:
        # Nombre nu → secondes.
        m = re.search(r"\d+", args)
        if m:
            total = float(m.group())
    return total or None
