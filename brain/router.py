# brain/router.py
"""CognitiveRouter — Routage cognitif connecté à SynapseX et Nexus."""

from typing import Any, Dict, Optional

from tools.algorithms.prompt_optimizer import PromptOptimizer


class CognitiveRouter:
    """Route les requêtes vers le profil LLM optimal via SynapseX + scoring mots-clés."""

    def __init__(self, synapse=None, nexus=None):
        self.synapse = synapse
        self.nexus = nexus
        self.optimizer = PromptOptimizer()
        self._init_profiles()

    def _init_profiles(self):
        self.profiles = {
            "codage": {
                "directive": "Tu es un ingénieur logiciel expert. Produis du code propre, optimisé et sans bavardage.",
                "temperature": 0.2,
                "max_tokens": 2048,
            },
            "donnees": {
                "directive": "Tu es un expert Data Analyst et NLP. Analyse les jeux de données et génère des synthèses.",
                "temperature": 0.2,
                "max_tokens": 1500,
            },
            "planification": {
                "directive": "Tu es un gestionnaire de projet IA. Décompose les objectifs en étapes claires.",
                "temperature": 0.3,
                "max_tokens": 1500,
            },
            "raisonnement": {
                "directive": "Raisonne étape par étape (Chain of Thought) avant la réponse finale.",
                "temperature": 0.3,
                "max_tokens": 1500,
            },
            "systeme": {
                "directive": (
                    "Tu es l'interface système Root. "
                    "Pour ouvrir une app : [LAUNCH: nom_application]. "
                    "Pour l'état PC : [STATUS: pc]."
                ),
                "temperature": 0.0,
                "max_tokens": 100,
            },
            "web": {
                "directive": "Tu es un assistant de recherche web. Synthétise de manière factuelle.",
                "temperature": 0.4,
                "max_tokens": 1024,
            },
            "creatif": {
                "directive": "Tu es un assistant créatif. Sois original et expressif.",
                "temperature": 0.8,
                "max_tokens": 2048,
            },
            "factuel": {
                "directive": "Donne une réponse claire, synthétique et directe.",
                "temperature": 0.5,
                "max_tokens": 1024,
            },
            "conversation": {
                "directive": "Tu es ONYX. Sois amical, concis et naturel.",
                "temperature": 0.7,
                "max_tokens": 512,
            },
            "fichier": {
                "directive": "Pour lire un fichier local : [READ_FILE: chemin]. Ne génère aucun autre texte.",
                "temperature": 0.0,
                "max_tokens": 150,
            },
        }
        self.keywords = {
            "codage": ["code", "python", "fonction", "script", "bug", "erreur", "refactor", "classe"],
            "donnees": ["statistique", "données", "csv", "json", "tendance", "graphe", "dataset"],
            "planification": ["planifie", "étapes", "objectif", "projet", "tâches", "roadmap"],
            "raisonnement": ["pourquoi", "explique", "comment", "analyse", "résous", "logique"],
            "systeme": ["lance", "ouvre", "exécute", "cmd", "powershell", "ferme", "statut"],
            "web": ["cherche", "web", "site", "url", "http", "recherche", "actualité"],
            "creatif": ["invente", "histoire", "idée", "imagine", "créatif", "poème"],
            "conversation": ["bonjour", "salut", "comment va", "hello", "hi"],
            "fichier": ["lis", "fichier", "ouvre le fichier", "analyse le fichier"],
            "factuel": ["qui est", "quel est", "combien", "date", "définition"],
        }
        self._synapse_mode_map = {
            "SYSTEM_ACTION": "systeme",
            "CODE_GEN": "codage",
            "CONVERSATION": "conversation",
        }

    def analyze(self, query: str) -> dict:
        """Retourne le profil le plus adapté."""
        if self.nexus:
            query = self.nexus.compress_prompt(query)
        else:
            query = self.optimizer.compress_prompt(query)

        if self.synapse:
            intent = self.synapse.analyze_intent(query)
            mapped = self._synapse_mode_map.get(intent.get("mode"))
            if mapped:
                profile = self.profiles.get(mapped)
                if profile:
                    return {**profile, "synapse_mode": intent.get("mode")}

        query_lower = query.lower()
        scores = {cat: 0 for cat in self.keywords}
        for category, words in self.keywords.items():
            for word in words:
                if word in query_lower:
                    scores[category] += 1

        best = max(scores, key=scores.get)
        if scores[best] > 0:
            return self.profiles.get(best, self.profiles["factuel"])
        return self.profiles["factuel"]

    def route(self, query: str) -> Dict[str, Any]:
        profile = self.analyze(query)
        if self.synapse:
            profile["intent"] = self.synapse.analyze_intent(query)
        return profile


# Alias rétrocompatibilité
FastIntentRouter = CognitiveRouter
