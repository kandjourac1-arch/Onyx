# tools/system_agent.py

import os
import subprocess
import platform

try:
    import psutil
except ImportError:
    psutil = None


class SystemAgent:
    def __init__(self):
        pass

    def launch_app(self, app_name: str) -> dict:
        system = platform.system().lower()
        app_clean = app_name.strip()
        try:
            if "windows" in system:
                try:
                    os.startfile(app_clean)
                except Exception:
                    subprocess.Popen(f"start {app_clean}", shell=True)
            elif "darwin" in system:
                subprocess.Popen(["open", "-a", app_clean])
            else:
                subprocess.Popen([app_clean], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "message": f"Lancement de '{app_clean}' réussi."}
        except Exception as e:
            return {"success": False, "message": f"Échec du lancement de '{app_clean}': {str(e)}"}

    def get_system_status(self) -> str:
        if psutil is None:
            return "Optionnel : installez 'psutil' (`pip install psutil`) pour un rapport détaillé du système."
        try:
            cpu_usage = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            status_report = (
                "**Rapport d'état système (ONYX)**\n"
                f"• Processeur (CPU) : {cpu_usage}%\n"
                f"• Mémoire RAM     : {ram.percent}% ({ram.used // (1024**2)} MB / {ram.total // (1024**2)} MB)\n"
                f"• Espace Disque   : {disk.percent}% ({disk.used // (1024**3)} GB / {disk.total // (1024**3)} GB libres)"
            )
            return status_report
        except Exception as e:
            return f"Erreur lors de la récupération de l'état système : {str(e)}"
