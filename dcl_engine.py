"""
Onyx V2 - Double-Cerveau Latéral (DCL Engine)
Routage multi-modèles sur port unique LM Studio (127.0.0.1:1234)
Intégration de l'Analyseur de Code et de la Sécurité
"""

import ast
import io
import os
import requests
from pyflakes import api as pyflakes_api
from pyflakes import reporter as pyflakes_reporter
from tools.algorithms.code_analyzer import CodeAnalyzer

SYSTEM_PROMPT_CB = """Tu es un compilateur de code Python ultra-strict. 
Tu reçois une fonction ou un script et une instruction, tu renvoies UNIQUEMENT le bloc de code corrigé sans explication, sans markdown superflu si non nécessaire.

Exemple :
Entrée : def add(a,b): return a-b | Instruction : corriger la soustraction en addition
Sortie :
def add(a, b):
    return a + b
"""

SYSTEM_PROMPT_CH = (
    "Tu es l'Architecte Logiciel (CH). "
    "Ton rôle est EXCLUSIVEMENT de lister 3 étapes textuelles abstraites. "
    "INTERDICTION ABSOLUE d'écrire du code Python, des fonctions ou d'utiliser des blocs de code (```). "
    "Sois extrêmement bref."
)

class DoubleCerveauEngine:
    def __init__(self, 
                 base_url: str = "http://127.0.0.1:1234/v1",
                 model_ch: str = "qwen2.5-7b-instruct",
                 model_cb: str = "qwen2.5-coder-0.5b-instruct",
                 model_embed: str = "text-embedding-nomic-embed-text-v1.5"):
        
        self.base_url = base_url.rstrip("/")
        self.model_ch = model_ch
        self.model_cb = model_cb
        self.model_embed = model_embed
        self.analyzer = CodeAnalyzer()

    def _call_chat(self, model: str, prompt: str, system_prompt: str, max_tokens: int = 500, temp: float = 0.1) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": False
        }
        try:
            res = requests.post(url, json=payload, timeout=60)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"].strip()
            return f"# Erreur LLM {res.status_code}"
        except Exception as e:
            return f"# Exception Connexion: {str(e)}"

    def get_embedding(self, text: str, is_query: bool = False) -> list:
        prefix = "search_query: " if is_query else "search_document: "
        formatted_text = f"{prefix}{text.strip()}"
        
        url = f"{self.base_url}/embeddings"
        payload = {"model": self.model_embed, "input": formatted_text}
        
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                return res.json()["data"][0]["embedding"]
            return []
        except Exception:
            return []

    def extraire_graphe_ast(self, code_source: str) -> dict:
        try:
            tree = ast.parse(code_source)
            fonctions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            complexity = self.analyzer.calculate_cyclomatic_complexity(code_source)
            sec_alerts = self.analyzer.security_scanner(code_source)
            return {"classes": classes, "fonctions": fonctions, "complexity": complexity, "security_alerts": sec_alerts}
        except SyntaxError as e:
            return {"erreur_syntaxe": str(e)}

    def verifier_code_linter(self, code_source: str) -> list:
        warning_stream = io.StringIO()
        error_stream = io.StringIO()
        reporter = pyflakes_reporter.Reporter(warning_stream, error_stream)
        pyflakes_api.check(code_source, filename="temp.py", reporter=reporter)
        errors = [e for e in (warning_stream.getvalue() + error_stream.getvalue()).strip().split('\n') if e]
        sec_alerts = self.analyzer.security_scanner(code_source)
        return errors + sec_alerts

    def traiter_demande(self, instruction: str, chemin_fichier: str = None) -> str:
        """Point d'entrée universel du DCL."""
        
        if chemin_fichier and os.path.exists(chemin_fichier):
            return self.refactoriser_fichier(chemin_fichier, instruction)

        print("[CH - Architecte 7B] Planification de la tâche...")
        prompt_ch = f"Instruction : {instruction}\nDonne un plan d'action en 3 points maximum sous forme de texte simple. Pas de code."
        plan = self._call_chat(
            model=self.model_ch,
            prompt=prompt_ch,
            system_prompt=SYSTEM_PROMPT_CH,
            max_tokens=80,
            temp=0.1
        )
        print(f"[CH Plan] :\n{plan}")

        print("[CB - Cerveau Bas 0.5B] Génération du code...")
        prompt_cb = (
            f"[PLAN D'ARCHITECTURE]\n{plan}\n\n"
            f"[INSTRUCTION]\n{instruction}\n\n"
            "Écris le code complet correspondant."
        )
        code_genere = self._call_chat(
            model=self.model_cb,
            prompt=prompt_cb,
            system_prompt=SYSTEM_PROMPT_CB,
            max_tokens=800,
            temp=0.0
        )

        if "```python" in code_genere:
            code_genere = code_genere.split("```python")[1].split("```")[0].strip()
        elif "```" in code_genere:
            code_genere = code_genere.split("```")[1].split("```")[0].strip()

        return code_genere

    def refactoriser_fichier(self, chemin_fichier: str, instruction: str) -> str:
        with open(chemin_fichier, "r", encoding="utf-8") as f:
            code_original = f.read()

        graphe = self.extraire_graphe_ast(code_original)
        
        prompt_ch = f"Graphe et métriques : {graphe}\nInstruction : {instruction}\nDonne un plan court (max 3 points). Pas de code."
        plan = self._call_chat(
            model=self.model_ch,
            prompt=prompt_ch,
            system_prompt=SYSTEM_PROMPT_CH,
            max_tokens=80,
            temp=0.1
        )

        prompt_cb = (
            "[CODE ORIGINAL]\n"
            f"{code_original}\n\n"
            "[PLAN]\n"
            f"{plan}\n\n"
            "[INSTRUCTION]\n"
            f"{instruction}"
        )
        
        code_genere = self._call_chat(
            model=self.model_cb,
            prompt=prompt_cb,
            system_prompt=SYSTEM_PROMPT_CB,
            max_tokens=800,
            temp=0.0
        )

        if "```python" in code_genere:
            code_genere = code_genere.split("```python")[1].split("```")[0].strip()
        elif "```" in code_genere:
            code_genere = code_genere.split("```")[1].split("```")[0].strip()

        erreurs = self.verifier_code_linter(code_genere)
        tentatives = 0
        while erreurs and tentatives < 2:
            prompt_fix = f"[CODE]\n{code_genere}\n\n[ERREURS LINTER & SÉCURITÉ]\n{erreurs}\nCorrige les erreurs."
            code_genere = self._call_chat(model=self.model_cb, prompt=prompt_fix, system_prompt=SYSTEM_PROMPT_CB, max_tokens=800, temp=0.0)
            if "```python" in code_genere:
                code_genere = code_genere.split("```python")[1].split("```")[0].strip()
            elif "```" in code_genere:
                code_genere = code_genere.split("```")[1].split("```")[0].strip()
            erreurs = self.verifier_code_linter(code_genere)
            tentatives += 1

        return code_genere