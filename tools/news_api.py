import requests
from typing import List, Dict

try:
    import feedparser
except ImportError:
    feedparser = None

def get_news(query: str = None, category: str = None, max_results: int = 5) -> List[Dict]:
    """
    Récupère des actualités via RSS (France Info par défaut).
    """
    feed_url = "https://www.francetvinfo.fr/titres.rss"
    try:
        if feedparser is None:
            return [{
                "title": "Actualités indisponibles",
                "description": "Le module 'feedparser' n'est pas installé.",
                "url": ""
            }]
        feed = feedparser.parse(feed_url)
        results = []
        for entry in feed.entries[:max_results]:
            title = entry.title
            description = entry.summary if hasattr(entry, 'summary') else ""
            link = entry.link if hasattr(entry, 'link') else ""
            # Filtre par mot-clé si spécifié
            if query:
                if query.lower() not in title.lower() and query.lower() not in description.lower():
                    continue
            results.append({
                "title": title,
                "description": description,
                "url": link
            })
        return results
    except Exception as e:
        return [{"title": "Erreur", "description": str(e), "url": ""}]
