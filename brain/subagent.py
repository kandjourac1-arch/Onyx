# brain/subagent.py
"""
Sous-agents autonomes et gestionnaire de délégations asynchrones pour Onyx V2.
"""

import threading
import uuid
import logging
import requests
from typing import Callable, Optional, Dict, Any

logger = logging.getLogger("OnyxSubAgent")


class SubAgentWorker(threading.Thread):
    """Sous-agent autonome exécutant une mission spécialisée en tâche de fond."""

    def __init__(
        self,
        task_id: str,
        mission: str,
        synapse_engine=None,
        callback: Optional[Callable] = None,
        llm_endpoint: str = "http://127.0.0.1:1234/v1/chat/completions"
    ):
        super().__init__()
        self.task_id = task_id
        self.mission = mission
        self.synapse = synapse_engine
        self.callback = callback
        self.llm_endpoint = llm_endpoint
        self.daemon = True

    def run(self):
        logger.info(f"🤖 [Sous-Agent {self.task_id}] Démarrage de la mission : {self.mission}")

        sub_system_prompt = (
            "Tu es un sous-agent d'ONYX spécialisé. Résous la tâche demandée "
            "de manière ultra-concise, technique et précise, sans bavardage superflu."
        )

        messages = [
            {"role": "system", "content": sub_system_prompt},
            {"role": "user", "content": self.mission}
        ]

        model_name = "qwen2.5-7b-instruct"
        if self.synapse and hasattr(self.synapse, "get_fulgur_config"):
            fulgur_cfg = self.synapse.get_fulgur_config()
            model_name = fulgur_cfg.get("main_model", model_name)

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 512,
            "stream": False
        }

        try:
            res = requests.post(self.llm_endpoint, json=payload, timeout=90)
            if res.status_code == 200:
                result = res.json()["choices"][0]["message"]["content"].strip()
                logger.info(f"✅ [Sous-Agent {self.task_id}] Mission accomplie.")
                if self.callback:
                    self.callback(self.task_id, self.mission, result, success=True)
            else:
                err = f"Erreur HTTP {res.status_code}: {res.text[:120]}"
                logger.error(f"❌ [Sous-Agent {self.task_id}] {err}")
                if self.callback:
                    self.callback(self.task_id, self.mission, err, success=False)
        except Exception as e:
            logger.error(f"❌ [Sous-Agent {self.task_id}] Exception : {e}")
            if self.callback:
                self.callback(self.task_id, self.mission, str(e), success=False)


class SubAgentManager:
    """Orchestrateur lançant et suivant les sous-agents d'ONYX."""

    def __init__(self, synapse_engine=None, llm_endpoint: str = "http://127.0.0.1:1234/v1/chat/completions"):
        self.synapse = synapse_engine
        self.llm_endpoint = llm_endpoint
        self.active_tasks: Dict[str, SubAgentWorker] = {}

    def spawn_subagent(self, mission: str, callback: Optional[Callable] = None) -> str:
        """Délègue une mission à un nouveau sous-agent parallèle."""
        task_id = str(uuid.uuid4())[:6]
        worker = SubAgentWorker(
            task_id=task_id,
            mission=mission,
            synapse_engine=self.synapse,
            callback=callback,
            llm_endpoint=self.llm_endpoint
        )
        self.active_tasks[task_id] = worker
        worker.start()
        return task_id
