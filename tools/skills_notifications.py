import requests
import os
from typing import Dict, Any

def send_notification(title: str, message: str, webhook_url: str = None) -> Dict[str, Any]:
    """
    Envoie une notification via webhook (Discord, Slack, etc.) ou console.
    """
    webhook_url = webhook_url or os.getenv("WEBHOOK_URL")
    if webhook_url:
        try:
            payload = {"content": f"**{title}**\n{message}"}
            resp = requests.post(webhook_url, json=payload, timeout=5)
            if resp.status_code == 200:
                return {"success": True, "message": "Notification envoyée"}
        except:
            pass
    # Fallback: afficher dans la console
    print(f"[NOTIFICATION] {title}: {message}")
    return {"success": True, "message": "Notification console"}