# brain/kairos.py
"""
KAIROS : Moteur Temporel, Contexte Chronologique, Débat Dialectique (Thèse / Antithèse)
et Consensus de Preuves (NLP & LLM).
"""

import inspect
import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Callable, Sequence

# Support optionnel spaCy pour inversion linguistique ultra-rapide (< 1 ms)
_NLP_INSTANCE = None

def _get_nlp():
    global _NLP_INSTANCE
    if _NLP_INSTANCE is not None:
        return _NLP_INSTANCE
    try:
        import spacy
        try:
            _NLP_INSTANCE = spacy.load("fr_core_news_sm")
        except Exception:
            _NLP_INSTANCE = None
    except ImportError:
        _NLP_INSTANCE = None
    return _NLP_INSTANCE


class LinguisticMirror:
    """Miroir Linguistique : Génère l'exacte antithèse en < 1 ms via NLP si disponible."""

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

    # Continue with more words...
}


    def invert_statement(self, text: str) -> str:
        nlp = _get_nlp()
        if not nlp:
            # Fallback textuel simple sans spaCy
            words = text.split()
            inverted = []
            for w in words:
                clean_w = w.lower().strip(",.?!;")
                if clean_w in self.ANTONYMS:
                    ant = self.ANTONYMS[clean_w]
                    inverted.append(ant.capitalize() if w[0].isupper() else ant)
                else:
                    inverted.append(w)
            return "Au contraire : " + " ".join(inverted)

        doc = nlp(text)
        inverted_tokens = []

        for token in doc:
            lemma_lower = token.lemma_.lower()
            if lemma_lower in self.ANTONYMS:
                antonym = self.ANTONYMS[lemma_lower]
                if token.text.istitle():
                    antonym = antonym.capitalize()
                inverted_tokens.append(antonym)
            elif token.pos_ == "VERB" and not token.is_stop:
                if any(child.dep_ == "advmod" and child.lemma_ in ["ne", "pas"] for child in token.children):
                    inverted_tokens.append(token.text)
                else:
                    if token.text[0].lower() in "aeiouyéèêâ":
                        inverted_tokens.append(f"n'{token.text}")
                    else:
                        inverted_tokens.append(f"ne {token.text}")
            else:
                inverted_tokens.append(token.text)

        result = " ".join(inverted_tokens)
        result = re.sub(r"\bde le\b", "du", result)
        result = re.sub(r"\bde les\b", "des", result)
        result = re.sub(r"\bne pas ne\b", "ne", result)
        result = re.sub(r"\s+", " ", result).strip()
        return result


class ConsensusEngine:
    """ConsensusEngine : Isole les faits communs et points de friction."""

    def __init__(self, match_threshold: float = 0.30):
        self.threshold = match_threshold

    @staticmethod
    def extract_keywords_simple(text: str) -> set:
        words = re.findall(r'\b[a-zA-ZÀ-ÿ]{4,}\b', text.lower())
        stopwords = {"pour", "dans", "avec", "cette", "votre", "nous", "vous", "leur", "plus", "tout", "faire", "sont", "être", "avoir"}
        return set(words) - stopwords

    def extract_consensus(self, thesis: str, antithesis: str) -> str:
        """Découpe en phrases et trouve les recoupements thématiques."""
        sentences_t = [s.strip() for s in re.split(r'[.!?\n]', thesis) if len(s.strip()) > 10]
        sentences_a = [s.strip() for s in re.split(r'[.!?\n]', antithesis) if len(s.strip()) > 10]

        consensus = []
        for st in sentences_t:
            kw_t = self.extract_keywords_simple(st)
            if not kw_t:
                continue
            for sa in sentences_a:
                kw_a = self.extract_keywords_simple(sa)
                common = kw_t.intersection(kw_a)
                if len(common) >= 2:
                    consensus.append(st)
                    break

        if consensus:
            return " ".join(consensus)
        return "Aucun consensus strict immédiat n'a été extrait ; synthèse équilibrée recommandée."


class KairosEngine:
    """
    KairosEngine : Coordonnateur temporel et arbitre dialectique d'Onyx V2.
    """

    def __init__(self):
        self.mirror = LinguisticMirror()
        self.consensus_engine = ConsensusEngine()

    def get_time_context(self) -> str:
        """Fournit la date et l'heure actuelles formatées."""
        return datetime.now().strftime("%A %d %B %Y à %H:%M:%S")

    def format_event_log(self, event_description: str) -> str:
        """Génère une ligne de log horodatée."""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        return f"{timestamp} {event_description}"

    def extract_consensus(self, thesis: str, antithesis: str) -> str:
        """Extrait les points communs entre deux positions."""
        return self.consensus_engine.extract_consensus(thesis, antithesis)

    def run_debate(
        self,
        user_prompt: str,
        call_qwen_fn: Optional[Callable] = None,
        call_mistral_fn: Optional[Callable] = None
    ) -> Dict[str, str]:
        """
        Déclenche le débat contradictoire dialectique :
        1. Thèse (avocat constructif via Qwen ou NLP)
        2. Antithèse (avocat critique via Mistral ou LinguisticMirror)
        3. Synthèse/Consensus des points incontestables
        """
        # 1. Thèse
        thesis_prompt = f"Rédige une réponse argumentée, claire et constructive à : {user_prompt} (max 100 mots)"
        if call_qwen_fn:
            thesis = call_qwen_fn(thesis_prompt, "Tu es un avocat défenseur et bâtisseur.")
        else:
            thesis = f"Position initiale concernant : {user_prompt}"

        thesis = thesis or "Thèse non disponible."

        # 2. Antithèse
        if call_mistral_fn:
            anti_prompt = f"Attaque point par point et critique de manière impitoyable cette thèse : {thesis}"
            antithesis = call_mistral_fn(anti_prompt)
        else:
            # Fallback miroir linguistique < 1 ms
            antithesis = self.mirror.invert_statement(thesis)

        antithesis = antithesis or "Antithèse non disponible."

        # 3. Consensus
        consensus = self.extract_consensus(thesis, antithesis)

        return {
            "thesis": thesis,
            "antithesis": antithesis,
            "consensus": consensus
        }


# Alias pour rétrocompatibilité
DebateEngine = KairosEngine
