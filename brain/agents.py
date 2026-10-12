# brain/agents.py
import os
import re
import subprocess
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

# Importer les outils
from tools.email_tools import send_email, read_emails
from tools.weather_api import get_weather
from tools.news_api import get_news

# ============================================================
# 10. AGENTS SPÉCIALISÉS (Architecture Multi-Agents)
# ============================================================
class BaseAgent:
    def __init__(self, name, description):
        self.name = name
        self.description = description
    def execute(self, task, context):
        raise NotImplementedError

class CodeAgent(BaseAgent):
    def __init__(self):
        super().__init__("CodeAgent", "Génération, exécution et correction de code Python")

    def execute(self, task, context):
        prompt = f"Écris du code Python pour : {task}\nContexte : {context}\nRetourne UNIQUEMENT le code."
        system = "Tu es un expert en programmation Python. Écris du code propre et commenté."
        code = call_qwen_deep(prompt, system, temperature=0.2, max_tokens=2048, timeout=LLM_TIMEOUT_MEDIUM)
        if not code:
            return {"success": False, "error": "Génération de code échouée"}
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()
        result = execute_python_sandbox(code, timeout=15)
        if result["success"]:
            return {"success": True, "output": result["output"], "code": code}
        else:
            error_msg = result["error"]
            fix_prompt = f"Le code suivant a échoué avec l'erreur : {error_msg}\nCode :\n{code}\nCorrige le code."
            fixed_code = call_qwen_deep(fix_prompt, "Tu es un débogueur expert. Corrige le code.", temperature=0.1, max_tokens=2048)
            if fixed_code:
                if "```python" in fixed_code:
                    fixed_code = fixed_code.split("```python")[1].split("```")[0].strip()
                elif "```" in fixed_code:
                    fixed_code = fixed_code.split("```")[1].split("```")[0].strip()
                result2 = execute_python_sandbox(fixed_code, timeout=15)
                if result2["success"]:
                    return {"success": True, "output": result2["output"], "code": fixed_code, "corrected": True}
                else:
                    return {"success": False, "error": result2["error"], "code": fixed_code}
            else:
                return {"success": False, "error": error_msg, "code": code}

class WebAgent(BaseAgent):
    def __init__(self):
        super().__init__("WebAgent", "Recherche web, scraping et récupération d'actualités")

    def execute(self, task, context):
        if "actualité" in task or "news" in task:
            query = task.replace("actualité", "").replace("news", "").strip()
            if not query:
                query = "actualités"
            articles = get_news(query=query)
            if articles:
                msg = "**Actualités**\n\n"
                for a in articles[:5]:
                    msg += f"• {a['title']}\n  {a.get('description', '')[:150]}...\n[Lien]({a.get('url', '#')})\n\n"
                return {"success": True, "output": msg}
            else:
                return {"success": False, "error": "Aucune actualité trouvée"}
        else:
            results = fetch_web_context(task, serper_key=context.get("serper_key"))
            if results:
                return {"success": True, "output": f"Résultats de recherche :\n{results}"}
            else:
                return {"success": False, "error": "Aucun résultat de recherche"}

class MailAgent(BaseAgent):
    def __init__(self):
        super().__init__("MailAgent", "Lecture et envoi d'emails")

    def execute(self, task, context):
        if "lire" in task or "read" in task:
            result = read_emails(limit=5, unread_only=True)
            if result.get("success") and result.get("emails"):
                msg = "**Derniers emails non lus**\n\n"
                for i, e in enumerate(result["emails"], 1):
                    msg += f"{i}. **De :** {e['from']}\n   **Sujet :** {e['subject']}\n   **Aperçu :** {e.get('snippet', '(vide)')}\n\n"
                return {"success": True, "output": msg}
            else:
                return {"success": False, "error": "Aucun email non lu"}
        else:
            match = re.search(r'envoyer\s+à\s+([^\s]+)\s+sujet\s*:\s*(.+?)(?:message\s*:\s*(.*))?$', task, re.IGNORECASE)
            if match:
                to = match.group(1)
                subject = match.group(2).strip()
                body = match.group(3).strip() if match.group(3) else ""
                result = send_email(to, subject, body)
                if result.get("success"):
                    return {"success": True, "output": f"Email envoyé à {to}"}
                else:
                    return {"success": False, "error": result.get("error", "Erreur d'envoi")}
            else:
                return {"success": False, "error": "Format non reconnu. Utilisez : envoyer à [email] sujet: ... message: ..."}

class SystemAgent(BaseAgent):
    def __init__(self):
        super().__init__("SystemAgent", "Contrôle système (volume, luminosité, veille, redémarrage, statut)")

    def _set_volume(self, action, amount=None):
        if PYCAW_AVAILABLE:
            try:
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = interface.QueryInterface(IAudioEndpointVolume)
                current_volume = volume.GetMasterVolumeLevelScalar()
                if action == "mute":
                    volume.SetMute(True, None)
                    return {"success": True, "output": "Volume coupé"}
                elif action == "+":
                    new_vol = min(1.0, current_volume + amount/100.0)
                    volume.SetMasterVolumeLevelScalar(new_vol, None)
                    return {"success": True, "output": f"Volume augmenté à {int(new_vol*100)}%"}
                elif action == "-":
                    new_vol = max(0.0, current_volume - amount/100.0)
                    volume.SetMasterVolumeLevelScalar(new_vol, None)
                    return {"success": True, "output": f"Volume diminué à {int(new_vol*100)}%"}
                else:
                    return {"success": False, "error": "Action inconnue"}
            except Exception as e:
                return {"success": False, "error": f"Erreur pycaw : {e}"}
        else:
            try:
                if action == "mute":
                    subprocess.run(["nircmd", "mutesysvolume", "2"], capture_output=True, timeout=5)
                    return {"success": True, "output": "Volume coupé"}
                elif action == "+":
                    subprocess.run(["nircmd", "changesysvolume", str(amount*655)], capture_output=True, timeout=5)
                    return {"success": True, "output": f"Volume augmenté de {amount}%"}
                elif action == "-":
                    subprocess.run(["nircmd", "changesysvolume", f"-{amount*655}"], capture_output=True, timeout=5)
                    return {"success": True, "output": f"Volume diminué de {amount}%"}
                else:
                    return {"success": False, "error": "Action inconnue"}
            except Exception as e:
                return {"success": False, "error": f"Impossible de contrôler le volume : {e}"}

    def _set_brightness(self, level):
        if SBC_AVAILABLE:
            try:
                sbc.set_brightness(level)
                return {"success": True, "output": f"Luminosité réglée à {level}%"}
            except Exception as e:
                return {"success": False, "error": f"Erreur luminosité : {e}"}
        else:
            return {"success": False, "error": "Module de contrôle de luminosité non installé (screen-brightness-control)"}

    def execute(self, task, context):
        task_lower = task.lower()
        if "volume" in task_lower:
            match = re.search(r'(augmente|diminue|monte|baisse|mute)\s*(?:le\s*)?(volume)?\s*(?:de\s*)?(\d+)?', task_lower)
            if match:
                action = match.group(1)
                amount = int(match.group(3)) if match.group(3) else 10
                if action in ["augmente", "monte"]:
                    return self._set_volume("+", amount)
                elif action in ["diminue", "baisse"]:
                    return self._set_volume("-", amount)
                elif "mute" in action:
                    return self._set_volume("mute")
            else:
                return {"success": False, "error": "Commande volume non reconnue"}
        elif "luminosité" in task_lower or "brightness" in task_lower:
            match = re.search(r'(luminosité|brightness)\s+(\d+)', task_lower)
            if match:
                level = int(match.group(2))
                return self._set_brightness(level)
            else:
                return {"success": False, "error": "Spécifiez un niveau (ex: luminosité 50)"}
        elif "veille" in task_lower or "sleep" in task_lower:
            try:
                subprocess.run(["shutdown", "/h"], capture_output=True, timeout=5)
                return {"success": True, "output": "Mise en veille"}
            except:
                return {"success": False, "error": "Erreur de mise en veille"}
        elif "redémarre" in task_lower or "reboot" in task_lower:
            try:
                subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True, timeout=5)
                return {"success": True, "output": "Redémarrage dans 5 secondes"}
            except:
                return {"success": False, "error": "Erreur de redémarrage"}
        elif "éteint" in task_lower or "shutdown" in task_lower:
            try:
                subprocess.run(["shutdown", "/s", "/t", "5"], capture_output=True, timeout=5)
                return {"success": True, "output": "Extinction dans 5 secondes"}
            except:
                return {"success": False, "error": "Erreur d'extinction"}
        elif "statut" in task_lower or "status" in task_lower:
            try:
                import psutil
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                msg = f"**Statut système**\nCPU : {cpu}%\nRAM : {ram.percent}% ({ram.used//(1024**2)} MB / {ram.total//(1024**2)} MB)\nDisque : {disk.percent}% ({disk.used//(1024**3)} GB / {disk.total//(1024**3)} GB)"
                return {"success": True, "output": msg}
            except:
                return {"success": False, "error": "Impossible de récupérer les statistiques"}
        else:
            return {"success": False, "error": "Commande système non reconnue"}

class DataAgent(BaseAgent):
    def __init__(self):
        super().__init__("DataAgent", "Analyse de données, traitement NLP et statistiques")
        from tools.algorithms.data_intelligence import DataIntelligence
        self.data_intel = DataIntelligence()

    def execute(self, task, context):
        sentiment = self.data_intel.nlp_sentiment_analysis(task)
        entities = self.data_intel.extract_named_entities(task)
        intent = self.data_intel.classify_text_intent(task)
        
        output = f"**Analyse de Données & NLP**\n"
        output += f"• Intention détectée : {intent}\n"
        output += f"• Sentiment : {sentiment['sentiment']} (score: {sentiment['score']})\n"
        if any(entities.values()):
            output += f"• Entités extraites : {entities}\n"
        return {"success": True, "output": output}

class PlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__("PlannerAgent", "Planification de tâches complexes et décomposition")
        from tools.algorithms.task_planner import TaskPlanner
        self.planner = TaskPlanner()

    def execute(self, task, context):
        subtasks = self.planner.decompose_goal(task)
        est = self.planner.estimate_resources(subtasks)
        
        output = f"**Planification d'Objectif**\n\n"
        output += f"**Estimation** : ~{est['estimated_time_sec']}s, {est['estimated_tokens']} jetons.\n\n"
        output += "**Étapes à exécuter :**\n"
        for st in subtasks:
            output += f"- [{st['id']}] {st['desc']}\n"
        return {"success": True, "output": output}

