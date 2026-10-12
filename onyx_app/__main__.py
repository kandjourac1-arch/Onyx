"""Permet de lancer Onyx avec ``python -m onyx_app``."""

from .server import run_terminal_mode, run_web_mode

import argparse
import threading


def main() -> None:
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


if __name__ == "__main__":
    main()
