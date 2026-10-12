# tools/skill_agent.py
import importlib.util
import os
import inspect
from pathlib import Path

class SkillManager:
    """Gestionnaire de compétences dynamiques (compatibles scripts custom et OpenClaw)."""

    def __init__(self, skills_dir: str = "./skills"):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(exist_ok=True)
        self.loaded_skills = {}
        self.reload_skills()

    def reload_skills(self):
        """Recharge tous les modules .py du dossier skills/."""
        self.loaded_skills.clear()
        for file in self.skills_dir.glob("*.py"):
            if file.name.startswith("__"):
                continue
            skill_name = file.stem
            spec = importlib.util.spec_from_file_location(skill_name, file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Recherche de la fonction principale run() dans le skill
            if hasattr(module, "run"):
                self.loaded_skills[skill_name] = module.run

    def get_available_skills_desc(self) -> str:
        """Retourne la liste des skills disponibles sous forme de documentation pour le LLM."""
        if not self.loaded_skills:
            return "Aucun skill externe chargé."
        
        desc = ["[SKILLS DISPONIBLES]"]
        for name, func in self.loaded_skills.items():
            doc = inspect.getdoc(func) or "Pas de description."
            desc.append(f"- [SKILL: {name}] : {doc}")
        return "\n".join(desc)

    def execute_skill(self, skill_name: str, *args, **kwargs) -> dict:
        """Exécute un skill spécifique et retourne le résultat."""
        if skill_name not in self.loaded_skills:
            return {"success": False, "error": f"Skill '{skill_name}' non trouvé."}
        try:
            result = self.loaded_skills[skill_name](*args, **kwargs)
            return {"success": True, "output": str(result)}
        except Exception as e:
            return {"success": False, "error": f"Erreur lors de l'exécution du skill : {e}"}