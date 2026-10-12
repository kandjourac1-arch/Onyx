"""
Sphinx Right - Hémisphère Droit
Rôle : Perception, détection des intentions (Création OS, Lecture/Importation OS) et extraction de chemins.
"""

import os
import re
from typing import Dict, Any

class SphinxRight:

    @staticmethod
    def calculate_complexity(user_input: str) -> float:
        score = 0.0
        words = user_input.split()
        score += min(len(words) / 40.0, 0.3)

        complex_keywords = [
            "refactor", "optimiser", "architecture", "classe", "héritage",
            "async", "thread", "ast", "arbre", "bug", "exception", "algo", 
            "dcl", "ia", "réseau", "base de données", "api", "gui", "interface",
            "analyse", "synthétise", "rapport", "déploie", "configure", "importe", "lis"
        ]
        matches = sum(1 for kw in complex_keywords if kw in user_input.lower())
        score += min(matches * 0.12, 0.4)

        if any(kw in user_input for kw in ["def ", "class ", "import ", "{", "```"]):
            score += 0.3

        return round(min(score, 1.0), 2)

    @classmethod
    def analyze_intent(cls, user_input: str) -> Dict[str, Any]:
        complexity = cls.calculate_complexity(user_input)
        user_lower = user_input.lower()

        desktop_patterns = [r"sur le bureau", r"sur mon bureau", r"desktop"]
        is_desktop = any(re.search(p, user_lower) for p in desktop_patterns)

        create_patterns = [r"crée", r"fais", r"génère", r"écris", r"mets", r"place", r"sauvegarde"]
        is_create = any(re.search(p, user_lower) for p in create_patterns)

        # Mots-clés pour la LECTURE / IMPORTATION
        read_patterns = [r"lis", r"importe", r"charge", r"ouvre", r"analyse le fichier", r"inspecte", r"examine"]
        is_read = any(re.search(p, user_lower) for p in read_patterns)

        is_code = bool(re.search(r"(code|script|python|html|js|c\+\+|c#|\.py|\.json|\.js|\.html)", user_lower)) or complexity > 0.4
        is_doc = bool(re.search(r"(rapport|résumé|document|lettre|texte|\.txt|\.md)", user_lower))

        action_os = None
        target_path = None
        suggested_filename = None
        content_type = "TEXT"

        # 1. Action d'Importation / Lecture
        if is_read:
            action_os = "READ_FILE"
            # Extraction d'un chemin de fichier ou nom entre guillemets ou selon motif extension
            match = re.search(r'["\']([^"\']+\.[a-zA-Z0-9]+)["\']|([a-zA-Z0-9_\-\/\\]+\.[a-zA-Z0-9]+)', user_input)
            if match:
                extracted_path = match.group(1) or match.group(2)
                target_path = os.path.expanduser(extracted_path)
                if is_desktop and not os.path.isabs(target_path):
                    target_path = os.path.join(os.path.expanduser("~"), "Desktop", os.path.basename(target_path))
            content_type = "CODE" if is_code else "DOCUMENT"

        # 2. Action de Création
        elif is_create and is_desktop:
            action_os = "CREATE_FILE_DESKTOP"
            target_path = os.path.join(os.path.expanduser("~"), "Desktop")
            if is_code:
                content_type = "CODE"
                suggested_filename = "app_ia.py" if "ia" in user_lower else "script_onyx.py"
            elif is_doc:
                content_type = "DOCUMENT"
                suggested_filename = "document_onyx.md"
            else:
                suggested_filename = "sortie_onyx.txt"
        elif is_code:
            content_type = "CODE"

        # Détermination du mode
        if action_os:
            intent_type = "ACTION_OS"
        elif complexity >= 0.7:
            intent_type = "EXPERT"
        elif len(user_input.split()) < 6 and not is_code:
            intent_type = "RAPIDE"
        else:
            intent_type = "STANDARD"

        return {
            "intent": intent_type,
            "complexity": complexity,
            "action_os": action_os,
            "target_path": target_path,
            "suggested_filename": suggested_filename,
            "content_type": content_type,
            "raw_prompt": user_input
        }