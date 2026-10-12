"""
tools/algorithms/task_planner.py
Planificateur de tâches complexes et exécution autonome
"""

import time
import uuid

class TaskPlanner:
    def decompose_goal(self, goal: str) -> list[dict]:
        """1. Décompose un objectif global en sous-tâches dépendantes."""
        subtasks = [
            {"id": "t1", "desc": f"Analyser les prérequis pour : {goal}", "deps": []},
            {"id": "t2", "desc": f"Exécuter le coeur du traitement pour : {goal}", "deps": ["t1"]},
            {"id": "t3", "desc": f"Vérifier et valider les résultats pour : {goal}", "deps": ["t2"]}
        ]
        return subtasks

    def resolve_dependencies(self, tasks: list[dict]) -> list[dict]:
        """2. Algorithme de tri topologique des dépendances de tâches."""
        resolved = []
        visited = set()
        
        def visit(task):
            if task["id"] in visited:
                return
            for dep_id in task.get("deps", []):
                dep_task = next((t for t in tasks if t["id"] == dep_id), None)
                if dep_task:
                    visit(dep_task)
            visited.add(task["id"])
            resolved.append(task)
            
        for t in tasks:
            visit(t)
        return resolved

    def score_task_priority(self, urgency: int, impact: int) -> float:
        """3. Calcul du score de priorité (Urgence x Impact)."""
        return round(float(urgency * impact), 2)

    def create_execution_tree(self, root_goal: str) -> dict:
        """4. Création d'un arbre d'exécution structuré."""
        return {
            "execution_id": str(uuid.uuid4())[:8],
            "goal": root_goal,
            "status": "pending",
            "children": self.decompose_goal(root_goal)
        }

    def track_progress(self, execution_tree: dict) -> float:
        """5. Suivi du taux de progression de l'arbre d'exécution."""
        children = execution_tree.get("children", [])
        if not children:
            return 1.0 if execution_tree.get("status") == "completed" else 0.0
        completed = sum(1 for c in children if c.get("status") == "completed")
        return round(completed / len(children), 2)

    def estimate_resources(self, tasks: list[dict]) -> dict:
        """6. Estimation du temps et des jetons nécessaires."""
        estimated_seconds = len(tasks) * 5
        estimated_tokens = len(tasks) * 300
        return {
            "estimated_time_sec": estimated_seconds,
            "estimated_tokens": estimated_tokens
        }

    def execute_with_retry(self, func, max_retries: int = 3, backoff_factor: float = 1.5):
        """7. Stratégie de retry intelligente avec exponential backoff."""
        attempt = 0
        while attempt < max_retries:
            try:
                return {"success": True, "result": func()}
            except Exception as e:
                attempt += 1
                if attempt >= max_retries:
                    return {"success": False, "error": str(e)}
                time.sleep(backoff_factor ** attempt)

    def detect_parallel_tasks(self, tasks: list[dict]) -> list[list[dict]]:
        """8. Détection des tâches parallélisables (sans dépendances croisées)."""
        independent = [t for t in tasks if not t.get("deps")]
        dependent = [t for t in tasks if t.get("deps")]
        batches = []
        if independent:
            batches.append(independent)
        if dependent:
            batches.append(dependent)
        return batches

    def save_checkpoint(self, state: dict, filepath: str = "memory/planner_checkpoint.json"):
        """9. Système de point de sauvegarde pour reprise sur panne."""
        import json
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def post_mortem_analysis(self, failed_task: dict, error_msg: str) -> dict:
        """10. Analyse post-mortem automatique d'une tâche échouée."""
        return {
            "task_id": failed_task.get("id"),
            "failure_reason": error_msg,
            "recommended_action": "Réduire la taille de l'entrée ou ajuster le prompt système.",
            "retry_allowed": True
        }
