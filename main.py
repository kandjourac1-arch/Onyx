"""
Onyx V2 - Orchestrateur Principal (pipeline brain/ unifié)
"""

import os
import requests

from brain import (
    NexusCore,
    KairosEngine,
    SynapseXCore,
    MemoryManager,
    DoubleCerveauEngine,
    CognitiveRouter,
    get_system_identity,
)


class OnyxOrchestrator:
    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1"):
        self.base_url = base_url.rstrip("/")
        self.model_ch = "qwen2.5-7b-instruct"

        self.memory = MemoryManager()
        self.kairos = KairosEngine()
        self.synapse = SynapseXCore()
        self.nexus = NexusCore(self.memory, self.kairos, self.synapse)
        self.router = CognitiveRouter(synapse=self.synapse, nexus=self.nexus)
        self.dcl = DoubleCerveauEngine(base_url=self.base_url)

        print("[Onyx V2] Pipeline brain/ initialisé (NEXUS + KAIROS + SYNAPSE X + DCL)")

    def route_intent(self, user_input: str) -> str:
        profile = self.router.analyze(user_input)
        mode = profile.get("synapse_mode") or profile.get("directive", "")[:20]
        if "codage" in str(profile.get("directive", "")).lower() or profile.get("temperature", 0.7) <= 0.2:
            code_kw = ["code", "refactor", "script", "fonction", "bug", "python", "fix"]
            if any(kw in user_input.lower() for kw in code_kw):
                return "EXPERT"
        if len(user_input.split()) < 6:
            return "RAPIDE"
        return "MEDIUM"

    def _call_llm(self, prompt: str, system_prompt: str = None, max_tokens: int = 500) -> str:
        system_prompt = system_prompt or get_system_identity()
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_ch,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        try:
            res = requests.post(url, json=payload, timeout=60)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"].strip()
            return f"Erreur serveur ({res.status_code})"
        except Exception as e:
            return f"Erreur de connexion : {str(e)}"

    def process_request(self, user_input: str, target_file: str = None) -> str:
        nexus_result = self.nexus.process(user_input)
        if nexus_result.get("handled"):
            return nexus_result["response"]

        cache_key = user_input.strip().lower()
        cached = self.synapse.get_cached(cache_key)
        if cached:
            return cached

        intent = self.route_intent(user_input)

        if intent == "EXPERT":
            print("\n[🧠 SPHINX] Mode Expert (Double-Cerveau DCL).")
            response = self.dcl.traiter_demande(user_input, target_file)
        elif intent == "RAPIDE":
            print("\n[⚡ SPHINX] Mode Rapide.")
            profile = self.router.analyze(user_input)
            ctx = self.nexus.prepare_context(user_input)
            response = self._call_llm(
                ctx,
                get_system_identity(profile["directive"], self.memory.get_context_for_prompt(max_recent=5)),
                max_tokens=150,
            )
        else:
            print("\n[⚙️ SPHINX] Mode Standard.")
            if self.kairos.is_complex_query(user_input):
                debate = self.kairos.run_debate(
                    user_input,
                    call_llm_fn=lambda p, s: self._call_llm(p, s, max_tokens=200),
                    mode="llm",
                )
                ctx = f"Consensus KAIROS : {debate['consensus']}\n\n{user_input}"
            else:
                ctx = self.nexus.prepare_context(user_input)
            profile = self.router.analyze(user_input)
            response = self._call_llm(
                ctx,
                get_system_identity(profile["directive"]),
                max_tokens=500,
            )

        if response:
            self.synapse.set_cached(cache_key, response)
            self.memory.add_message("user", user_input)
            self.memory.add_message("assistant", response)

        return response or "Aucune réponse générée."


EliteLegalCabinetOrchestrator = OnyxOrchestrator


if __name__ == "__main__":
    orchestrator = OnyxOrchestrator()
    reponse = orchestrator.process_request(
        "Rédige une fonction Python pour trier une liste de dictionnaires par clé"
    )
    print("\n[Résultat Onyx] :\n", reponse)
