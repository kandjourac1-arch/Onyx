# tools/web_search.py
"""
Onyx V2 - Module de Recherche et Lecture Web
"""

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

def search_web(query: str) -> str:
    """Effectue une recherche sur le Web et renvoie les 3 premiers résultats."""
    try:
        results = list(DDGS().text(query, max_results=3))
        if not results:
            return "Aucun résultat trouvé sur le web."
        formatted_results = []
        for r in results:
            formatted_results.append(f"Titre : {r['title']}\nLien : {r['href']}\nExtrait : {r['body']}")
        return "\n\n".join(formatted_results)
    except Exception as e:
        return f"Erreur lors de la recherche web : {str(e)}"

def fetch_webpage(url: str) -> str:
    """Visite une URL, extrait le texte principal et élimine le bruit HTML."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for element in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
            element.extract()
        text = soup.get_text(separator=' ', strip=True)
        if len(text) > 3000:
            return text[:3000] + "... [Contenu tronqué]"
        return text if text else "Aucun contenu textuel lisible trouvé sur cette page."
    except Exception as e:
        return f"Impossible de lire la page web : {str(e)}"