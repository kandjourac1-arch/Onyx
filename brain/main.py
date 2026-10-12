# brain/main.py
import os
import requests
from .dcl_engine import DoubleCerveauEngine

class OnyxOrchestrator:
    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1"):
        self.base_url = base_url.rstrip("/")
        self.model_ch = "qwen2.5-7b-instruct"
        self.dcl = DoubleCerveauEngine(base_url=self.base_url)
        print("[Onyx V2] Orchestrateur et moteur DCL prêts.")

    def route_intent(self, user_input: str) -> str:
        user_input_lower = user_input.lower()
        mots_cles_code = ["code", "refactor", "script", "fonction", "bug", "erreur", "python", "fix", "app.py", "main.py", "dcl_engine.py", "modifier", "créer"]
        if any(kw in user_input_lower for kw in mots_cles_code):
            return "EXPERT"
        elif len(user_input.split()) < 6:
            return "RAPIDE"
        return "MEDIUM"

    def _call_llm(self, prompt: str, system_prompt: str = "Tu es Onyx V2.", max_tokens: int = 500) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_ch,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens
        }
        try:
            res = requests.post(url, json=payload, timeout=60)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"].strip()
            return f"Erreur serveur ({res.status_code})"
        except Exception as e:
            return f"Erreur de connexion : {str(e)}"

    def process_request(self, user_input: str, target_file: str = None) -> str:
        intent = self.route_intent(user_input)
        if intent == "EXPERT":
            return self.dcl.traiter_demande(user_input, target_file)
        elif intent == "RAPIDE":
            return self._call_llm(user_input, system_prompt="Réponds de manière concise et directe.", max_tokens=150)
        else:
            return self._call_llm(user_input, system_prompt="Tu es Onyx V2, un assistant IA local performant.", max_tokens=500)

EliteLegalCabinetOrchestrator = OnyxOrchestrator