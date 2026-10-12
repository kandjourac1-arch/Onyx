# brain/synapse.py
"""
SYNAPSE-X : Routage Cognitif Neural, Cache KV avec TTL, Recherche LTM,
Régulation d'Entropie Sophia et Configuration Spéculative Fulgur.
"""

import time
import math
import os
import json
from typing import Dict, Any, List, Optional, Tuple


class KVCache:
    """Cache en mémoire indexé par clé avec Time-To-Live (TTL) pour accélérer les requêtes récurrentes."""

    def __init__(self, ttl: int = 300):
        self.cache: Dict[str, Tuple[float, str]] = {}
        self.ttl = ttl

    def get(self, key: str) -> Optional[str]:
        if key in self.cache:
            timestamp, value = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None

    def set(self, key: str, value: str):
        self.cache[key] = (time.time(), value)

    def clear(self):
        self.cache.clear()


class SophiaEntropyRegulator:
    """Régulateur d'entropie dynamique : Ajuste la température d'inférence en fonction de l'incertitude."""

    def __init__(self, base_temp: float = 0.7, min_temp: float = 0.15, max_temp: float = 1.0):
        self.base_temp = base_temp
        self.min_temp = min_temp
        self.max_temp = max_temp
        self.recent_tokens: List[str] = []

    def calculate_token_entropy(self, logprobs: List[float]) -> float:
        """Calcule l'entropie de Shannon sur les log-probabilités."""
        if not logprobs:
            return 0.0
        entropy = 0.0
        for lp in logprobs:
            try:
                p = math.exp(lp)
                if p > 0:
                    entropy -= p * math.log2(p)
            except Exception:
                continue
        return entropy

    def adjust_temperature(self, current_entropy: float = 0.0, repetition_detected: bool = False) -> float:
        """
        - Si répétition détectée : monte la température pour débloquer le modèle.
        - Si entropie trop forte (> 2.5) : baisse la température pour recentrer.
        - Si entropie trop basse (< 0.5) : monte légèrement pour éviter le figement.
        """
        if repetition_detected:
            return min(self.max_temp, self.base_temp + 0.3)

        if current_entropy > 2.5:
            return max(self.min_temp, self.base_temp - 0.25)
        elif 0 < current_entropy < 0.5:
            return min(self.max_temp, self.base_temp + 0.15)

        return self.base_temp


class FulgurSpeculativeConfig:
    """Configuration du décodage spéculatif Draft / Main Model."""

    def __init__(
        self,
        draft_model_name: str = "qwen2.5-coder-0.5b-instruct",
        main_model_name: str = "qwen2.5-7b-instruct",
        num_speculative_tokens: int = 4
    ):
        self.draft_model_name = draft_model_name
        self.main_model_name = main_model_name
        self.num_speculative_tokens = num_speculative_tokens
        self.use_kv_cache = True

    def get_settings(self) -> Dict[str, Any]:
        return {
            "draft_model": self.draft_model_name,
            "main_model": self.main_model_name,
            "num_speculative_tokens": self.num_speculative_tokens,
            "use_cache": self.use_kv_cache
        }


class SynapseXCore:
    """
    SynapseXCore : Noyau neural unifié d'Onyx V2 intégrant :
    - Routage d'intention cognitif (SYSTEM_ACTION, CODE_GEN, CONVERSATION, etc.)
    - KVCache haute performance (avec TTL de 300s)
    - Recherche de contexte en mémoire long terme (LTM)
    - Régulateur de température Sophia
    - Configuration spéculative Fulgur
    """

    def __init__(self, ltm_file_path: str = "ltm.json", cache_ttl: int = 300):
        self.cache = KVCache(ttl=cache_ttl)
        self.entropy_regulator = SophiaEntropyRegulator()
        self.fulgur = FulgurSpeculativeConfig()
        self.ltm_file_path = ltm_file_path

    # --- Cache ---
    def get_cached_response(self, key: str) -> Optional[str]:
        return self.cache.get(key)

    def set_cached_response(self, key: str, value: str):
        self.cache.set(key, value)

    # --- Analyse d'Intention & Routage ---
    def analyze_intent(self, user_query: str) -> Dict[str, Any]:
        query_lower = user_query.lower()

        # Actions système
        if any(kw in query_lower for kw in ["lance", "ouvre", "exécute", "ferme", "powershell", "cmd", "redémarre", "éteint", "volume", "luminosité"]):
            return {"mode": "SYSTEM_ACTION", "priority": "HIGH", "use_tools": True, "category": "system"}

        # Programmation / Code
        elif any(kw in query_lower for kw in ["code", "python", "fonction", "script", "bug", "erreur", "refactor", "classe", "import", "def ", "class ", "json", "c++"]):
            return {"mode": "CODE_GEN", "priority": "MEDIUM", "use_tools": False, "category": "coding"}

        # Recherche web / Actualités
        elif any(kw in query_lower for kw in ["cherche", "actualité", "news", "météo", "cours", "prix", "web"]):
            return {"mode": "WEB_QUERY", "priority": "MEDIUM", "use_tools": True, "category": "web"}

        # Conversation standard
        return {"mode": "CONVERSATION", "priority": "LOW", "use_tools": False, "category": "conversation"}

    def enrich_prompt(self, user_query: str, intent: Dict[str, Any], time_context: str) -> str:
        return (
            f"[SYNAPSE X - ROUTE: {intent.get('mode', 'CONVERSATION')}]\n"
            f"[HORODATAGE KAIROS: {time_context}]\n"
            f"REQUÊTE UTILISATEUR: {user_query}"
        )

    # --- Recherche Long Term Memory (LTM) ---
    # Référence au MemoryManager pour recherche améliorée (injecté par NexusCore)
    _memory_manager = None

    @classmethod
    def set_memory_manager(cls, mm) -> None:
        cls._memory_manager = mm

    def search_ltm(self, username: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        # Délégation vers MemoryManager.search_ltm_smart si disponible
        if self._memory_manager:
            try:
                results = self._memory_manager.search_ltm_smart(username, query, limit=limit)
                if results:
                    return results
            except Exception as e:
                print(f"[SynapseXCore] Erreur recherche LTM : {e}")

        # Fallback : recherche simple fichier ltm.json
        if not os.path.exists(self.ltm_file_path):
            return []
        try:
            with open(self.ltm_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        query_words = set(re.findall(r'\b\w{4,}\b', query.lower()))
        if not query_words:
            return []

        results = []
        for conv in data.get("conversations", []):
            if conv.get("username") != username:
                continue
            combined = (conv.get("user", "") + " " + conv.get("assistant", "")).lower()
            score = sum(1 for w in query_words if w in combined)
            if score > 0:
                results.append((score, conv))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    # --- Régulation de température & Décodage spéculatif ---
    def adjust_temperature(self, base_temp: float = 0.7, repetition_detected: bool = False) -> float:
        return self.entropy_regulator.adjust_temperature(repetition_detected=repetition_detected)

    def get_fulgur_config(self) -> Dict[str, Any]:
        return self.fulgur.get_settings()


# Alias pour rétrocompatibilité
SynapseX = SynapseXCore
SynapseXRouter = SynapseXCore
