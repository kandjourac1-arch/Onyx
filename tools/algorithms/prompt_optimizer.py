"""
tools/algorithms/prompt_optimizer.py
Optimiseur de prompts pour assistat LLM dans Onyx V2
"""

import re
import math
from collections import Counter

class PromptOptimizer:
    def __init__(self):
        self.stop_words_fr = {"le", "la", "les", "du", "de", "des", "un", "une", "et", "est", "en", "que", "qui", "pour", "dans", "par", "sur", "au", "aux", "avec", "ce", "cette", "ces"}

    def compress_prompt(self, text: str, max_ratio: float = 0.8) -> str:
        """1. Compression sémantique légère en retirant le bruit redondant."""
        words = text.split()
        if len(words) <= 10:
            return text
        cleaned = re.sub(r'\b(s\'il te plaît|s\'il vous plaît|stp|svp|dis-moi|euh|du coup|en fait)\b', '', text, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned if cleaned else text

    def inject_chain_of_thought(self, prompt: str, category: str = "general") -> str:
        """2. Injection automatique de consignes Chain-of-Thought."""
        if "étape par étape" in prompt.lower() or "step by step" in prompt.lower():
            return prompt
        cot_prefix = "[Mode Raisonnement Structuré: Réfléchis étape par étape avant d'afficher la réponse finale.]\n\n"
        return cot_prefix + prompt

    def build_few_shot_prompt(self, base_prompt: str, examples: list[dict]) -> str:
        """3. Construction de prompts few-shot dynamiques."""
        if not examples:
            return base_prompt
        shots_str = ""
        for ex in examples:
            shots_str += f"Exemple Entrée: {ex.get('input','')}\nExemple Sortie: {ex.get('output','')}\n---\n"
        return f"{shots_str}Nouvelle demande:\n{base_prompt}"

    def score_prompt_clarity(self, prompt: str) -> dict:
        """4. Évaluation de la clarté et concision du prompt (0-100)."""
        length = len(prompt)
        words = prompt.split()
        num_words = len(words)
        if num_words == 0:
            return {"score": 0, "feedback": "Prompt vide"}
        
        has_action_verb = bool(re.search(r'\b(crée|fais|explique|analyse|écris|génère|calcule|donne|résous)\b', prompt, re.IGNORECASE))
        score = 50
        if 5 <= num_words <= 50:
            score += 25
        elif num_words > 50:
            score += 10
        
        if has_action_verb:
            score += 25
            
        return {
            "score": min(100, score),
            "word_count": num_words,
            "has_action_verb": has_action_verb
        }

    def auto_decompose_query(self, prompt: str) -> list[str]:
        """5. Découpage automatique des requêtes complexes en sous-tâches."""
        parts = re.split(r'\b(?:et ensuite|puis|après ça|également|enfin)\b|\n', prompt, flags=re.IGNORECASE)
        sub_tasks = [p.strip() for p in parts if p.strip()]
        return sub_tasks if len(sub_tasks) > 1 else [prompt]

    def manage_context_window(self, messages: list[dict], max_tokens_approx: int = 2000) -> list[dict]:
        """6. Gestion intelligente de la fenêtre de contexte."""
        current_len = 0
        kept_messages = []
        for msg in reversed(messages):
            msg_tokens = len(msg.get("content", "").split()) * 1.3
            if current_len + msg_tokens > max_tokens_approx:
                break
            kept_messages.insert(0, msg)
            current_len += msg_tokens
        return kept_messages

    def adapt_system_prompt_language(self, prompt: str, default_lang: str = "fr") -> str:
        """7. Détection et adaptation dynamique de la langue."""
        english_words = {"the", "is", "and", "to", "in", "of", "you", "that", "it", "for", "on", "with"}
        words = set(re.findall(r'\w+', prompt.lower()))
        eng_overlap = len(words.intersection(english_words))
        
        if eng_overlap >= 2:
            return "Please respond in English. Be clear, precise, and structured."
        return "Réponds en français. Sois clair, précis et structuré."

    def get_template(self, domain: str, input_text: str) -> str:
        """8. Moteur de templates par domaine."""
        templates = {
            "code": f"Tu es un expert développeur. Écris du code propre, testé et documenté pour :\n{input_text}",
            "summary": f"Tu es un synthétiseur d'informations. Fais un résumé clair et concis du texte suivant :\n{input_text}",
            "refactor": f"Analyse et optimise le code suivant en respectant les meilleures pratiques :\n{input_text}",
            "explain": f"Explique le concept suivant de manière simple et didactique :\n{input_text}"
        }
        return templates.get(domain, input_text)

    def filter_duplicate_history(self, messages: list[dict]) -> list[dict]:
        """9. Filtrage des doublons dans l'historique."""
        seen = set()
        unique_msgs = []
        for msg in messages:
            content = msg.get("content", "").strip()
            if content not in seen:
                seen.add(content)
                unique_msgs.append(msg)
        return unique_msgs

    def apply_hallucination_guardrail(self, prompt: str) -> str:
        """10. Instruction de protection anti-hallucination."""
        guardrail = "\n\n[Instruction de Stricte Exactitude: Si tu ne connais pas la réponse avec certitude ou si les données fournies sont insuffisantes, indique-le clairement sans inventer de faits.]"
        return prompt + guardrail
