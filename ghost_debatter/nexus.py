"""
NEXUS-Ω : Interception, Filtrage, Tool Matching et Compression.
Exécution ultra-rapide (< 5 ms) sur CPU.
"""

import re
import sqlite3
import asyncio
from typing import Dict, Any, Optional, Tuple, List


class FlashRouter:
    """Standardiste : Répond directement aux calculs ou requêtes simples."""
    
    def __init__(self):
        # Expressions mathématiques simples (ex: 25*4, 12+8/2)
        self.math_pattern = re.compile(r"^\s*([\d\.\s\+\-\*\/\(\)]+)\s*$")

    def route(self, query: str) -> Optional[Dict[str, Any]]:
        cleaned = query.strip().lower()
        
        # 1. Traitement direct des expressions mathématiques
        if self.math_pattern.match(query) and any(op in query for op in "+-*/"):
            try:
                # Évaluation sécurisée des caractères mathématiques
                result = eval(query, {"__builtins__": None}, {})
                return {"type": "FAST_RESPONSE", "content": f"{query} = {result}"}
            except Exception:
                pass

        # 2. Salutations rapides ou requêtes courantes
        if cleaned in ["salut", "bonjour", "hello", "hi", "ping"]:
            return {"type": "FAST_RESPONSE", "content": "Bonjour ! Comment puis-je vous aider aujourd'hui ?"}

        return None  # Nécessite un traitement avancé


class ContextCompressor:
    """Rédacteur : Supprime le bruit linguistique et les tics de langage."""

    FILLERS = [
        r"\bdu coup\b", r"\ben fait\b", r"\beuh\b", r"\bbon\b", r"\bs'il te plaît\b",
        r"\bs'il vous plaît\b", r"\bstp\b", r"\bsvp\b", r"\bdis moi\b", r"\bacctuellement\b",
        r"\bgenre\b", r"\bfaçon\b"
    ]

    def __init__(self):
        self.pattern = re.compile("|".join(self.FILLERS), flags=re.IGNORECASE)

    def compress(self, text: str) -> str:
        # Suppression des tics de langage
        cleaned = self.pattern.sub("", text)
        # Normalisation des espaces multiples
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned if cleaned else text


class ToolMatcher:
    """Mécanicien : Détecte et exécute les outils Python préenregistrés."""

    def __init__(self):
        self.tools = {}

    def register_tool(self, name: str, keywords: List[str], func):
        self.tools[name] = {"keywords": keywords, "func": func}

    def match_and_execute(self, query: str) -> Optional[Dict[str, Any]]:
        query_lower = query.lower()
        for name, tool in self.tools.items():
            if any(kw in query_lower for kw in tool["keywords"]):
                try:
                    result = tool["func"](query)
                    return {"tool_name": name, "result": result}
                except Exception as e:
                    return {"tool_name": name, "error": str(e)}
        return None


class Scribe:
    """Secrétaire : Historisation SQLite asynchrone en arrière-plan."""

    def __init__(self, db_path: str = "history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    user_query TEXT,
                    compressed_query TEXT,
                    response TEXT
                )
            """)

    async def log_async(self, user_query: str, compressed_query: str, response: str):
        def _insert():
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO logs (user_query, compressed_query, response) VALUES (?, ?, ?)",
                    (user_query, compressed_query, response)
                )
        await asyncio.to_thread(_insert)