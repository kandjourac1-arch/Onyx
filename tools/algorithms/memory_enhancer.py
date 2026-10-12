"""
tools/algorithms/memory_enhancer.py
Gestionnaire de mémoire cognitive avancée et profil utilisateur
"""

import json
import time
import os
import math
from datetime import datetime

class MemoryEnhancer:
    def __init__(self, memory_dir: str = "memory"):
        self.memory_dir = memory_dir
        os.makedirs(memory_dir, exist_ok=True)
        self.profile_path = os.path.join(memory_dir, "user_profile.json")
        self.profile = self.load_user_profile()

    def load_user_profile(self) -> dict:
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"preferences": {}, "interaction_count": 0, "topics_interest": {}}

    def save_user_profile(self):
        with open(self.profile_path, "w", encoding="utf-8") as f:
            json.dump(self.profile, f, ensure_ascii=False, indent=2)

    def record_episodic_memory(self, user_id: str, event: str, emotion: str = "neutral") -> dict:
        """1. Enregistreur de mémoire épisodique avec horodatage."""
        return {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "event": event,
            "emotion": emotion
        }

    def cluster_semantic_memories(self, memories: list[str]) -> dict:
        """2. Regroupement thématique simple des souvenirs."""
        clusters = {"technique": [], "personnel": [], "general": []}
        for mem in memories:
            m_lower = mem.lower()
            if any(k in m_lower for k in ["code", "python", "bug", "erreur", "systeme"]):
                clusters["technique"].append(mem)
            elif any(k in m_lower for k in ["je suis", "j'aime", "mon nom", "préfère"]):
                clusters["personnel"].append(mem)
            else:
                clusters["general"].append(mem)
        return clusters

    def apply_memory_decay(self, timestamp_epoch: float, half_life_days: float = 7.0) -> float:
        """3. Calcul de pondération temporelle (dégradation selon la courbe d'oubli)."""
        now = time.time()
        age_days = (now - timestamp_epoch) / 86400.0
        decay_factor = math.pow(0.5, age_days / half_life_days)
        return round(decay_factor, 4)

    def auto_summarize_conversation(self, messages: list[dict]) -> str:
        """4. Résumé automatique de conversations."""
        topics = []
        for msg in messages:
            content = msg.get("content", "")
            if len(content) > 20:
                topics.append(content[:50] + "...")
        return f"Discussion portant sur {len(messages)} messages. Sujets abordés: " + " | ".join(topics[:3])

    def update_user_profile(self, user_input: str):
        """5. Construction et mise à jour du profil utilisateur."""
        self.profile["interaction_count"] = self.profile.get("interaction_count", 0) + 1
        
        # Apprentissage des centres d'intérêt
        words = user_input.lower().split()
        for w in words:
            if len(w) > 5:
                self.profile["topics_interest"][w] = self.profile["topics_interest"].get(w, 0) + 1
                
        self.save_user_profile()

    def learn_implicit_preference(self, key: str, value: str):
        """6. Apprentissage implicite des préférences."""
        self.profile["preferences"][key] = value
        self.save_user_profile()

    def rebuild_ltm_context(self, query: str, limit: int = 3) -> str:
        """7. Reconstruction du contexte pertinent depuis la mémoire LTM."""
        if not self.profile.get("preferences"):
            return ""
        prefs = [f"{k}: {v}" for k, v in self.profile.get("preferences", {}).items()]
        return "[PRÉFÉRENCES UTILISATEUR]\n" + "\n".join(prefs)

    def score_fact_importance(self, fact: str) -> float:
        """8. Calcul d'un score d'importance d'un fait."""
        score = 0.5
        if any(k in fact.lower() for k in ["nom", "toujours", "important", "jamais", "préférence"]):
            score += 0.4
        return min(1.0, score)

    def ebbinghaus_retention(self, elapsed_hours: float) -> float:
        """9. Implémentation formelle de la courbe d'oubli d'Ebbinghaus."""
        if elapsed_hours <= 0:
            return 1.0
        # R = e^(-t / S)
        retention = math.exp(-elapsed_hours / 24.0)
        return round(retention, 4)

    def build_knowledge_graph_node(self, subject: str, relation: str, obj: str) -> dict:
        """10. Construction de nœud dans le graphe de connaissances local."""
        return {
            "subject": subject.strip().lower(),
            "relation": relation.strip().lower(),
            "object": obj.strip().lower(),
            "created_at": datetime.now().isoformat()
        }
