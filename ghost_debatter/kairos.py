"""
KAIROS : Miroir Linguistique (Inversion Algorithmique < 1 ms)
et Moteur de Consensus de Preuves (Thèse vs Antithèse).
"""

import re
import spacy
from typing import List, Dict, Tuple

# Chargement du modèle français spaCy
try:
    nlp = spacy.load("fr_core_news_sm")
except Exception:
    # Fallback minimal si le modèle n'est pas encore téléchargé
    import spacy.cli
    spacy.cli.download("fr_core_news_sm")
    nlp = spacy.load("fr_core_news_sm")


class LinguisticMirror:
    """Miroir Linguistique : Génère l'exacte Antithèse d'une Thèse en < 1 ms sans aucun LLM."""
ANTONYMS = {
    "bon": "mauvais",
    "excellente": "médiocre",
    "rapide": "lent",
    "efficace": "inefficace",
    "rentable": "coûteux",
    "propre": "polluant",
    "abondante": "rare",
    "facile": "difficile",
    "avantage": "inconvénient",
    "toujours": "rarement",
    "partout": "nulle part",
    "augmenter": "diminuer",
    "utile": "inutile",
    "fiable": "instable",
    "simple": "complexe",
    
    "sage": "insensé",
    "brave": "courageux",
    "rare": "abondant",
    "taciturne": "bavard",
    "joyeux": "triste",
    "clair": "obscur",
    "chaud": "froid",
    "fort": "faible",
    "heureux": "malheureux",
    "vivant": "mort",
    "lumineux": "sombre",
    "jeune": "ancien",
    "long": "court",
    "large": "étroit",
    "doux": "aigre",
    "haut": "bas",
    "grand": "petit",

    "gentil": "méchant",
    "sympathique": "antipathique",
    "bienveillant": "hostile",
    "amical": "indifférent",
    "convenable": "inconvénient",
    "admirable": "abject",
    "courageux": "timide",
    "saint": "pervers",
    "sérieux": "froissé",
    "calme": "hystérique",
    "aimant": "antipathique",
    "bienfait": "malfait",
    "clairvoyant": "aveugle",
    "vigilant": "inattentif",
    "douillet": "froid",
    "pétulant": "sombre",

    "libre": "enchaîné",
    "généreux": "misérable",
    "capricieux": "constat",
    "spontané": "artificiel",
    "optimiste": "pessimiste",
    "confiant": "douteux",
    "actif": "passif",
    "bavard": "silencieux",
    "vivace": "flasque",
    "agréable": "insupportable",
    "sensible": "insensible",
    "vigoureux": "affaibli",
    "énergique": "démunis",
    "intelligent": "stupide",
    "savant": "ignorant",

    "mûr": "vierge",
    "sain": "mauvais",
    "pur": "corrompu",
    "purificateur": "contaminateur",
    "léger": "lourd",
    "lumineux": "ténébreux",
    "brillant": "brouillard",
    "vif": "dormi",
    "éveillé": "endormi",
    "heureux": "malheureux",
    "serein": "perturbé",
    "tranquille": "agité",
    "calme": "hystérique",
    "pacifique": "chaotique",
    "harmonieux": "discordant",

    "abondance": "manque",
    "abondance": "pénurie",
    "plein": "vide",
    "plein": "sèche",
    "fertile": "stéril",
    "plein": "dénué",
    "généreux": "miserable",
    "plein": "boudeur",
    "abondant": "scarce",
    "abundant": "insuffisant",
    "plein": "déficient",
    "généreux": "misérable",
    "plein": "désert",
    "plein": "épuisé",
    "plein": "défraîchi",

    "sain": "mauvais",
    "bien": "mal",
    "vivant": "mort",
    "fort": "faible",
    "heureux": "triste",
    "serein": "perturbé",
    "tranquille": "agité",
    "calme": "hystérique",
    "pacifique": "chaotique",
    "harmonieux": "discordant",

    "amical": "indifférent",
    "convenable": "inconvénient",
    "admirable": "abject",
    "courageux": "timide",
    "saint": "pervers",
    "sérieux": "froissé",
    "calme": "hystérique",
    "aimant": "antipathique",
    "bienfait": "malfait",
    "clairvoyant": "aveugle",
    "vigilant": "inattentif",
    "douillet": "froid",
    "pétulant": "sombre",

  
}


    def invert_statement(self, text: str) -> str:
        doc = nlp(text)
        inverted_tokens = []

        for token in doc:
            lemma_lower = token.lemma_.lower()
            word_lower = token.text.lower()

            # 1. Remplacement d'antonymes stricts
            if lemma_lower in self.ANTONYMS:
                antonym = self.ANTONYMS[lemma_lower]
                # Respect de la casse
                if token.text.istitle():
                    antonym = antonym.capitalize()
                inverted_tokens.append(antonym)

            # 2. Inversion de négation / affirmation sur les verbes principaux
            elif token.pos_ == "VERB" and not token.is_stop:
                # Ajout ou suppression de la négation
                if any(child.dep_ == "advmod" and child.lemma_ in ["ne", "pas"] for child in token.children):
                    inverted_tokens.append(token.text)  # On conserve (la suppression se fera en Regex)
                else:
                    if token.text[0].lower() in "aeiouyéèêâ":
                        inverted_tokens.append(f"n'{token.text}")
                    else:
                        inverted_tokens.append(f"ne {token.text}")
            else:
                inverted_tokens.append(token.text)

        result = " ".join(inverted_tokens)

        # Nettoyage syntaxique des élisions et espaces
        result = re.sub(r"\bde le\b", "du", result)
        result = re.sub(r"\bde les\b", "des", result)
        result = re.sub(r"\bne pas ne\b", "ne", result)
        result = re.sub(r"\s+", " ", result).strip()

        return result


class ConsensusEngine:
    """Filtre de Preuves : Isole les faits incontestables et extrait les points de friction."""

    def __init__(self, match_threshold: float = 0.35):
        self.threshold = match_threshold

    def _extract_keywords(self, doc) -> set:
        return {token.lemma_.lower() for token in doc if token.pos_ in ("NOUN", "VERB", "ADJ", "PROPN") and not token.is_stop}

    def compute_consensus(self, thesis: str, antithesis: str) -> Tuple[List[str], List[Tuple[str, str]]]:
        doc_thesis = nlp(thesis)
        doc_anti = nlp(antithesis)

        sentences_thesis = [sent for sent in doc_thesis.sents]
        sentences_anti = [sent for sent in doc_anti.sents]

        consensus_facts = []
        friction_points = []

        for st in sentences_thesis:
            kw_t = self._extract_keywords(st)
            if not kw_t:
                continue

            best_score = 0.0
            best_sa = None

            for sa in sentences_anti:
                kw_a = self._extract_keywords(sa)
                if not kw_a:
                    continue

                intersection = len(kw_t.intersection(kw_a))
                union = len(kw_t.union(kw_a))
                score = intersection / union if union > 0 else 0.0

                if score > best_score:
                    best_score = score
                    best_sa = sa

            if best_score >= self.threshold:
                # Accord de sujet/cadre -> Factuel
                consensus_facts.append(st.text.strip())
            elif best_sa:
                # Désaccord -> Point de friction
                friction_points.append((st.text.strip(), best_sa.text.strip()))

        return consensus_facts, friction_points