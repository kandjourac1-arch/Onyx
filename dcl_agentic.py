"""
Onyx V2 - Moteur Agentique DCL (dcl_agentic.py)
Gère le calcul de complexité Sphinx, le streaming réactif et l'interruption réflexe par Watchdog Linter.
"""

import ast
import io
import json
import threading
import time
import requests
from pyflakes import api as pyflakes_api
from pyflakes import reporter as pyflakes_reporter


class SphinxRouter:
    """Évaluateur de complexité algorithmic & intentionnel."""

    @staticmethod
    def calculate_complexity(user_input: str) -> float:
        """Calcule un score de complexité entre 0.0 et 1.0."""
        score = 0.0
        words = user_input.split()

        # 1. Facteur longueur
        score += min(len(words) / 50.0, 0.3)

        # 2. Mots-clés de complexité technique
        tech_keywords = [
            "refactor", "optimiser", "architecture", "classe", "héritage",
            "async", "thread", "ast", "arbre", "bug", "exception", "algo", "dcl"
        ]
        matches = sum(1 for kw in tech_keywords if kw in user_input.lower())
        score += min(matches * 0.15, 0.4)

        # 3. Détection de code ou structure complexe dans la requête
        if "def " in user_input or "class " in user_input or "import " in user_input:
            score += 0.3

        return round(min(score, 1.0), 2)


class WatchdogLinter:
    """Surveille le flux de code en temps réel et déclenche une interruption en cas de faute."""

    def __init__(self):
        self.stop_event = threading.Event()
        self.last_checked_code = ""

    def check_syntax(self, code_buffer: str) -> list:
        """Exécute un contrôle pyflakes ultra-rapide en mémoire."""
        if not code_buffer.strip():
            return []
        
        warning_stream = io.StringIO()
        error_stream = io.StringIO()
        reporter = pyflakes_reporter.Reporter(warning_stream, error_stream)
        
        try:
            pyflakes_api.check(code_buffer, filename="buffer.py", reporter=reporter)
            output = warning_stream.getvalue() + error_stream.getvalue()
            return [line for line in output.splitlines() if line]
        except Exception:
            return []

    def start_monitoring(self, get_code_callback, on_error_callback):
        """Thread autonome exécuté à 20 Hz (toutes les 50ms)."""
        self.stop_event.clear()

        def worker():
            while not self.stop_event.is_set():
                current_code = get_code_callback()
                if current_code and current_code != self.last_checked_code:
                    self.last_checked_code = current_code
                    errors = self.check_syntax(current_code)
                    if errors:
                        # Interruption d'urgence du streaming
                        self.stop_event.set()
                        on_error_callback(errors, current_code)
                        break
                time.sleep(0.05)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return t

    def stop(self):
        self.stop_event.set()


class DCLAgenticEngine:
    """Moteur principal combinant streaming interrompable et architecture DCL."""

    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1"):
        self.base_url = base_url.rstrip("/")
        self.model_ch = "qwen2.5-7b-instruct"
        self.model_cb = "qwen2.5-coder-0.5b-instruct"
        self.router = SphinxRouter()
        self.watchdog = WatchdogLinter()

    def stream_call(self, model: str, prompt: str, system_prompt: str, on_token_callback, stop_event: threading.Event) -> str:
        """Génère du texte en HTTP SSE Streaming avec possibilité de coupure nette."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "stream": True
        }

        full_response = ""
        try:
            response = requests.post(url, json=payload, stream=True, timeout=60)
            for line in response.iter_lines():
                if stop_event.is_set():
                    print("\n[⚡ REFLEXE DCL] Interruption du stream transmise au serveur HTTP !")
                    break

                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        data_json = line_str[6:]
                        if data_json.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_json)
                            token = chunk["choices"][0]["delta"].get("content", "")
                            full_response += token
                            if on_token_callback:
                                on_token_callback(token)
                        except Exception:
                            continue
        except Exception as e:
            full_response += f"\n[Erreur Stream : {str(e)}]"

        return full_response

    def executer_demande(self, user_input: str, on_token_callback=None) -> str:
        # Étape 1 : Anayse de complexité Sphinx
        score = self.router.calculate_complexity(user_input)
        print(f"\n[Sphinx Router] Score de complexité : {score}")

        if score < 0.7:
            print("[Sphinx] Mode Standard / Rapide sélectionné.")
            stop_evt = threading.Event()
            return self.stream_call(
                model=self.model_ch,
                prompt=user_input,
                system_prompt="Tu es Onyx V2. Réponds de manière directe.",
                on_token_callback=on_token_callback,
                stop_event=stop_evt
            )

        # Étape 2 : Mode Expert DCL (Activation du Watchdog + Dual-Brain)
        print("[Sphinx] Mode Expert Agentique (DCL + Watchdog) activé.")
        
        # 1. Cerveau Haut (Planification)
        stop_evt_ch = threading.Event()
        print("\n[CH - Architecte 7B] Élaboration du plan...")
        plan = self.stream_call(
            model=self.model_ch,
            prompt=f"Instruction : {user_input}\nFournis uniquement un plan en 3 points concis.",
            system_prompt="Tu es l'Architecte. Donne uniquement un plan sans code.",
            on_token_callback=on_token_callback,
            stop_event=stop_evt_ch
        )

        # 2. Cerveau Bas (Exécution + Watchdog Linter)
        code_buffer = ""
        stop_evt_cb = threading.Event()

        def update_code(token):
            nonlocal code_buffer
            code_buffer += token
            if on_token_callback:
                on_token_callback(token)

        def on_linter_error(errors, code):
            print(f"\n[Réflexe Linter] Erreur syntaxe détectée en direct : {errors[0]}")
            print("[Réflexe Linter] Relancement immédiat de la correction...")

        # Démarrage de la surveillance asynchrone
        self.watchdog.start_monitoring(lambda: code_buffer, on_linter_error)

        print("\n[CB - Cerveau Bas 0.5B] Génération du code sous contrôle du Watchdog...")
        prompt_cb = f"[PLAN]\n{plan}\n\n[INSTRUCTION]\n{user_input}"
        code_final = self.stream_call(
            model=self.model_cb,
            prompt=prompt_cb,
            system_prompt="Tu es un compilateur Python. Rédige uniquement le code.",
            on_token_callback=update_code,
            stop_event=stop_evt_cb
        )

        self.watchdog.stop()
        return code_final


if __name__ == "__main__":
    agent = DCLAgenticEngine()
    
    def print_token(token):
        print(token, end="", flush=True)

    test_prompt = "Créer une classe Python pour gérer une file d'attente prioritaire avec des threads et gestion d'exceptions"
    print("--- TEST AGENTIQUE DCL ---")
    agent.executer_demande(test_prompt, on_token_callback=print_token)