import os
import requests

def get_weather(city: str, country: str = None) -> dict:
    """
    Récupère la météo d'une ville via OpenWeatherMap.
    Utilise la clé API définie dans la variable d'environnement OPENWEATHER_API_KEY.
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        # Clé de démonstration (limitée) – remplace par ta propre clé
        api_key = "votre_cle_api_ici"
        # Pour une clé gratuite, inscris-toi sur openweathermap.org
        # et mets-la dans une variable d'environnement ou directement ici
    if api_key == "votre_cle_api_ici":
        return {
            "success": False,
            "error": "Clé API météo non configurée. Définissez OPENWEATHER_API_KEY."
        }
    query = f"{city},{country}" if country else city
    url = f"https://api.openweathermap.org/data/2.5/weather?q={query}&appid={api_key}&units=metric&lang=fr"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "success": True,
                "city": data["name"],
                "temp": data["main"]["temp"],
                "description": data["weather"][0]["description"],
                "humidity": data["main"]["humidity"],
                "wind_speed": data["wind"]["speed"]
            }
        else:
            return {"success": False, "error": f"Erreur {resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}