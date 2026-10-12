"""
Onyx V2 - Module system_control.py
Gère l'exécution des commandes système et le statut de la machine.
"""

import subprocess
import platform
import os

def get_system_status() -> str:
    """Retourne des informations de base sur le statut du système."""
    try:
        os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
        node = platform.node()
        return f"Système : {os_info}, Machine : {node}, Statut : Opérationnel."
    except Exception as e:
        return f"Impossible de récupérer le statut du système : {str(e)}"

def execute_system_command(command: str) -> str:
    """
    Exécute une commande système de manière sécurisée et corrige 
    les erreurs de formatage courantes des LLMs.
    """
    command = command.strip()
    
    # 1. Si le LLM a juste renvoyé un chemin de fichier entre guillemets (comme pour Steam)
    if command.startswith('"') and command.endswith('"') and not command.startswith(('&', 'Start-Process')):
        command = f"& {command}"
    elif command.startswith("'") and command.endswith("'") and not command.startswith(('&', 'Start-Process')):
        command = f"& {command}"

    # 2. Si le LLM renvoie un chemin brut sans guillemets, on le corrige avec Start-Process
    elif "C:\\" in command and not command.startswith(('&', '"', "'", 'Start-Process', 'cd', 'ls', 'dir')):
        command = f"Start-Process -FilePath '{command}'"

    try:
        # Exécution avec le module subprocess
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            shell=False  # Garder False pour la sécurité
        )
        
        if result.returncode != 0:
            return f"Erreur d'exécution PowerShell :\n{result.stderr.strip()}"
        
        return result.stdout.strip() if result.stdout else "Commande exécutée avec succès."
        
    except Exception as e:
        return f"Erreur critique lors de l'exécution de l'outil : {str(e)}"