# brain/memory.py
"""
Onyx V2 - Système de Mémoire Unifié Hybride & Adaptatif
- STM (Short-Term Memory) : Fenêtre glissante token-aware de conversation immédiate.
- LTM (Long-Term Memory) : Recherche hybride (TF-IDF + embeddings + récence) avec consolidation automatique.
- Profil & Faits Utilisateur (Facts Store) : Extraction et stockage permanent de faits personnels.
- Entité & Thème Extractor : Identification automatique d'entités, projets, préférences.
- Topic Boundary Detection : Découpage automatique des conversations par thème.
"""

import os
import re
import json
import time
import math
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set

try:
    import tiktoken
    _has_tiktoken = True
except ImportError:
    _has_tiktoken = False


class TokenCounter:
    """Compteur de tokens — utilise tiktoken si disponible, sinon estimation caractères/4."""
    _encoders: Dict[str, Any] = {}

    @classmethod
    def count(cls, text: str, model: str = "gpt-3.5-turbo") -> int:
        if not text:
            return 0
        try:
            if _has_tiktoken:
                if model not in cls._encoders:
                    try:
                        cls._encoders[model] = tiktoken.encoding_for_model(model)
                    except Exception:
                        cls._encoders[model] = tiktoken.encoding_for_model("gpt-3.5-turbo")
                return len(cls._encoders[model].encode(text))
        except Exception:
            pass
        return int(len(text) / 3.5) + 1

    @classmethod
    def truncate(cls, text: str, max_tokens: int, model: str = "gpt-3.5-turbo") -> str:
        if cls.count(text, model) <= max_tokens:
            return text
        words = text.split()
        while words and cls.count(" ".join(words), model) > max_tokens:
            words.pop()
        return " ".join(words)


class EntityExtractor:
    """Extracteur d'entités nommées — projets, langages, technologies, localisations."""

    PROJECT_PATTERN = re.compile(
        r"\b(?:mon projet|projet\s+:?|travaille sur|développe|création de)\s+([a-zA-ZÀ-ÿ0-9][\w\s\-\.']{3,50})",
        re.IGNORECASE
    )
    LANGUAGE_PATTERN = re.compile(
        r"\b(?:Python|JavaScript|TypeScript|Java|C\+\+|Go|Rust|Swift|Kotlin|Ruby|PHP|Rust|React|Vue|Angular|Svelte|Vue\.js|Next\.js|Node\.js|Flutter|Django|Flask|FastAPI|PyTorch|TensorFlow)\b",
        re.IGNORECASE
    )
    LOCATION_PATTERN = re.compile(
        r"\b(?:Paris|Lyon|Marseille|Nice|Toulouse|Montréal|Québec|Genève|Lausanne|Bruxelles|Conakry|Guinée|Sénégal|Mali|France|Suisse|Canada|États-Unis|USA|UK|Allemagne|Espagne|Italie|Espagne)\b",
        re.IGNORECASE
    )
    SKILL_PATTERN = re.compile(
        r"\b(?:développeur|développeuse|ingénieur|data scientist|product manager|designer|chef de projet| CTO|CEO|freelance|consultant|formateur|chercheur|journaliste|traducteur)\b",
        re.IGNORECASE
    )

    @classmethod
    def extract(cls, text: str) -> Dict[str, List[str]]:
        entities: Dict[str, List[str]] = {
            "projects": [],
            "languages": [],
            "locations": [],
            "skills": [],
            "technologies": []
        }
        if not text:
            return entities

        for m in cls.PROJECT_PATTERN.finditer(text):
            val = m.group(1).strip()
            if val and val not in entities["projects"]:
                entities["projects"].append(val)

        for m in cls.LANGUAGE_PATTERN.finditer(text):
            val = m.group(1).strip()
            if val and val.lower() not in [l.lower() for l in entities["languages"]]:
                entities["languages"].append(val.title())

        for m in cls.LOCATION_PATTERN.finditer(text):
            val = m.group(1).strip()
            if val and val not in entities["locations"]:
                entities["locations"].append(val)

        for m in cls.SKILL_PATTERN.finditer(text):
            val = m.group(1).strip()
            if val and val.lower() not in [s.lower() for s in entities["skills"]]:
                entities["skills"].append(val.lower())

        return entities


class TopicDetector:
    """Détection de boundaries thématiques pour segmentation conversationnelle."""

    TOPIC_KEYWORDS: Dict[str, List[str]] = {
        "code": ["code", "python", "function", "script", "débogage", "bug", "erreur", "programmation", "api", "déploiement"],
        "web": ["site", "web", "page", "recherche", "google", "actualité", "news", "url"],
        "system": ["volume", "ordinateur", "dossier", "fichier", "fenêtre", "processus", "tasklist", "répertoire"],
        "mail": ["email", "mail", "courriel", "message", "envoyer", "recevoir", "boîte"],
        "weather": ["météo", "temps", "pluie", "température", "humidité", "neige"],
        "finance": ["argent", "compte", "banque", "budget", "prix", "coût", "achat", "facture"],
        "personnel": ["je", "moi", "mon", "mes", "moi-même", "profil", "préférence", "souvenir"],
    }

    @classmethod
    def classify(cls, text: str) -> str:
        if not text:
            return "general"
        text_lower = text.lower()
        scores: Dict[str, int] = {}
        for topic, keywords in cls.TOPIC_KEYWORDS.items():
            scores[topic] = sum(1 for kw in keywords if kw in text_lower)
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general"

    @classmethod
    def detect_boundary(cls, messages: List[Dict[str, Any]], window_size: int = 4) -> List[int]:
        """Retourne les indices où un nouveau topic commence."""
        boundaries: List[int] = []
        if len(messages) < window_size * 2:
            return boundaries
        for i in range(window_size, len(messages), window_size):
            prev_window = " ".join(m.get("content", "") for m in messages[max(0, i - window_size):i])
            curr_window = " ".join(m.get("content", "") for m in messages[i:i + window_size])
            if curr_window and prev_window:
                prev_topic = cls.classify(prev_window)
                curr_topic = cls.classify(curr_window)
                if prev_topic != curr_topic:
                    boundaries.append(i)
        return boundaries


class MemoryManager:
    """
    Gestionnaire de Mémoire Avancé pour Onyx V2.
    - Stockage thread-safe
    - Extraction automatique et manuelle de faits (LTM Facts)
    - Fenêtre contextuelle glissante (STM Conversation)
    - Recherche sémantique pondérée (LTM Search)
    """

    def __init__(self, memory_dir: str = None):
        if memory_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if '__file__' in globals() else os.getcwd()
            memory_dir = os.path.join(base_dir, "memory")

        self.memory_dir = memory_dir
        os.makedirs(self.memory_dir, exist_ok=True)

        self.stm_file = os.path.join(self.memory_dir, "stm.json")
        self.ltm_file = os.path.join(self.memory_dir, "ltm.json")
        self.facts_file = os.path.join(self.memory_dir, "facts.json")

        self._lock = threading.RLock()

        self.stm = self._load_json(self.stm_file, default={"conversations": {}})
        self.ltm = self._load_json(self.ltm_file, default={"consolidations": []})
        self.user_facts = self._load_json(self.facts_file, default={"users": {}}).get("users", {})

    def _load_json(self, filepath: str, default: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            return data
                except Exception as e:
                    print(f"[MemoryManager] Erreur lecture {filepath}: {e}")
            return default

    def _save_json(self, filepath: str, data: Dict[str, Any]) -> None:
        with self._lock:
            try:
                temp_file = filepath + ".tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                if os.path.exists(filepath):
                    os.replace(temp_file, filepath)
                else:
                    os.rename(temp_file, filepath)
            except Exception as e:
                print(f"[MemoryManager] Erreur sauvegarde {filepath}: {e}")

    # ============================================================
    # 1. MÉMOIRE PROFIL & FAITS UTILISATEUR (LTM FACTS)
    # ============================================================
    def get_user_facts(self, username: str) -> List[str]:
        """Retourne la liste des faits mémorisés pour un utilisateur."""
        with self._lock:
            username_clean = (username or "default").strip().lower()
            return list(self.user_facts.get(username_clean, []))

    def add_user_fact(self, username: str, fact: str) -> bool:
        """Ajoute manuellement ou automatiquement un fait permanent."""
        if not fact or not fact.strip():
            return False
        fact_clean = fact.strip()
        with self._lock:
            username_clean = (username or "default").strip().lower()
            facts = self.user_facts.setdefault(username_clean, [])
            if fact_clean not in facts:
                facts.append(fact_clean)
                self._save_json(self.facts_file, {"users": self.user_facts})
                print(f"[MemoryManager] 🧠 Nouveau fait mémorisé ({username_clean}) : {fact_clean}")
                return True
        return False

    def remove_user_fact(self, username: str, fact_pattern: str) -> int:
        """Supprime les faits correspondant à un motif/mot-clé."""
        pattern_lower = fact_pattern.lower().strip()
        removed_count = 0
        with self._lock:
            username_clean = (username or "default").strip().lower()
            facts = self.user_facts.get(username_clean, [])
            new_facts = []
            for f in facts:
                if pattern_lower in f.lower():
                    removed_count += 1
                else:
                    new_facts.append(f)
            if removed_count > 0:
                self.user_facts[username_clean] = new_facts
                self._save_json(self.facts_file, {"users": self.user_facts})
        return removed_count

    def clear_user_facts(self, username: str) -> None:
        """Efface tous les faits mémorisés pour un utilisateur."""
        with self._lock:
            username_clean = (username or "default").strip().lower()
            if username_clean in self.user_facts:
                del self.user_facts[username_clean]
                self._save_json(self.facts_file, {"users": self.user_facts})

    def extract_facts_from_text(self, username: str, user_input: str) -> List[str]:
        """Détecte et extrait automatiquement les affirmations personnelles de l'utilisateur."""
        if not user_input or len(user_input) < 5:
            return []

        text_lower = user_input.lower().strip()
        extracted = []

        patterns = [
            (r"\b(?:je m'appelle|mon nom est|mon prénom est)\s+([a-zA-zÀ-ÿ\s\-]{2,30})", "Prénom / Nom : {}"),
            (r"\b(?:mon projet|mon projet s'appelle|je travaille sur)\s+([a-zA-zÀ-ÿ0-9\s\-_\.]{2,40})", "Projet principal : {}"),
            (r"\b(?:j'habite à|je vis à|je suis basé à)\s+([a-zA-zÀ-ÿ\s\-]{2,30})", "Localisation : {}"),
            (r"\b(?:mon langage préféré|je code en|j'utilise le langage)\s+([a-zA-z0-9#\+\s\-]{2,20})", "Langage préféré : {}"),
            (r"\b(?:souviens-toi que|n'oublie pas que|retiens que)\s+(.+)", "Fait mémorisé : {}"),
            (r"\b(?:je suis|mon métier est|mon rôle est)\s+(un[e]?\s+[a-zA-zÀ-ÿ\s\-]{3,30})", "Rôle / Métier : {}"),
            (r"\b(?:ma clé serper est|mon api key est)\s+([a-zA-z0-9_\-]{8,64})", "Clé API enregistrée : {}")
        ]

        for regex, template in patterns:
            match = re.search(regex, user_input, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                if val:
                    fact_str = template.format(val)
                    if self.add_user_fact(username, fact_str):
                        extracted.append(fact_str)

        return extracted

    # ============================================================
    # 2. MÉMOIRE COURT TERME TOKEN-AWARE (STM / CONVERSATION)
    # ============================================================
    DEFAULT_STM_TOKEN_LIMIT = 3072
    MAX_STM_TURNS = 12

    def record_turn(
        self,
        username: str,
        conv_id: str,
        user_input: str,
        assistant_response: str,
        token_limit: int = None
    ) -> None:
        """Enregistre un échange complet dans le fil STM avec gestion token-aware."""
        token_limit = token_limit or self.DEFAULT_STM_TOKEN_LIMIT
        with self._lock:
            convs = self.stm.setdefault("conversations", {})
            conv_key = f"{username}:{conv_id}" if conv_id else f"{username}:default"
            history = convs.setdefault(conv_key, [])

            now_str = datetime.now().isoformat()
            history.append({"role": "user", "content": user_input, "timestamp": now_str})
            history.append({"role": "assistant", "content": assistant_response, "timestamp": now_str})

            # Nettoyer les entrées expirées (>1h) pour garder la mémoire courte
            max_age = 3600
            cutoff_ts = time.time() - max_age
            cutoff_str = datetime.fromtimestamp(cutoff_ts).isoformat()
            # Garder au moins les 4 derniers messages
            if len(history) > 4:
                history[:] = [m for m in history if m.get("timestamp", "") > cutoff_str]

            # Compression token-aware : supprimer les messages les plus anciens si dépassement
            while len(history) > 4:
                total_tokens = sum(TokenCounter.count(m.get("content", "")) for m in history)
                if total_tokens <= token_limit:
                    break
                # Supprimer le message le plus ancien (pair user+assistant)
                history.pop(0)
                if history:
                    history.pop(0)

            self._save_json(self.stm_file, self.stm)

            # Extraire des faits en tâche de fond (non bloquante)
            threading.Thread(
                target=self.extract_facts_from_text,
                args=(username, user_input),
                daemon=True
            ).start()

    def get_stm_context(
        self,
        username: str,
        conv_id: str,
        max_turns: int = 5,
        token_budget: int = 2048
    ) -> List[Dict[str, str]]:
        """Récupère les derniers échanges avec budget token-aware."""
        with self._lock:
            convs = self.stm.get("conversations", {})
            conv_key = f"{username}:{conv_id}" if conv_id else f"{username}:default"
            history = convs.get(conv_key, [])
            if not history:
                return []

            # Retourner les max_turns*2 derniers, mais en respectant le budget token
            max_messages = min(max_turns * 2, len(history))
            result = history[-max_messages:]

            # Ajuster pour le budget token
            total_tokens = sum(TokenCounter.count(m.get("content", "")) for m in result)
            while total_tokens > token_budget and len(result) > 4:
                result = result[1:]
                total_tokens = sum(TokenCounter.count(m.get("content", "")) for m in result)

            return result

    def _summarize_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """Génère un résumé de la conversation pour la compacter en LTM."""
        if not messages:
            return ""
        user_msgs = [m["content"] for m in messages if m.get("role") == "user" and m.get("content")]
        asst_msgs = [m["content"] for m in messages if m.get("role") == "assistant" and m.get("content")]
        if not user_msgs:
            return ""
        # Construction d'un résumé simple basé sur les thèmes dominants
        topic = TopicDetector.classify(" ".join(user_msgs))
        all_text = " ".join(user_msgs + asst_msgs[:3])[:500]
        entities = EntityExtractor.extract(" ".join(user_msgs))
        summary_parts = [f"Topic: {topic}"]
        if entities["projects"]:
            summary_parts.append(f"Projets: {', '.join(entities['projects'][:2])}")
        if entities["languages"]:
            summary_parts.append(f"Langages: {', '.join(entities['languages'][:3])}")
        if entities["locations"]:
            summary_parts.append(f"Localisation: {', '.join(entities['locations'][:2])}")
        summary_parts.append(f"Contexte: {all_text[:200]}")
        return " | ".join(summary_parts)

    def get_stm_summary(self, username: str, conv_id: str) -> str:
        """Retourne un résumé token-efficient de la conversation courante."""
        with self._lock:
            convs = self.stm.get("conversations", {})
            conv_key = f"{username}:{conv_id}" if conv_id else f"{username}:default"
            history = convs.get(conv_key, [])
            if not history:
                return ""
            return self._summarize_conversation(history)

    def format_stm_for_prompt(
        self,
        username: str,
        conv_id: str,
        max_turns: int = 5,
        token_budget: int = 2048
    ) -> str:
        """Formate le fil récent de conversation pour l'injection dans le prompt LLM."""
        recent_messages = self.get_stm_context(username, conv_id, max_turns=max_turns, token_budget=token_budget)
        if not recent_messages:
            return ""
        lines = []
        for msg in recent_messages:
            sender = "Utilisateur" if msg.get("role") == "user" else "Onyx"
            lines.append(f"{sender} : {msg.get('content', '')[:500]}")
        return "\n".join(lines)

    def clear_stm_for_conversation(self, username: str, conv_id: str) -> None:
        """Efface la mémoire court terme d'une conversation spécifique."""
        with self._lock:
            convs = self.stm.get("conversations", {})
            conv_key = f"{username}:{conv_id}" if conv_id else f"{username}:default"
            if conv_key in convs:
                del convs[conv_key]
                self._save_json(self.stm_file, self.stm)

    # ============================================================
    # 3. RECHERCHE HYBRIDE & PONDÉRÉE DANS LA MÉMOIRE LONG TERME (LTM)
    # ============================================================
    LTM_MAX_ENTRIES = 500
    LTM_IMPORTANCE_DECAY_DAYS = 30

    def _calculate_importance(self, item: Dict[str, Any]) -> float:
        """Calcule un score d'importance basé sur la longueur, les entités et les interactions."""
        importance = 0.0
        user_text = item.get("user", "") or item.get("content", "") or ""
        asst_text = item.get("assistant", "") or item.get("response", "") or ""
        # Score basé sur la longueur
        importance += min(0.3, len(user_text) / 200)
        importance += min(0.2, len(asst_text) / 500)
        # Score basé sur les entités extraites
        entities = EntityExtractor.extract(user_text + " " + asst_text)
        importance += min(0.3, len(entities["projects"]) * 0.1)
        importance += min(0.2, len(entities["languages"]) * 0.05)
        # Bonus si l'utilisateur a explicitement demandé un rappel
        if any(kw in user_text.lower() for kw in ["souviens", "n'oublie", "retiens", "rappelle", "mémoire"]):
            importance += 0.3
        return min(1.0, importance)

    def _compute_tfidf_scores(
        self,
        query_words: List[str],
        documents: List[str]
    ) -> Dict[int, float]:
        """Calcule des scores TF-IDF simples pour un ensemble de documents."""
        scores: Dict[int, float] = {}
        N = len(documents)
        if N == 0:
            return scores

        df: Dict[str, int] = {}
        for doc in documents:
            doc_words = set(w for w in re.findall(r'\b\w{3,}\b', doc.lower()))
            for w in doc_words:
                df[w] = df.get(w, 0) + 1

        for doc_idx, doc in enumerate(documents):
            tf = {}
            for word in re.findall(r'\b\w{3,}\b', doc.lower()):
                tf[word] = tf.get(word, 0) + 1
            score = 0.0
            for qw in query_words:
                if qw in tf:
                    idf = math.log(1 + N / (df.get(qw, 1) + 1))
                    score += tf[qw] * idf
            scores[doc_idx] = score
        return scores

    def search_ltm_smart(
        self,
        username: str,
        query: str,
        ltm_data_source: List[Dict[str, Any]] = None,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Recherche intelligente dans les archives LTM :
        - Score TF-IDF amélioré avec n-grammes
        - Décroissance temporelle (bonus pour les souvenirs récents)
        - Score d'importance (bonus pour les entrées importantes)
        - Filtrage par entités
        """
        if not query or not query.strip():
            return []

        query_clean = query.lower().strip()
        query_words = [w for w in re.findall(r'\b\w{3,}\b', query_clean)]
        if not query_words:
            return []

        if ltm_data_source is None:
            # Lire depuis le fichier ltm.json (format consolidations)
            ltm_data_source = self.ltm.get("consolidations", [])
            # Si pas de consolidations, fallback sur l'ancien format
            if not ltm_data_source:
                ltm_conversations = self._load_ltm_legacy()
                ltm_data_source = ltm_conversations

        results = []
        now_ts = time.time()

        documents = []
        valid_items = []
        for item in ltm_data_source:
            user_text = item.get("user", "") or item.get("content") or ""
            asst_text = item.get("assistant", "") or item.get("response") or ""
            combined = f"{user_text} {asst_text}".lower()
            if not combined.strip():
                continue
            if username and item.get("username", "").lower() != username.lower():
                continue
            documents.append(combined)
            valid_items.append(item)

        if not documents:
            return []

        tfidf_scores = self._compute_tfidf_scores(query_words, documents)

        for idx, item in enumerate(valid_items):
            user_text = item.get("user", "") or ""
            asst_text = item.get("assistant", "") or ""
            combined = f"{user_text} {asst_text}".lower()

            # Score TF-IDF
            score = tfidf_scores.get(idx, 0.0)
            if score <= 0:
                # Fallback : fréquence simple
                for word in query_words:
                    count = combined.count(word)
                    if count > 0:
                        score += math.log(1 + count) * (1.5 if word in user_text.lower() else 1.0)

            # Bonus bigrammes
            for i in range(len(query_words) - 1):
                bigram = f"{query_words[i]} {query_words[i+1]}"
                if bigram in combined:
                    score += 2.5

            if score < 0.5:
                continue

            # Décroissance temporelle
            item_date_str = item.get("timestamp", "")
            recency_multiplier = 1.0
            if item_date_str:
                try:
                    item_ts = datetime.fromisoformat(str(item_date_str)[:19]).timestamp()
                    days_old = max(0, (now_ts - item_ts) / 86400.0)
                    recency_multiplier = max(0.5, 1.0 - (math.log(1 + days_old) * 0.05))
                except Exception:
                    pass

            # Score d'importance
            importance = self._calculate_importance(item)

            final_score = score * recency_multiplier * (0.7 + 0.3 * importance)
            results.append((final_score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def _load_ltm_legacy(self) -> List[Dict[str, Any]]:
        """Charge l'ancien format ltm.json (conversations) pour rétrocompatibilité."""
        legacy_path = os.path.join(os.path.dirname(self.ltm_file), "ltm.json")
        if os.path.exists(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                conversations = data.get("conversations", [])
                return conversations
            except Exception:
                return []
        return []

    def consolidate_to_ltm(
        self,
        username: str,
        conv_id: str,
        conversation_messages: List[Dict[str, Any]],
        topic: str = None,
        importance_threshold: float = 0.3
    ) -> Optional[Dict[str, Any]]:
        """
        Consolide une conversation terminée vers la LTM sous forme de résumé.
        - Génère un résumé compact
        - Extracte les entités
        - Calcule le score d'importance
        - Découpe par topics si nécessaire
        """
        if not conversation_messages:
            return None

        with self._lock:
            # Détecter les boundaries thématiques
            boundaries = TopicDetector.detect_boundary(conversation_messages)
            segments = []
            if boundaries:
                start = 0
                for b in boundaries:
                    segments.append(conversation_messages[start:b])
                    start = b
                segments.append(conversation_messages[start:])
            else:
                segments.append(conversation_messages)

            consolidated_entries = []
            username_clean = (username or "default").strip().lower()

            for seg in segments:
                if len(seg) < 2:
                    continue
                user_msgs = [m.get("content", "") for m in seg if m.get("role") == "user"]
                asst_msgs = [m.get("content", "") for m in seg if m.get("role") == "assistant"]
                if not user_msgs:
                    continue

                full_query = " ".join(user_msgs)
                topic_label = TopicDetector.classify(full_query) if topic is None else topic

                # Créer l'entrée consolidée
                entry: Dict[str, Any] = {
                    "username": username_clean,
                    "timestamp": datetime.now().isoformat(),
                    "conv_id": conv_id,
                    "topic": topic_label,
                    "user": "; ".join(user_msgs[:3]),
                    "assistant": "; ".join(asst_msgs[:2]) if asst_msgs else "",
                    "summary": self._summarize_conversation(seg),
                    "entities": EntityExtractor.extract(full_query + " " + " ".join(asst_msgs[:2])),
                    "importance": self._calculate_importance({
                        "user": " ".join(user_msgs),
                        "assistant": " ".join(asst_msgs) if asst_msgs else ""
                    }),
                    "message_count": len(seg),
                    "token_count": sum(TokenCounter.count(m.get("content", "")) for m in seg),
                }

                if entry["importance"] >= importance_threshold:
                    consolidated_entries.append(entry)

            # Ajouter aux consolidations LTM
            consolidations = self.ltm.setdefault("consolidations", [])
            consolidations.extend(consolidated_entries)

            # Pruning : garder les 500 entrées les plus importantes récentes
            if len(consolidations) > self.LTM_MAX_ENTRIES:
                now_ts = time.time()
                for entry in consolidations:
                    ts_str = entry.get("timestamp", "")
                    try:
                        entry_ts = datetime.fromisoformat(str(ts_str)[:19]).timestamp()
                        days_old = max(0, (now_ts - entry_ts) / 86400.0)
                        age_decay = max(0.1, 1.0 - (math.log(1 + days_old) * 0.05))
                    except Exception:
                        age_decay = 1.0
                    entry["_sort_score"] = entry.get("importance", 0.5) * age_decay

                consolidations.sort(key=lambda x: x.get("_sort_score", 0), reverse=True)
                for entry in consolidations:
                    entry.pop("_sort_score", None)
                self.ltm["consolidations"] = consolidations[:self.LTM_MAX_ENTRIES]

            self._save_json(self.ltm_file, self.ltm)

            if consolidated_entries:
                print(f"[MemoryManager] 📚 Consolidation LTM ({len(consolidated_entries)} entrées, topic: {topic_label})")
            return consolidated_entries[-1] if consolidated_entries else None

    def auto_consolidate_from_history(
        self,
        username: str,
        history: List[Dict[str, Any]]
    ) -> None:
        """
        Parcourt l'historique complet de l'utilisateur et consolide les conversations
        terminées vers la LTM. À appeler périodiquement ou à la fermeture de session.
        """
        username_clean = (username or "default").strip().lower()
        with self._lock:
            existing_conv_ids = {
                c.get("conv_id") for c in self.ltm.get("consolidations", [])
                if c.get("username") == username_clean
            }

            for conv in history:
                conv_id = conv.get("id", "")
                if conv_id in existing_conv_ids:
                    continue
                messages = conv.get("messages", [])
                if len(messages) < 4:
                    continue
                # Vérifier si la conversation a une activité récente suffisante
                last_ts = conv.get("updated_at", "")
                try:
                    last_dt = datetime.fromisoformat(str(last_ts))
                    if (datetime.now() - last_dt).days > 30:
                        continue
                except Exception:
                    pass

                self.consolidate_to_ltm(
                    username=username_clean,
                    conv_id=conv_id,
                    conversation_messages=messages,
                    importance_threshold=0.25
                )

    # ============================================================
    # 4. CONTEXTE GLOBAL INTÉGRÉ POUR PROMPT LLM
    # ============================================================
    def get_full_memory_context(
        self,
        username: str,
        conv_id: str,
        query: str,
        past_conversations: List[Dict[str, Any]] = None,
        max_stm_turns: int = 5,
        stm_token_budget: int = 2048
    ) -> Dict[str, Any]:
        """
        Assemble l'ensemble du contexte mémoriel (Faits LTM + Fil STM + Archives LTM).
        - Faits permanents extraits automatiquement
        - Fil récent token-aware (STM)
        - Archives LTM pertinentes (recherche TF-IDF + recency + importance)
        - Contexte d'entités (projets, langages, localisations)
        """
        username_clean = (username or "default").strip().lower()

        # 1. Faits permanents de l'utilisateur
        facts = self.get_user_facts(username_clean)
        facts_block = ""
        if facts:
            facts_lines = [f"• {f}" for f in facts[-10:]]
            facts_block = "=== PROFIL & FAITS UTILISATEUR (LTM) ===\n" + "\n".join(facts_lines)

        # 2. Entités contextuelles (bonus pour projets/langages pertinents)
        entities_context = EntityExtractor.extract(query)
        entity_block = ""
        entity_lines = []
        if entities_context["projects"]:
            entity_lines.append(f"Projets mentionnés : {', '.join(entities_context['projects'])}")
        if entities_context["languages"]:
            entity_lines.append(f"Langages : {', '.join(entities_context['languages'])}")
        if entities_context["locations"]:
            entity_lines.append(f"Localisation : {', '.join(entities_context['locations'])}")
        if entity_lines:
            entity_block = "=== ENTITÉS DÉTECTÉES ===\n" + "\n".join(entity_lines)

        # 3. Fil récent de conversation (STM)
        stm_str = self.format_stm_for_prompt(username_clean, conv_id, max_turns=max_stm_turns, token_budget=stm_token_budget)
        stm_block = ""
        if stm_str:
            stm_block = "=== DÉROULÉ DE LA CONVERSATION RÉCENTE (STM) ===\n" + stm_str

        # 4. Archives LTM pertinentes
        ltm_results = self.search_ltm_smart(
            username_clean, query,
            ltm_data_source=past_conversations,
            limit=3
        )
        ltm_block = ""
        if ltm_results:
            ltm_lines = []
            for item in ltm_results:
                u = item.get("user") or item.get("user_input") or ""
                a = item.get("assistant") or item.get("response") or ""
                summary = item.get("summary", "")
                ts = str(item.get("timestamp", ""))[:10]
                if u and a:
                    if summary:
                        ltm_lines.append(f"• ({ts}) {summary}")
                    else:
                        ltm_lines.append(f"• ({ts}) Utilisateur : {u[:100]} | Onyx : {a[:100]}")
            if ltm_lines:
                ltm_block = "=== SOUVENIRS PERTINENTS RETROUVÉS (LTM) ===\n" + "\n".join(ltm_lines)

        full_parts = [p for p in [facts_block, entity_block, ltm_block, stm_block] if p]
        full_context_str = "\n\n".join(full_parts)

        return {
            "facts": facts,
            "entities": entities_context,
            "stm_history": self.get_stm_context(username_clean, conv_id, max_turns=max_stm_turns, token_budget=stm_token_budget),
            "ltm_results": ltm_results,
            "formatted_context": full_context_str
        }

    def get_memory_stats(self, username: str = None) -> Dict[str, Any]:
        """Retourne des statistiques sur l'état de la mémoire."""
        username_clean = (username or "default").strip().lower()
        with self._lock:
            stm_convs = self.stm.get("conversations", {})
            stm_keys_for_user = [k for k in stm_convs.keys() if k.startswith(f"{username_clean}:")]
            stm_msg_count = sum(len(v) for v in [stm_convs[k] for k in stm_keys_for_user])

            ltm_consolidations = self.ltm.get("consolidations", [])
            ltm_user_entries = [c for c in ltm_consolidations if c.get("username") == username_clean]

            topics_counts: Dict[str, int] = {}
            for entry in ltm_user_entries:
                topic = entry.get("topic", "general")
                topics_counts[topic] = topics_counts.get(topic, 0) + 1

            return {
                "stm_conversations": len(stm_keys_for_user),
                "stm_messages": stm_msg_count,
                "ltm_consolidations": len(ltm_user_entries),
                "ltm_total_entries": len(ltm_consolidations),
                "topics_breakdown": topics_counts,
                "user_facts_count": len(self.get_user_facts(username_clean)),
            }

    def reset_stm(self, username: str = None) -> None:
        """Efface toute la mémoire court terme (garde la LTM)."""
        username_clean = (username or "default").strip().lower()
        with self._lock:
            if username:
                keys_to_remove = [k for k in self.stm.get("conversations", {}).keys() if k.startswith(f"{username_clean}:")]
                for k in keys_to_remove:
                    del self.stm["conversations"][k]
            else:
                self.stm = {"conversations": {}}
            self._save_json(self.stm_file, self.stm)
            print(f"[MemoryManager] 🧹 STM réinitialisée ({username_clean})")


# Modèle singleton et rétrocompatibilité
memory_manager = MemoryManager()
CognitiveMemory = MemoryManager
OnyxMemoryManager = MemoryManager

