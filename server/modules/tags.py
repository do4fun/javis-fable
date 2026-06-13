"""Parseur de balises d'expression en flux (F4.1).

Le LLM balise ses réponses (cf. ``server/prompts/system.md``) :
- ``[emo:NOM]`` en tête → émotion ;
- ``[geste:NOM]`` en cours de texte → geste ponctuel ;
- ``[tool:nom(args)]`` → appel d'outil (F4.2).

Ces balises sont retirées du texte avant la synthèse vocale (jamais
prononcées). Le parseur fonctionne en **streaming** : on lui pousse des
fragments de tokens (potentiellement coupés au milieu d'une balise) et il
renvoie des évènements typés + le texte « propre » au fil de l'eau.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TAG_RE = re.compile(r"\[(emo|geste|tool):([^\]]*)\]")


@dataclass
class TextEvent:
    text: str


@dataclass
class EmotionEvent:
    name: str
    intensity: float = 1.0


@dataclass
class GestureEvent:
    name: str


@dataclass
class ToolEvent:
    raw: str  # contenu brut « nom(args) », interprété en F4.2


Event = TextEvent | EmotionEvent | GestureEvent | ToolEvent


class StreamTagParser:
    """Machine à états tolérante aux balises coupées entre deux tokens."""

    def __init__(self) -> None:
        self._buf = ""  # tampon où peut subsister un début de balise

    def feed(self, chunk: str) -> list[Event]:
        """Pousse un fragment de texte, renvoie les évènements complets."""
        self._buf += chunk
        events: list[Event] = []

        while True:
            open_idx = self._buf.find("[")
            if open_idx == -1:
                # Pas de balise en cours : tout le tampon est du texte propre.
                if self._buf:
                    events.append(TextEvent(self._buf))
                    self._buf = ""
                break

            # Texte propre avant la balise.
            if open_idx > 0:
                events.append(TextEvent(self._buf[:open_idx]))
                self._buf = self._buf[open_idx:]

            close_idx = self._buf.find("]")
            if close_idx == -1:
                # Balise incomplète : on attend le prochain chunk.
                # Garde-fou : si ce n'est pas un début de balise plausible,
                # on libère le '[' comme texte pour ne pas bloquer.
                if not re.match(r"\[(e|g|t)?[a-z]*:?[^\]]*$", self._buf):
                    events.append(TextEvent(self._buf))
                    self._buf = ""
                break

            tag = self._buf[: close_idx + 1]
            self._buf = self._buf[close_idx + 1 :]
            ev = self._parse_tag(tag)
            if ev is not None:
                events.append(ev)
            else:
                # Balise inconnue : on la traite comme du texte (rare).
                events.append(TextEvent(tag))

        return events

    def flush(self) -> list[Event]:
        """Vide le tampon en fin de génération."""
        if not self._buf:
            return []
        out = [TextEvent(self._buf)]
        self._buf = ""
        return out

    @staticmethod
    def _parse_tag(tag: str) -> Event | None:
        m = _TAG_RE.fullmatch(tag.strip())
        if not m:
            return None
        kind, value = m.group(1), m.group(2).strip()
        if kind == "emo":
            return EmotionEvent(name=value or "neutre")
        if kind == "geste":
            return GestureEvent(name=value)
        if kind == "tool":
            return ToolEvent(raw=value)
        return None
