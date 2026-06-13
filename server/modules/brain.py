"""Cerveau conversationnel via Ollama (F4.1).

Réponses intelligentes, expressives, en flux. Le LLM tourne en local (Ollama,
http://localhost:11434). Le persona « Jarvis » est chargé depuis
``server/prompts/system.md`` ; il impose le balisage d'expression
(``[emo:...]`` en tête, ``[geste:...]`` en cours de texte).

Ce module gère :
- la vérification de disponibilité (avec message d'aide) ;
- le streaming des tokens depuis Ollama, **annulable** (barge-in) ;
- le repli rule-based (``fallback_brain``) si Ollama est injoignable.

L'orchestration balises → émotions/TTS est faite par l'appelant (app/pipeline),
qui consomme les tokens via le parseur ``tags.StreamTagParser``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from . import fallback_brain

log = logging.getLogger("jarvis.brain")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.md"


class BrainUnavailable(Exception):
    """Ollama est injoignable ou le modèle est absent."""


class Brain:
    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        # La variable d'env (Docker compose) prime sur la config.
        host = os.environ.get("JARVIS_OLLAMA_HOST") or cfg.get("host", "http://localhost:11434")
        self.host = host.rstrip("/")
        self.model = cfg.get("model", "llama3.1:8b")
        self.timeout = float(cfg.get("timeout", 30))
        self.system_prompt = self._load_prompt()
        self._tutoiement = cfg.get("tutoiement", True)

    def _load_prompt(self) -> str:
        try:
            return PROMPT_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            log.warning("Persona introuvable (%s) — prompt minimal.", PROMPT_PATH)
            return "Tu es Jarvis, un assistant vocal français. Réponds court."

    async def available(self) -> tuple[bool, str]:
        """Vérifie Ollama et la présence du modèle. Renvoie (ok, message)."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self.host}/api/tags")
                r.raise_for_status()
                models = [m.get("name", "") for m in r.json().get("models", [])]
        except Exception as e:
            return False, (
                f"Ollama injoignable sur {self.host} ({e}). "
                "Installe-le depuis https://ollama.com et lance le service."
            )
        # Tolère les variantes de tag (llama3.1:8b vs llama3.1).
        base = self.model.split(":")[0]
        if not any(self.model == m or m.startswith(base) for m in models):
            return False, f"Modèle '{self.model}' absent. Lance : ollama pull {self.model}"
        return True, "ok"

    async def stream(
        self,
        user_text: str,
        history: list[dict] | None = None,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        """Streame les tokens de la réponse. Repli rule-based si indisponible.

        Lève/encapsule les erreurs réseau en basculant sur ``fallback_brain``.
        """
        messages = [{"role": "system", "content": self._render_system()}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        try:
            async for tok in self._stream_ollama(messages, cancel):
                yield tok
            return
        except BrainUnavailable as e:
            log.warning("Bascule sur le cerveau de repli : %s", e)
        except Exception as e:  # robustesse : toute panne → repli
            log.exception("Erreur Ollama (%s) → repli.", e)

        # Repli rule-based : on émet la réponse d'un bloc.
        yield fallback_brain.respond(user_text)

    def _render_system(self) -> str:
        note = "" if self._tutoiement else "\n\n(Vouvoie l'utilisateur.)"
        return self.system_prompt + note

    async def _stream_ollama(
        self, messages: list[dict], cancel: asyncio.Event | None
    ) -> AsyncIterator[str]:
        payload = {"model": self.model, "messages": messages, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", f"{self.host}/api/chat", json=payload
                ) as resp:
                    if resp.status_code != 200:
                        raise BrainUnavailable(f"HTTP {resp.status_code}")
                    async for line in resp.aiter_lines():
                        if cancel is not None and cancel.is_set():
                            log.info("Génération LLM annulée (barge-in).")
                            return
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if data.get("done"):
                            return
                        tok = data.get("message", {}).get("content", "")
                        if tok:
                            yield tok
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise BrainUnavailable(str(e)) from e
