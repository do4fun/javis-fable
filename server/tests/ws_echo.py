"""Client de test manuel du WebSocket /ws (F0.2).

Envoie un ``user_text`` et affiche les trames reçues. Utile pour vérifier à la
main que le serveur répond, sans navigateur.

Usage :
    # 1. lance le serveur dans un terminal : `make run` (ou run.ps1)
    # 2. dans un autre terminal :
    python tests/ws_echo.py "Bonjour Jarvis"
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets  # noqa: E402

from core.protocol import ClientMsg, Envelope  # noqa: E402

URL = "ws://127.0.0.1:8000/ws"


async def main(text: str) -> None:
    async with websockets.connect(URL) as ws:
        # State initial annoncé par le serveur.
        print("←", await ws.recv())

        env = Envelope.make(ClientMsg.USER_TEXT, {"text": text})
        await ws.send(env.to_json())
        print("→", env.to_json())

        # On lit l'accusé de réception (et d'éventuels messages suivants).
        try:
            for _ in range(3):
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print("←", msg)
        except TimeoutError:
            pass


if __name__ == "__main__":
    phrase = sys.argv[1] if len(sys.argv) > 1 else "Bonjour Jarvis"
    asyncio.run(main(phrase))
