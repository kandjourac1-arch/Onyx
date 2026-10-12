"""
Onyx V2 - Kairos Engine (Gestionnaire Temporel et Suivi de Session)
"""

from datetime import datetime

class KairosEngine:
    """Gère le contexte temporel, les horodatages et le suivi chronologique des actions."""

    def get_current_time_context(self) -> str:
        """Retourne la date et l'heure actuelles formatées pour le prompt."""
        now = datetime.now()
        return now.strftime("%A %d %B %Y à %H:%M:%S")

    def format_event_log(self, event_description: str) -> str:
        """Formate une entrée d'événement horodatée."""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        return f"{timestamp} {event_description}"