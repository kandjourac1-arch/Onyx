"""
Onyx V2 - Synapse X (Moteur de Routage Cognitif et Stratégies de Prompt)
"""

from typing import Dict, Any

class SynapseXRouter:
    """Analyse les requêtes pour déterminer la stratégie d'exécution optimale."""

    def analyze_intent(self, user_query: str) -> Dict[str, Any]:
        """Détermine l'intention de la requête utilisateur."""
        query_lower = user_query.lower()
        
        # Mots-clés d'action système
        if any(keyword in query_lower for keyword in ["ouvre", "lance", "exécute", "ferme", "power-shell", "cmd", "steam"]):
            return {"mode": "SYSTEM_ACTION", "priority": "HIGH", "use_tools": True}
        
        # Mots-clés de programmation / code
        elif any(keyword in query_lower for keyword in ["code", "python", "bug", " script", "fonction", "json", "c++"]):
            return {"mode": "CODE_GEN", "priority": "MEDIUM", "use_tools": False}
        
        # Mode conversationnel ou factuel par défaut
        return {"mode": "CONVERSATION", "priority": "LOW", "use_tools": False}

    def enrich_prompt(self, user_query: str, intent: Dict[str, Any], time_context: str) -> str:
        """Enrichit la requête avant son envoi au LLM avec les données Synapse X."""
        return (
            f"[SYNAPSE X - ROUTE: {intent['mode']}]\n"
            f"[HORODATAGE KAIROS: {time_context}]\n"
            f"REQUÊTE UTILISATEUR: {user_query}"
        )