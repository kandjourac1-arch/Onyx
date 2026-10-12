import urllib.request
from bs4 import BeautifulSoup


class WebNavigator:
    def __init__(self):
        pass

    def fetch_page(self, url: str) -> dict:
        """
        Récupère et nettoie le contenu textuel d'une URL web.
        
        Retourne :
            {"success": bool, "url": str, "content": str, "error": str}
        """
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
            soup = BeautifulSoup(html, 'html.parser')
            for script in soup(["script", "style"]):
                script.extract()
                
            text = soup.get_text(separator=' ')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return {
                "success": True,
                "url": url,
                "content": clean_text[:4000],
                "error": ""
            }
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "content": "",
                "error": str(e)
            }
