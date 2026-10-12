# brain/nexus.py
"""
NEXUS-Ω & Nexus Core : Bus central de données, interception ultra-rapide,
compression de contexte, Tool Matching et synchronisation multi-modules.
"""

import re
import sqlite3
import asyncio
import ast
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List, Callable


class FlashRouter:
    """Standardiste ultra-rapide (< 5 ms sur CPU) :
    Prend en charge instantanément les calculs arithmétiques basiques et les salutations.
    """

    def __init__(self):
        self.math_pattern = re.compile(r"^\s*([\d\.\s\+\-\*\/\(\)\%]+)\s*$")
        self.salutations = {"salut", "bonjour", "hello", "hi", "ping", "coucou", "hey"}

    def route(self, query: str) -> Optional[Dict[str, Any]]:
        cleaned = query.strip().lower()
        if self.math_pattern.match(query) and any(op in query for op in "+-*/%"):
            try:
                result = self._safe_math(query)
                return {
                    "type": "FAST_RESPONSE",
                    "source": "NEXUS-FlashRouter",
                    "content": f"{query.strip()} = {result}"
                }
            except Exception:
                pass

        if cleaned in self.salutations:
            return {
                "type": "FAST_RESPONSE",
                "source": "NEXUS-FlashRouter",
                "content": "Bonjour ! Je suis Onyx. Comment puis-je vous assister aujourd'hui ?"
            }

        return None

    @staticmethod
    def _safe_math(expression: str):
        """Évalue uniquement un AST arithmétique, sans eval ni accès Python."""
        tree = ast.parse(expression, mode="eval")
        allowed = (ast.Expression, ast.Constant, ast.UnaryOp, ast.BinOp, ast.Add, ast.Sub,
                   ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.USub, ast.UAdd)
        for node in ast.walk(tree):
            if not isinstance(node, allowed) or (isinstance(node, ast.Constant) and not isinstance(node.value, (int, float))):
                raise ValueError("expression non autorisée")
        return FlashRouter._eval_node(tree.body)

    @staticmethod
    def _eval_node(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp):
            value = FlashRouter._eval_node(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        left, right = FlashRouter._eval_node(node.left), FlashRouter._eval_node(node.right)
        operations = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right,
                      ast.Mult: lambda: left * right, ast.Div: lambda: left / right,
                      ast.Mod: lambda: left % right, ast.Pow: lambda: left ** right}
        for operator, action in operations.items():
            if isinstance(node.op, operator):
                result = action()
                if abs(result) > 10**12:
                    raise ValueError("résultat hors limites")
                return result
        raise ValueError("opération non autorisée")


class ContextCompressor:
    """Rédacteur : Supprime le bruit linguistique, tics de langage et mots de remplissage."""

    FILLERS = [
        r"\bdu coup\b", r"\ben fait\b", r"\beuh\b", r"\bbon\b", r"\bs'il te plaît\b",
        r"\bs'il vous plaît\b", r"\bstp\b", r"\bsvp\b", r"\bdis moi\b", r"\bactuellement\b",
        r"\bacctuellement\b", r"\bgenre\b", r"\bfaçon\b"
    ]

    def __init__(self):
        self.pattern = re.compile("|".join(self.FILLERS), flags=re.IGNORECASE)

    def compress(self, text: str) -> str:
        if not text:
            return ""
        cleaned = self.pattern.sub("", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned if cleaned else text


class ToolMatcher:
    """Mécanicien : Détecte et exécute les outils Python locaux enregistrés."""

    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}

    def register_tool(self, name: str, keywords: List[str], func: Callable):
        self.tools[name] = {"keywords": [k.lower() for k in keywords], "func": func}

    def match_and_execute(self, query: str) -> Optional[Dict[str, Any]]:
        query_lower = query.lower()
        for name, tool in self.tools.items():
            if any(kw in query_lower for kw in tool["keywords"]):
                try:
                    result = tool["func"](query)
                    return {"tool_name": name, "result": result, "success": True}
                except Exception as e:
                    return {"tool_name": name, "error": str(e), "success": False}
        return None


class Scribe:
    """Secrétaire : Historisation SQLite asynchrone pour l'audit et l'apprentissage continu."""

    def __init__(self, db_path: str = "history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        user_query TEXT,
                        compressed_query TEXT,
                        response TEXT,
                        module_used TEXT
                    )
                """)
        except Exception as e:
            print(f"[NEXUS Scribe] Avertissement init DB : {e}")

    def log_sync(self, user_query: str, compressed_query: str, response: str, module_used: str = "ONYX"):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO logs (user_query, compressed_query, response, module_used) VALUES (?, ?, ?, ?)",
                    (user_query, compressed_query, response, module_used)
                )
        except Exception as e:
            print(f"[NEXUS Scribe] Erreur log_sync : {e}")

    async def log_async(self, user_query: str, compressed_query: str, response: str, module_used: str = "ONYX"):
        await asyncio.to_thread(self.log_sync, user_query, compressed_query, response, module_used)


class NexusCore:
    """
    NexusCore : Le pont central unifié intégrant :
    - FlashRouter (calculs & salutations immédiats)
    - ContextCompressor (nettoyage)
    - ToolMatcher & Intentions d'outils
    - Scribe (persistance)
    - NexusDataBus (coordination Kairos, Synapse, Mémoire)
    """

    def __init__(self, memory_manager=None, kairos_engine=None, synapse_router=None, db_path: str = "history.db"):
        self.flash_router = FlashRouter()
        self.compressor = ContextCompressor()
        self.tool_matcher = ToolMatcher()
        self.scribe = Scribe(db_path=db_path)

        self.memory = memory_manager
        self.kairos = kairos_engine
        self.synapse = synapse_router

    def attach_subsystems(self, memory_manager=None, kairos_engine=None, synapse_router=None):
        """Permet l'injection de dépendances après instanciation si nécessaire."""
        if memory_manager:
            self.memory = memory_manager
        if kairos_engine:
            self.kairos = kairos_engine
        if synapse_router:
            self.synapse = synapse_router

    def check_fast_path(self, query: str) -> Optional[Dict[str, Any]]:
        """Vérifie si la requête peut être traitée sans LLM via le FlashRouter."""
        return self.flash_router.route(query)

    def compress(self, query: str) -> str:
        """Nettoie la requête utilisateur."""
        return self.compressor.compress(query)

    def prepare_context(self, user_query: str) -> Dict[str, Any]:
        """
        Coordonne la mémoire, le contexte temporel de Kairos et l'intention de Synapse X
        pour forger un prompt hautement contextuel et enrichi.
        """
        compressed_query = self.compress(user_query)

        time_context = self.kairos.get_time_context() if self.kairos and hasattr(self.kairos, "get_time_context") else datetime.now().strftime("%A %d %B %Y à %H:%M:%S")

        intent = {}
        if self.synapse and hasattr(self.synapse, "analyze_intent"):
            intent = self.synapse.analyze_intent(compressed_query)
        else:
            intent = {"mode": "CONVERSATION", "priority": "NORMAL"}

        memory_context = ""
        if self.memory and hasattr(self.memory, "get_context_for_prompt"):
            memory_context = self.memory.get_context_for_prompt()

        enriched_prompt = (
            f"[SYNAPSE-X // ROUTE: {intent.get('mode', 'STANDARD')}]\n"
            f"[KAIROS // CONTEXTE TEMPOREL: {time_context}]\n"
            f"REQUÊTE UTILISATEUR: {compressed_query}"
        )

        return {
            "original_query": user_query,
            "compressed_query": compressed_query,
            "intent": intent,
            "time_context": time_context,
            "memory_context": memory_context,
            "enriched_prompt": enriched_prompt
        }

    def detect_tool_intent(self, user_input: str, username: str = "Admin", tools_bridge: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Détection et dispatching des outils natifs (météo, news, email, tâches, etc.).
        Permet d'unifier la logique d'outils avec tools_bridge.
        """
        text_lower = user_input.lower()
        bridge = tools_bridge or {}

        # Météo
        if any(kw in text_lower for kw in ['météo', 'weather', 'quel temps', 'température', 'il fait']):
            get_weather_fn = bridge.get("get_weather")
            if callable(get_weather_fn):
                city_match = re.search(r'(?:météo|weather|temps)\s+(?:de|à|a|pour)?\s*([a-zA-ZÀ-ÿ\s\-]+)', text_lower)
                city = city_match.group(1).strip() if city_match else 'Paris'
                res = get_weather_fn(city)
                if isinstance(res, dict) and res.get("success"):
                    return "tool", f"Météo à {res.get('city', city)}: {res.get('temp', '?')}°C, {res.get('description', '')}, humidité {res.get('humidity', '?')}%, vent {res.get('wind_speed', '?')} m/s"
                elif isinstance(res, dict):
                    return "tool", f"Erreur : {res.get('error', 'Météo indisponible')}"

        # News
        if any(kw in text_lower for kw in ['actualité', 'actualités', 'news', 'info', 'infos', 'dernières nouvelles']):
            get_news_fn = bridge.get("get_news")
            if callable(get_news_fn):
                query = "actualités"
                for kw in ['actualités', 'actualité', 'news', 'info', 'infos']:
                    if kw in text_lower:
                        parts = text_lower.split(kw, 1)
                        if len(parts) > 1 and parts[1].strip():
                            query = parts[1].strip()
                        break
                articles = get_news_fn(query=query)
                if articles:
                    msg = "**Actualités récentes**\n\n"
                    for a in articles[:5]:
                        title = a.get("title", "Sans titre")
                        desc = (a.get("description") or "")[:150]
                        url = a.get("url", "#")
                        msg += f"• **{title}**\n  {desc}...\n  [Lire l'article]({url})\n\n"
                    return "tool", msg
                return "tool", "Aucune actualité trouvée à ce sujet."

        # Emails non lus
        if any(kw in text_lower for kw in ['lis mes mails', 'vérifie mes emails', 'montre mes emails', 'affiche mes mails']):
            read_emails_fn = bridge.get("read_emails")
            if callable(read_emails_fn):
                res = read_emails_fn(limit=5, unread_only=True)
                if isinstance(res, dict) and res.get("success") and res.get("emails"):
                    msg = "**Derniers emails non lus**\n\n"
                    for i, e in enumerate(res["emails"], 1):
                        sender = e.get("from", "Inconnu")
                        subj = e.get("subject", "Sans sujet")
                        snip = e.get("snippet", "(vide)")
                        msg += f"{i}. **De :** {sender}\n   **Sujet :** {subj}\n   **Aperçu :** {snip}\n\n"
                    return "tool", msg
                return "tool", "Aucun nouvel email non lu trouvé."

        # ToolMatcher personnalisé
        matched = self.tool_matcher.match_and_execute(user_input)
        if matched:
            if matched.get("success"):
                return "tool", f"Outil : résultat [{matched['tool_name']}]:\n{matched['result']}"
            else:
                return "tool", f"Erreur outil [{matched['tool_name']}]: {matched.get('error')}"

        return None, None


class ToolHandlers:
    """Gestionnaire utilitaire pour encapsuler et connecter les fonctions outils."""

    @staticmethod
    def format_weather(result: dict) -> str:
        if result.get("success"):
            return f"Météo à {result.get('city')}: {result.get('temp')}°C, {result.get('description')}, humidité {result.get('humidity')}%, vent {result.get('wind_speed')} m/s"
        return f"Erreur : {result.get('error', 'Erreur météo')}"

    @staticmethod
    def format_news(articles: list) -> str:
        if not articles:
            return "Aucune actualité trouvée."
        msg = "**Actualités récentes**\n\n"
        for a in articles[:5]:
            msg += f"• **{a.get('title', 'Titre')}**\n  {(a.get('description') or '')[:150]}...\n  [Lien]({a.get('url', '#')})\n\n"
        return msg
