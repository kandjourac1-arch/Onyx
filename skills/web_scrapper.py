# skills/web_scraper.py
import urllib.request
from bs4 import BeautifulSoup

def run(url: str) -> str:
    """Extrait le contenu texte principal d'une page Web depuis une URL."""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
    
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup(["script", "style"]):
        script.extract()
    
    text = soup.get_text(separator=' ')
    lines = (line.strip() for line in text.splitlines())
    return ' '.join(chunk for chunk in lines if chunk)[:1500]