"""Cerveau conversationnel (F4.1).

Deux providers interchangeables via ``config.yaml`` (llm.provider) :

  * ``"claude"``  — Anthropic API (claude-fable-5, etc.) ; nécessite la
                    variable d'env ``ANTHROPIC_API_KEY`` ou ``llm.api_key``.
  * ``"ollama"``  — Ollama local (http://localhost:11434) ; 100 % local,
                    aucune clé API.

Le persona « Jarvis » est chargé depuis ``server/prompts/system.md`` ; il
impose le balisage d'expression (``[emo:...]``, ``[geste:...]``).

Ce module gère :
- la vérification de disponibilité (clé API ou ping Ollama) ;
- le streaming des tokens, **annulable** (barge-in) ;
- le repli rule-based (``fallback_brain``) si le provider est indisponible.
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
    """Le provider LLM est injoignable ou mal configuré."""


class Brain:
    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        self._provider = cfg.get("provider", "ollama")
        self.model     = cfg.get("model", "llama3.1:8b")
        self.timeout   = float(cfg.get("timeout", 30))
        self.system_prompt = self._load_prompt()
        self._tutoiement   = cfg.get("tutoiement", True)

        # ── Ollama ────────────────────────────────────────────────────────────
        host = os.environ.get("JARVIS_OLLAMA_HOST") or cfg.get("host", "http://localhost:11434")
        self.host = host.rstrip("/")

        # ── Claude (Anthropic) ────────────────────────────────────────────────
        self._claude     = None
        self._claude_key = ""
        if self._provider == "claude":
            self._claude_key = (
                os.environ.get("ANTHROPIC_API_KEY") or cfg.get("api_key", "")
            )
            try:
                import anthropic as _anthropic  # importé lazily (dép. optionnelle)
                self._claude = _anthropic.AsyncAnthropic(api_key=self._claude_key)
            except ImportError:
                log.error(
                    "Package 'anthropic' manquant. "
                    "Lance : pip install anthropic  (ou pip install -r requirements.txt)"
                )

        log.info("Brain initialisé — provider=%s model=%s", self._provider, self.model)

    # ── Chargement du prompt ──────────────────────────────────────────────────

    def _load_prompt(self) -> str:
        try:
            return PROMPT_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            log.warning("Persona introuvable (%s) — prompt minimal.", PROMPT_PATH)
            return "Tu es Jarvis, un assistant vocal français. Réponds court."

    def _render_system(self) -> str:
        note = "" if self._tutoiement else "\n\n(Vouvoie l'utilisateur.)"
        return self.system_prompt + note

    # ── Disponibilité ─────────────────────────────────────────────────────────

    async def available(self) -> tuple[bool, str]:
        """Vérifie que le provider est joignable et configuré. Renvoie (ok, message)."""
        if self._provider == "claude":
            return self._check_claude()
        return await self._check_ollama()

    def _check_claude(self) -> tuple[bool, str]:
        if self._claude is None:
            return False, (
                "Package 'anthropic' manquant. "
                "Lance : pip install anthropic"
            )
        if not self._claude_key:
            return False, (
                "Clé API Anthropic manquante. "
                "Définis la variable d'env ANTHROPIC_API_KEY "
                "ou renseigne llm.api_key dans server/config.yaml."
            )
        return True, "ok"

    async def _check_ollama(self) -> tuple[bool, str]:
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
        base = self.model.split(":")[0]
        if not any(self.model == m or m.startswith(base) for m in models):
            return False, f"Modèle '{self.model}' absent. Lance : ollama pull {self.model}"
        return True, "ok"

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def stream(
        self,
        user_text: str,
        history: list[dict] | None = None,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        """Streame les tokens de la réponse. Repli rule-based si indisponible."""
        messages = [{"role": "system", "content": self._render_system()}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        try:
            if self._provider == "claude":
                async for tok in self._stream_claude(messages, cancel):
                    yield tok
            else:
                async for tok in self._stream_ollama(messages, cancel):
                    yield tok
            return
        except BrainUnavailable as e:
            log.warning("Bascule sur le cerveau de repli : %s", e)
        except Exception as e:
            log.exception("Erreur LLM provider=%s (%s) → repli.", self._provider, e)

        # Repli rule-based : réponse déterministe, émise d'un bloc.
        yield fallback_brain.respond(user_text)

    # ── Provider Claude ───────────────────────────────────────────────────────

    async def _stream_claude(
        self, messages: list[dict], cancel: asyncio.Event | None
    ) -> AsyncIterator[str]:
        if self._claude is None:
            raise BrainUnavailable("SDK anthropic non installé.")

        # L'API Anthropic sépare le prompt système des messages user/assistant.
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        conv   = [m for m in messages if m["role"] != "system"]

        try:
            import anthropic as _anthropic

            async with self._claude.messages.stream(
                model=self.model,
                max_tokens=350,   # 1-4 phrases orales → 350 tokens suffisent largement
                system=system or "",
                messages=conv,
            ) as stream:
                async for text in stream.text_stream:
                    if cancel is not None and cancel.is_set():
                        log.info("Génération Claude annulée (barge-in).")
                        return
                    yield text

        except _anthropic.AuthenticationError as e:
            raise BrainUnavailable(f"Clé API Anthropic invalide : {e}") from e
        except _anthropic.APIConnectionError as e:
            raise BrainUnavailable(f"Anthropic API injoignable : {e}") from e
        except _anthropic.APIStatusError as e:
            raise BrainUnavailable(f"Erreur API Anthropic {e.status_code} : {e.message}") from e

    # ── Provider Ollama ───────────────────────────────────────────────────────

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
                            log.info("Génération Ollama annulée (barge-in).")
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
