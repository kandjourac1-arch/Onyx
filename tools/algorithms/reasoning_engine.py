"""
tools/algorithms/reasoning_engine.py
Moteur de raisonnement structuré et analyse logique
"""

import re
from collections import Counter

class ReasoningEngine:
    def generate_socratic_questions(self, topic: str) -> list[str]:
        """1. Générateur de questionnement socratique."""
        return [
            f"Pourquoi considérez-vous que '{topic}' est un point central ?",
            f"Quelles sont les preuves directes qui appuient la thèse sur '{topic}' ?",
            f"Existe-t-il une alternative ou une contre-perspective évidente à '{topic}' ?",
            f"Quelles seraient les conséquences si l'hypothèse inverse sur '{topic}' était vraie ?"
        ]

    def find_analogies(self, concept: str) -> str:
        """2. Générateur d'analogies explicatives."""
        analogies_db = {
            "api": "Une API est comme un serveur dans un restaurant qui prend votre commande et apporte le plat de la cuisine.",
            "variables": "Une variable est comme une boîte étiquetée dans laquelle on stocke un objet.",
            "recursion": "La récursion est comme des poupées russes s'emboîtant les unes dans les autres.",
            "llm": "Un LLM est comme un autocomplétement ultra-avancé formé sur toute la bibliothèque humaine."
        }
        for key, val in analogies_db.items():
            if key in concept.lower():
                return val
        return f"Pour comprendre '{concept}', imaginez un système interconnecté où chaque composant transmet des signaux."

    def detect_contradictions(self, text_a: str, text_b: str) -> list[str]:
        """3. Détecteur de contradictions textuelles simples."""
        contradictions = []
        negations = ["ne pas", "aucun", "jamais", "impossible", "faux", "interdit"]
        
        words_a = set(re.findall(r'\w+', text_a.lower()))
        words_b = set(re.findall(r'\w+', text_b.lower()))
        common = words_a.intersection(words_b)
        
        has_neg_a = any(n in text_a.lower() for n in negations)
        has_neg_b = any(n in text_b.lower() for n in negations)
        
        if len(common) >= 2 and (has_neg_a != has_neg_b):
            contradictions.append(f"Contradiction potentielle détectée sur les concepts communs: {list(common)[:3]}")
            
        return contradictions

    def map_arguments(self, text: str) -> dict:
        """4. Cartographie des arguments Pro / Contra."""
        pros = []
        cons = []
        sentences = re.split(r'[.!?]\s+', text)
        
        pro_kw = ["avantage", "bénéfice", "positif", "bon", "gain", "utile"]
        con_kw = ["inconvénient", "risqué", "négatif", "mauvais", "perte", "limite"]
        
        for s in sentences:
            if any(k in s.lower() for k in pro_kw):
                pros.append(s.strip())
            elif any(k in s.lower() for k in con_kw):
                cons.append(s.strip())
                
        return {"pros": pros, "cons": cons}

    def score_evidence_strength(self, statement: str) -> float:
        """5. Évaluation de la solidité des preuves."""
        score = 0.5
        fact_indicators = ["étud", "chiffre", "donnée", "%", "selon", "prouvé", "mesuré"]
        vague_indicators = ["peut-être", "semble", "on dit", "probablement", "je pense"]
        
        for kw in fact_indicators:
            if kw in statement.lower():
                score += 0.1
        for kw in vague_indicators:
            if kw in statement.lower():
                score -= 0.1
                
        return max(0.0, min(1.0, round(score, 2)))

    def bayesian_update(self, prior: float, likelihood: float, marginal_likelihood: float) -> float:
        """6. Mise à jour Bayésienne des probabilités d'hypothèses."""
        if marginal_likelihood == 0:
            return prior
        posterior = (likelihood * prior) / marginal_likelihood
        return max(0.0, min(1.0, round(posterior, 4)))

    def detect_logical_fallacies(self, text: str) -> list[str]:
        """7. Détecteur de sophismes courants."""
        fallacies = []
        if re.search(r'\b(tout le monde sait|tout le monde fait|évidemment)\b', text, re.IGNORECASE):
            fallacies.append("Sophisme d'Appel au Peuple (Argumentum ad populum)")
        if re.search(r'\b(si on accepte.*alors pire|effet boule de neige)\b', text, re.IGNORECASE):
            fallacies.append("Pente glissante (Slippery Slope)")
        if re.search(r'\b(soit.*soit.*rien d\'autre)\b', text, re.IGNORECASE):
            fallacies.append("Faux dilemme")
        return fallacies

    def extract_key_facts(self, text: str) -> list[str]:
        """8. Extracteur de faits clés."""
        sentences = re.split(r'[.!?]\s+', text)
        facts = []
        for s in sentences:
            if re.search(r'\d+|est un|s\'appelle|situé|créé en', s, re.IGNORECASE):
                facts.append(s.strip())
        return facts[:5]

    def rank_summary_sentences(self, text: str, top_n: int = 3) -> list[str]:
        """9. Classement des phrases d'un texte par importance (TextRank simplifié)."""
        sentences = [s.strip() for s in re.split(r'[.!?]\s+', text) if len(s.strip()) > 10]
        if not sentences:
            return []
        
        words = re.findall(r'\w+', text.lower())
        word_freq = Counter(words)
        
        scored_sentences = []
        for s in sentences:
            s_words = re.findall(r'\w+', s.lower())
            score = sum(word_freq[w] for w in s_words) / (len(s_words) + 1e-5)
            scored_sentences.append((score, s))
            
        scored_sentences.sort(key=lambda x: x[0], reverse=True)
        return [s for score, s in scored_sentences[:top_n]]

    def generate_multi_perspectives(self, prompt: str) -> dict:
        """10. Générateur d'angles de vue multiples."""
        return {
            "pragmatique": f"D'un point de vue pratique pour '{prompt}': Chercher la solution la plus directe.",
            "analytique": f"D'un point de vue technique pour '{prompt}': Décomposer les variables et le fonctionnement interne.",
            "critique": f"D'un point de vue risques pour '{prompt}': Identifier les failles potentielles et limites."
        }
