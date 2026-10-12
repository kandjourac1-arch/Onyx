"""
Sphinx Left - Hémisphère Gauche
Rôle : Purge des hallucinations, contrôle AST/Linter, écriture physique ET lecture physique sécurisée.
"""

import ast
import io
import os
import re
from typing import Dict, Any, List, Tuple
from pyflakes import api as pyflakes_api
from pyflakes import reporter as pyflakes_reporter

class SphinxLeft:

    CODE_HALLUCINATIONS = [
        r"# Exécution automatique du script lors du démarrage du système.*",
        r"# Ce script s'exécute automatiquement au démarrage.*",
        r"# Lancement automatique activé.*",
        r"# Enregistré dans le registre Windows au démarrage.*"
    ]

    TEXT_HALLUCINATIONS = [
        r"En tant qu'intelligence artificielle, je ne peux pas.*",
        r"Je suis un modèle de langage d'IA.*",
        r"Désolé, je ne suis pas en mesure de.*"
    ]

    @classmethod
    def purge_hallucinations(cls, text: str, content_type: str = "TEXT") -> str:
        cleaned = text
        if content_type == "CODE":
            for pattern in cls.CODE_HALLUCINATIONS:
                cleaned = re.sub(pattern, "# Point d'entrée principal du script", cleaned, flags=re.IGNORECASE)
        
        for pattern in cls.TEXT_HALLUCINATIONS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
            
        return cleaned.strip()

    @classmethod
    def extract_content(cls, raw_text: str, content_type: str) -> str:
        if content_type == "CODE":
            if "```python" in raw_text:
                return raw_text.split("```python")[1].split("```")[0].strip()
            elif "```" in raw_text:
                return raw_text.split("```")[1].split("```")[0].strip()
        elif content_type == "DOCUMENT":
            if raw_text.startswith("```markdown") and raw_text.endswith("```"):
                return raw_text[11:-3].strip()
        return raw_text.strip()

    @classmethod
    def check_code_quality(cls, code_source: str) -> Tuple[bool, List[str]]:
        try:
            ast.parse(code_source)
        except SyntaxError as e:
            return False, [f"Erreur de syntaxe ligne {e.lineno} : {e.msg}"]

        w_stream, e_stream = io.StringIO(), io.StringIO()
        reporter = pyflakes_reporter.Reporter(w_stream, e_stream)
        pyflakes_api.check(code_source, filename="onyx_buffer.py", reporter=reporter)
        
        errors = [line for line in (w_stream.getvalue() + e_stream.getvalue()).splitlines() if line]
        return True, errors

    @classmethod
    def execute_physical_write(cls, target_dir: str, filename: str, content: str) -> Dict[str, Any]:
        try:
            os.makedirs(target_dir, exist_ok=True)
            full_path = os.path.join(target_dir, filename)
            
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "file_path": full_path,
                "message": f"Fichier créé avec succès : {full_path}"
            }
        except Exception as e:
            return {
                "success": False,
                "file_path": None,
                "message": f"Erreur lors de l'écriture : {str(e)}"
            }

    @classmethod
    def execute_physical_read(cls, file_path: str) -> Dict[str, Any]:
        """Lit physiquement le contenu d'un fichier local."""
        if not file_path or not os.path.exists(file_path):
            return {
                "success": False,
                "content": None,
                "message": f"Fichier introuvable : '{file_path}'"
            }

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            return {
                "success": True,
                "content": content,
                "file_path": file_path,
                "message": f"Fichier importé avec succès ({len(content)} caractères)."
            }
        except Exception as e:
            return {
                "success": False,
                "content": None,
                "message": f"Erreur de lecture du fichier : {str(e)}"
            }