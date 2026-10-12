"""
Onyx System - memory_manager.py
Gestionnaire de mémoire hybride :
- STM (Short-Term Memory) : Sauvegardé en continu dans memory/stm.json
- LTM (Long-Term Memory)  : Consolidation archivée dans memory/ltm.json tous les 10 échanges
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List


class OnyxMemoryManager:
    """Gère la persistance de la mémoire à court terme (STM) et à long terme (LTM)."""

    def __init__(self, memory_dir: str = "memory"):
        self.memory_dir = memory_dir
        self.stm_file = os.path.join(memory_dir, "stm.json")
        self.ltm_file = os.path.join(memory_dir, "ltm.json")

        if not os.path.exists(memory_dir):
            os.makedirs(memory_dir)

        self.stm = self._load_json(self.stm_file, default={"conversation_count": 0, "history": []})
        self.ltm = self._load_json(self.ltm_file, default={"consolidations": []})

    def _load_json(self, filepath: str, default: Dict[str, Any]) -> Dict[str, Any]:
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return default

    def _save_json(self, filepath: str, data: Dict[str, Any]) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_message(self, role: str, content: str) -> None:
        """Enregistre un message dans la STM et déclenche la LTM tous les 10 tours."""
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        self.stm["history"].append(entry)

        # On incrémente le compteur uniquement quand l'assistant répond (tour complet)
        if role.lower() in ["assistant", "onyx"]:
            self.stm["conversation_count"] += 1
            
            # Seuil de consolidation : tous les 10 échanges
            if self.stm["conversation_count"] > 0 and self.stm["conversation_count"] % 10 == 0:
                self._consolidate_to_ltm()

        self._save_json(self.stm_file, self.stm)

    def _consolidate_to_ltm(self) -> None:
        """Archive les 20 derniers messages (10 tours) dans la LTM."""
        last_10_turns = self.stm["history"][-20:]

        consolidation_entry = {
            "batch_id": self.stm["conversation_count"] // 10,
            "timestamp": datetime.now().isoformat(),
            "messages_count": len(last_10_turns),
            "snapshot": [
                {"role": msg["role"], "content": msg["content"]} for msg in last_10_turns
            ]
        }

        self.ltm["consolidations"].append(consolidation_entry)
        self._save_json(self.ltm_file, self.ltm)
        print(f"\n🧠 [LTM OK] Consolidation #{consolidation_entry['batch_id']} enregistrée dans {self.ltm_file}")

    def get_context_for_prompt(self, max_recent_messages: int = 10) -> str:
        """Génère le bloc de contexte à injecter dans le prompt système de Qwen."""
        # 1. Archives LTM
        ltm_summary = []
        for batch in self.ltm.get("consolidations", []):
            ltm_summary.append(f"--- Archive #{batch['batch_id']} ({batch['timestamp'][:10]}) ---")
            for msg in batch["snapshot"]:
                ltm_summary.append(f"{msg['role'].upper()}: {msg['content']}")

        ltm_text = "\n".join(ltm_summary) if ltm_summary else "Aucune archive long terme pour le moment."

        # 2. Fil récent STM
        recent_stm = self.stm["history"][-max_recent_messages:]
        stm_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent_stm])

        return f"""=== MÉMOIRE LONG TERME (LTM) ===
{ltm_text}

=== MÉMOIRE COURTE DÉROULANTE (STM) ===
{stm_text}"""

    def clear_stm(self) -> None:
        """Réinitialise la mémoire court terme si besoin."""
        self.stm = {"conversation_count": 0, "history": []}
        self._save_json(self.stm_file, self.stm)


if __name__ == "__main__":
    memory = OnyxMemoryManager()
    print("OnyxMemoryManager initialisé avec succès.")