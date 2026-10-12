# brain/__init__.py
"""
Package brain — Noyau cognitif unifié d'Onyx V2.
NEXUS / KAIROS / SYNAPSE X + Mémoire + Router + DCL.
"""

from .nexus import NexusCore, FlashRouter, ContextCompressor, ToolMatcher, Scribe, ToolHandlers
from .kairos import KairosEngine, LinguisticMirror, ConsensusEngine
from .synapse import SynapseXCore, KVCache, SophiaEntropyRegulator, FulgurSpeculativeConfig
from .memory import MemoryManager, CognitiveMemory
from .identity import get_system_identity, build_system_prompt, ONYX_PERSONALITY
from .router import CognitiveRouter, FastIntentRouter
from .dcl_engine import DoubleCerveauEngine

__all__ = [
    "NexusCore",
    "FlashRouter",
    "KairosEngine",
    "SynapseXCore",
    "MemoryManager",
    "DoubleCerveauEngine",
    "CognitiveRouter",
    "FastIntentRouter",
    "get_system_identity",
    "build_system_prompt",
    "ONYX_PERSONALITY",
    "ToolHandlers",
]
