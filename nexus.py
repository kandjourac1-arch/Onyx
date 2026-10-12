"""
Onyx V2 - Nexus Data Bus (Centralisateur des sous-systèmes)
"""

from typing import Dict, Any
from memory_manager import OnyxMemoryManager
from skills.kairos import KairosEngine
from skills.synapse import SynapseXRouter

class NexusDataBus:
    """Centralise et coordonne la Mémoire, Kairos, Synapse X et les Outils Système."""

    def __init__(self):
        self.memory = OnyxMemoryManager()
        self.kairos = KairosEngine()
        self.synapse = SynapseXRouter()

    def prepare_context(self, user_query: str) -> Dict[str, Any]:
        """Combine la mémoire, le temps Kairos et le routage Synapse X."""
        time_context = self.kairos.get_current_time_context()
        intent = self.synapse.analyze_intent(user_query)
        memory_context = self.memory.get_context_for_prompt()
        enriched_prompt = self.synapse.enrich_prompt(user_query, intent, time_context)

        return {
            "intent": intent,
            "time_context": time_context,
            "memory_context": memory_context,
            "enriched_prompt": enriched_prompt
        }