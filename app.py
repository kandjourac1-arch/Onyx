"""Point d'entrée rétrocompatible du serveur Onyx.

Le code applicatif vit désormais dans :mod:`onyx_app.server`. Ce petit
module conserve ``python app.py`` et ``from app import ...`` pour les scripts
existants, tout en laissant l'IDE indexer un vrai package Python.
"""

from onyx_app.server import *  # noqa: F401,F403
from onyx_app.server import app, run_terminal_mode, run_web_mode


if __name__ == "__main__":
    import argparse
    import threading

    parser = argparse.ArgumentParser(description="Onyx V2")
    parser.add_argument("--terminal", "-t", action="store_true", help="Lancer en mode terminal")
    parser.add_argument("--web", "-w", action="store_true", help="Lancer en mode web uniquement")
    args = parser.parse_args()

    if args.terminal:
        run_terminal_mode()
    elif args.web:
        run_web_mode()
    else:
        web_thread = threading.Thread(target=run_web_mode, daemon=True)
        web_thread.start()
        print("[Onyx V2] Interface web démarrée en arrière-plan sur http://localhost:5000")
        run_terminal_mode()
