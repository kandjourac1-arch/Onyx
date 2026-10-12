"""
SYNAPSE-X : Mémoire Vectorielle / RAM, Régulateur d'Entropie SOPHIA et Moteur Spéculatif.
"""

import math
from typing import List, Dict, Any


class MemoryManagerMDERI:
    """Gestionnaire de mémoire hybride : RAM courte durée + Base Vectorielle."""

    def __init__(self, ram_capacity: int = 15):
        self.ram_buffer: List[Dict[str, str]] = []
        self.ram_capacity = ram_capacity
        # Note : ChromaDB ou FAISS s'intègre ici pour la mémoire long terme
        self.vector_store = []  # Simulation légère pour démonstration

    def add_to_ram(self, role: str, content: str):
        if len(self.ram_buffer) >= self.ram_capacity:
            self.ram_buffer.pop(0)
        self.ram_buffer.append({"role": role, "content": content})

    def get_context_snapshot(self) -> List[Dict[str, str]]:
        return list(self.ram_buffer)

    def search_similar_past_conversations(self, query: str, top_k: int = 3) -> List[str]:
        # Simulation d'un retrieval vectoriel ultra-rapide (< 10 ms)
        results = []
        for item in self.vector_store:
            if any(word in item.lower() for word in query.lower().split() if len(word) > 3):
                results.append(item)
                if len(results) >= top_k:
                    break
        return results


class SophiaEntropyRegulator:
    """Régulateur d'humeur : Ajuste dynamiquement la température pour éviter répétitions et hallucinations."""

    def __init__(self, base_temp: float = 0.7, min_temp: float = 0.2, max_temp: float = 1.0):
        self.base_temp = base_temp
        self.min_temp = min_temp
        self.max_temp = max_temp

    def calculate_token_entropy(self, logprobs: List[float]) -> float:
        """Calcule l'entropie de Shannon sur la distribution de probabilités des tokens."""
        if not logprobs:
            return 0.0
        entropy = 0.0
        for lp in logprobs:
            p = math.exp(lp)
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy

    def adjust_temperature(self, current_entropy: float, repetition_detected: bool = False) -> float:
        """
        Ajuste la température :
        - Entropie élevée (modèle confus) -> Baisser la température.
        - Répétition détectée -> Monter la température pour débloquer le modèle.
        """
        if repetition_detected:
            return min(self.max_temp, self.base_temp + 0.25)
        
        if current_entropy > 2.5:
            # Trop d'incertitude : recentrer
            return max(self.min_temp, self.base_temp - 0.2)
        elif current_entropy < 0.5:
            # Trop déterministe / risque de boucle
            return min(self.max_temp, self.base_temp + 0.1)

        return self.base_temp


class FulgurSpeculativeConfig:
    """Configuration du Moteur Spéculatif FULGUR."""

    def __init__(self, draft_model_name: str = "Qwen/Qwen2.5-0.5B-Instruct", main_model_name: str = "Qwen/Qwen2.5-9B-Instruct"):
        # Bon alignement de tokenizer garanti en utilisant Qwen 0.5B comme Draft Model
        self.draft_model_name = draft_model_name
        self.main_model_name = main_model_name
        self.num_speculative_tokens = 4
        self.use_kv_cache = True

    def get_generation_settings(self) -> Dict[str, Any]:
        return {
            "draft_model": self.draft_model_name,
            "main_model": self.main_model_name,
            "num_speculative_tokens": self.num_speculative_tokens,
            "use_cache": self.use_kv_cache
        }