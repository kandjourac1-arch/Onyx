import importlib
import os
from typing import Dict, Any

class SkillRegistry:
    """Détecte et charge dynamiquement les compétences Python dans le dossier skills/"""
    
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = skills_dir
        self.loaded_skills: Dict[str, Any] = {}
        if not os.path.exists(skills_dir):
            os.makedirs(skills_dir)
        self.reload_skills()

    def reload_skills(self):
        """Recharge tous les modules .py sans relancer Onyx."""
        for file in os.listdir(self.skills_dir):
            if file.endswith(".py") and not file.startswith("__"):
                skill_name = file[:-3]
                # Import dynamique à chaud
                module = importlib.import_module(f"{self.skills_dir}.{skill_name}")
                importlib.reload(module)  # Met à jour si le fichier a changé
                self.loaded_skills[skill_name] = module
                print(f"⚡ Skill Onyx actif : {skill_name}")

    def execute_skill(self, skill_name: str, function_name: str, *args, **kwargs):
        """Exécute une fonction spécifique d'un skill chargé."""
        if skill_name in self.loaded_skills:
            skill_module = self.loaded_skills[skill_name]
            func = getattr(skill_module, function_name, None)
            if func:
                return func(*args, **kwargs)
        raise ValueError(f"Skill ou fonction introuvable : {skill_name}.{function_name}")