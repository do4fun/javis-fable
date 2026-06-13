"""Bus d'événements asynchrone (asyncio).

Petit médiateur publish/subscribe qui servira à chaîner les futurs modules :
``stt → llm → tts``. Chaque module publie des événements typés sur le bus ;
les abonnés réagissent sans se connaître mutuellement (couplage faible).

Volontairement minimal : pas de file persistante, pas de garantie de
livraison au-delà du process. Tout est en mémoire, en localhost.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("jarvis.bus")

# Un handler reçoit la charge utile de l'événement et peut être asynchrone.
Handler = Callable[[Any], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> Callable[[], None]:
        """Abonne un handler à un type d'événement.

        Retourne une fonction de désabonnement.
        """
        self._subs[event].append(handler)

        def _unsub() -> None:
            try:
                self._subs[event].remove(handler)
            except ValueError:
                pass

        return _unsub

    async def publish(self, event: str, payload: Any = None) -> None:
        """Publie un événement ; les handlers sont exécutés en parallèle.

        Une exception dans un handler est loguée mais n'interrompt pas les
        autres (isolation des erreurs).
        """
        handlers = list(self._subs.get(event, ()))
        if not handlers:
            return

        results = await asyncio.gather(
            *(h(payload) for h in handlers), return_exceptions=True
        )
        for h, res in zip(handlers, results):
            if isinstance(res, Exception):
                log.exception("Handler %r a échoué sur '%s': %r", h, event, res)

    def clear(self) -> None:
        """Vide tous les abonnements (utile entre deux sessions/tests)."""
        self._subs.clear()
