"""Système d'affect simulé pour Onyx.

Ce module ne prétend pas donner des sentiments réels à l'IA : il détecte
l'humeur exprimée par l'utilisateur et conserve un état conversationnel léger
afin d'adapter le ton, la vitesse et le niveau d'empathie des réponses.
"""

import json
import os
import re
import threading
from datetime import datetime
from typing import Dict, Any


class SentimentEngine:
    LABELS = {
        "joy": ("Joie", "😊", "chaleureux et enthousiaste"),
        "sadness": ("Tristesse", "🌧️", "doux, rassurant et patient"),
        "anger": ("Frustration", "⚡", "calme, factuel et désamorçant"),
        "fear": ("Inquiétude", "🫶", "rassurant, prudent et structuré"),
        "stress": ("Stress", "🌿", "calme, simple et orienté vers une prochaine étape"),
        "curiosity": ("Curiosité", "🔎", "pédagogique et stimulant"),
        "neutral": ("Neutre", "◌", "naturel et direct"),
    }

    LEXICON = {
        "joy": "heureux heureuse joie content contente super génial merci bravo formidable amour adore adoré rire haha",
        "sadness": "triste tristesse déçu déçue déception pleure pleurer malheureux malheureuse solitude seul seule perdu perdue",
        "anger": "énervé énervée colère colère marre agacé agacée furieux furieuse déteste nul nulle impossible bordel",
        "fear": "peur anxieux anxieuse angoisse inquiet inquiète crainte panique danger risque",
        "stress": "stress stressé stressée pression urgence débordé débordée fatigue fatigué fatiguée problème compliqué difficile",
        "curiosity": "pourquoi comment explique différence apprendre comprendre savoir question curieux curieuse",
    }

    def __init__(self, memory_dir: str = "memory"):
        self.path = os.path.join(memory_dir, "sentiments.json")
        self._lock = threading.RLock()
        os.makedirs(memory_dir, exist_ok=True)
        self.states = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        temp = self.path + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(self.states, handle, ensure_ascii=False, indent=2)
        os.replace(temp, self.path)

    def analyze(self, text: str) -> Dict[str, Any]:
        normalized = re.sub(r"[^a-zàâçéèêëîïôûùüÿñæœ'\s]", " ", (text or "").lower())
        scores = {label: sum(1 for word in words.split() if re.search(rf"\b{re.escape(word)}\b", normalized)) for label, words in self.LEXICON.items()}
        label, score = max(scores.items(), key=lambda item: item[1]) if scores else ("neutral", 0)
        if score == 0:
            label = "neutral"
        confidence = round(min(1.0, score / 3), 2)
        name, emoji, tone = self.LABELS[label]
        return {"label": label, "name": name, "emoji": emoji, "tone": tone, "confidence": confidence, "scores": scores}

    def observe(self, username: str, text: str) -> Dict[str, Any]:
        result = self.analyze(text)
        key = (username or "default").strip().lower()
        with self._lock:
            previous = self.states.get(key, {})
            self.states[key] = {
                **result,
                "previous": previous.get("label", "neutral"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._save()
        return self.states[key]

    def get_state(self, username: str) -> Dict[str, Any]:
        key = (username or "default").strip().lower()
        return self.states.get(key) or self.analyze("")

    def guidance(self, sentiment: Dict[str, Any]) -> str:
        return (
            f"État affectif détecté (simulation) : {sentiment['name']} {sentiment['emoji']}. "
            f"Adapte ton ton pour être {sentiment['tone']}. Ne prétends pas ressentir toi-même cette émotion "
            "et n'en fais pas un diagnostic psychologique."
        )
