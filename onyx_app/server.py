"""
ONYX V2 - AGENT TOTALEMENT ADAPTATIF (ZERO PRÉDÉFINI)
- Détection d'intention ultra‑précise pour les commandes système
- Exécution automatique des actions (création de dossier, fichiers, etc.)
- Pipeline NEXUS/SYNAPSE/KAIROS/QWEN complet
- S'adapte à la situation sans rien de pré‑défini
"""

import sys
import os
import json
import time
import threading
import hashlib
import ast
import io
import re
import urllib.parse
import subprocess
import traceback
import argparse
import secrets
import logging
import atexit
from functools import wraps
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, jsonify, render_template_string, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests
from bs4 import BeautifulSoup
import bcrypt
from storage import get_storage

# --- Ignorer les warnings Eventlet ---
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- Tentative d'import des librairies de contrôle système (Windows) ---
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False

try:
    import screen_brightness_control as sbc
    SBC_AVAILABLE = True
except ImportError:
    SBC_AVAILABLE = False

# ============================================================
# 1. CONFIGURATION
# ============================================================
app = Flask(__name__)
app.secret_key = os.environ.get("ONYX_SECRET_KEY") or secrets.token_hex(32)
_cors_origins = [origin.strip() for origin in os.environ.get("ONYX_CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000").split(",") if origin.strip()]
CORS(app, resources={r"/api/*": {"origins": _cors_origins}})
socketio = SocketIO(app, cors_allowed_origins=_cors_origins, async_mode='threading')
app.config.update(MAX_CONTENT_LENGTH=10 * 1024 * 1024, JSON_SORT_KEYS=False)
logger = logging.getLogger("onyx")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("ONYX_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
MAX_PROMPT_LENGTH = 32_000
MAX_CODE_LENGTH = 50_000
MAX_RESPONSE_LENGTH = 100_000

# Paramètres exposés dans l'interface. Les bornes évitent qu'une préférence
# persistée ou falsifiée ne provoque des requêtes LLM disproportionnées.
DEFAULT_USER_SETTINGS = {
    "language": "fr",
    "theme": "dark",
    "voice_enabled": True,
    "cloud_sync": False,
    "serper_key": "",
    "model": "qwen2.5-7b-instruct",
    "temperature": 0.3,
    "max_tokens": 1024,
    "request_timeout": 120,
    "compact_memory": True,
}

def normalize_user_settings(raw):
    """Retourne uniquement des réglages sûrs et bornés pour le client et le LLM."""
    raw = raw if isinstance(raw, dict) else {}
    result = dict(DEFAULT_USER_SETTINGS)
    language = str(raw.get("language", result["language"]))
    if language in LANGUAGE_NAMES:
        result["language"] = language
    theme = str(raw.get("theme", result["theme"]))
    if theme in {"dark", "light", "system"}:
        result["theme"] = theme
    result["voice_enabled"] = bool(raw.get("voice_enabled", result["voice_enabled"]))
    result["cloud_sync"] = bool(raw.get("cloud_sync", result["cloud_sync"]))
    result["compact_memory"] = bool(raw.get("compact_memory", result["compact_memory"]))
    result["serper_key"] = str(raw.get("serper_key", result["serper_key"]))[:256]
    model = str(raw.get("model", result["model"]))
    if model in {MAIN_BRAIN, SUB_BRAIN}:
        result["model"] = model
    try:
        temperature = float(raw.get("temperature", result["temperature"]))
        result["temperature"] = round(max(0.0, min(1.5, temperature)), 2)
    except (TypeError, ValueError):
        pass
    try:
        max_tokens = int(raw.get("max_tokens", result["max_tokens"]))
        result["max_tokens"] = max(128, min(4096, max_tokens))
    except (TypeError, ValueError):
        pass
    try:
        timeout = int(raw.get("request_timeout", result["request_timeout"]))
        result["request_timeout"] = max(15, min(300, timeout))
    except (TypeError, ValueError):
        pass
    return result

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
MAIN_BRAIN = "qwen2.5-7b-instruct"
SUB_BRAIN = "mistral-7b-instruct-v0.2"
ORCHESTRATOR_BRAIN = "ministral-3b"

LLM_TIMEOUT_LONG = 120
LLM_TIMEOUT_MEDIUM = 60
LLM_TIMEOUT_SHORT = 30

http_session = requests.Session()
http_session.headers.update({"Content-Type": "application/json"})
executor = ThreadPoolExecutor(max_workers=6)

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
}

LANGUAGE_NAMES = {
    'fr': 'Français', 'en': 'English', 'es': 'Español',
    'de': 'Deutsch', 'it': 'Italiano', 'pt': 'Português',
    'ru': 'Русский', 'zh': '中文'
}

# ============================================================
# 2. SKILLS & UTILITAIRES & MOTEUR VOCAL
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if '__file__' in globals() else os.getcwd()
onyx_storage = get_storage(os.path.join(BASE_DIR, "onyx.db"))
if not onyx_storage.get_setting("json_migration_v1", False):
    onyx_storage.migrate_from_json(BASE_DIR)
    onyx_storage.set_setting("json_migration_v1", True)
atexit.register(onyx_storage.close)
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
BRAIN_DIR = os.path.join(BASE_DIR, "brain")
sys.path.insert(0, SKILLS_DIR)
sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, BRAIN_DIR)

# --- NOYAU COGNITIF UNIFIÉ (BRAIN / NEXUS / KAIROS / SYNAPSE X) ---
try:
    from brain import NexusCore, KairosEngine, SynapseXCore, MemoryManager, CognitiveRouter, DoubleCerveauEngine
    brain_memory = MemoryManager()
    brain_kairos = KairosEngine()
    brain_synapse = SynapseXCore()
    SynapseXCore.set_memory_manager(brain_memory)
    brain_nexus = NexusCore(memory_manager=brain_memory, kairos_engine=brain_kairos, synapse_router=brain_synapse)
    logger.info("ONYX Core cognitive modules initialized")
except Exception as _e_brain:
    logger.warning("ONYX Core initialization warning: %s", type(_e_brain).__name__)
    brain_memory = None
    brain_kairos = None
    brain_synapse = None
    brain_nexus = None

try:
    from brain.sentiment import SentimentEngine
    sentiment_engine = SentimentEngine(memory_dir=os.path.join(BASE_DIR, "memory"))
except Exception as _e_sentiment:
    logger.warning("ONYX sentiment module unavailable: %s", type(_e_sentiment).__name__)
    sentiment_engine = None

try:
    from tools.voice_engine import VoiceAssistant, TTSEngine, STTEngine
    VOICE_AVAILABLE = True
except ImportError:
    try:
        from voice_engine import VoiceAssistant, TTSEngine, STTEngine
        VOICE_AVAILABLE = True
    except ImportError:
        VOICE_AVAILABLE = False
        class VoiceAssistant:
            def __init__(self, *args, **kwargs):
                self.state = "idle"
                self.wakeword = "hey_jarvis"
            def start(self): pass
            def stop(self): pass
            def toggle(self): return False

try:
    from tools.email_tools import send_email, read_emails
except ImportError:
    try:
        from skills.email_tools import send_email, read_emails
    except ImportError:
        pass
if 'send_email' not in dir():
    def send_email(*args, **kwargs):
        return {"success": False, "error": "Email non disponible"}
    def read_emails(*args, **kwargs):
        return {"success": False, "error": "Email non disponible"}

try:
    from tools.weather_api import get_weather
except ImportError:
    try:
        from skills.weather_api import get_weather
    except ImportError:
        pass
if 'get_weather' not in dir():
    def get_weather(city):
        return {"success": False, "error": "Météo non disponible"}

try:
    from tools.news_api import get_news
except ImportError:
    try:
        from skills.news_api import get_news
    except ImportError:
        pass
if 'get_news' not in dir():
    def get_news(query=None):
        return [{"title": "News non disponible"}]

try:
    from tools.file_monitor import FileMonitor
except ImportError:
    try:
        from skills.file_monitor import FileMonitor
    except ImportError:
        pass
if 'FileMonitor' not in dir():
    class FileMonitor:
        def __init__(self, callback):
            self.callback = callback
            self.watched_files = {}
        def add_file(self, path): pass
        def start(self, interval=30): pass
        def stop(self): pass

try:
    from tools.skills_notifications import send_notification
except ImportError:
    try:
        from skills.notification import send_notification
    except ImportError:
        pass
if 'send_notification' not in dir():
    def send_notification(title, message):
        print(f"[NOTIF] {title}: {message}")

# ============================================================
# 3. MOTEURS DE RECHERCHE
# ============================================================
web_cache = {}
web_cache_lock = threading.RLock()
WEB_CACHE_TTL = 600

def search_duckduckgo_recent(query, max_results=2):
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}&df=d"
        resp = http_session.get(url, headers=HEADERS_BROWSER, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for result in soup.find_all('div', class_='result__body', limit=max_results):
                title_elem = result.find('a', class_='result__a')
                snippet_elem = result.find('a', class_='result__snippet')
                if title_elem and snippet_elem:
                    results.append(f"• {title_elem.get_text(strip=True)}\n  {snippet_elem.get_text(strip=True)}")
            return results
    except Exception as e:
        print(f"[DDG ERROR] {e}")
    return []

def search_qwant(query, max_results=2):
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.qwant.com/v3/search/web?q={encoded_query}&count={max_results}&locale=fr_FR"
        resp = http_session.get(url, headers=HEADERS_BROWSER, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", {}).get("result", {}).get("items", {}).get("mainline", [])
            results = []
            for item in items:
                for res in item.get("items", []):
                    title = res.get("title")
                    desc = res.get("desc")
                    if title and desc:
                        results.append(f"• {title}\n  {desc}")
                        if len(results) >= max_results:
                            break
            return results
    except Exception as e:
        print(f"[QWANT ERROR] {e}")
    return []

def search_google_recent(query, max_results=2):
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded_query}&tbs=qdr:d&hl=fr"
        resp = http_session.get(url, headers=HEADERS_BROWSER, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for g in soup.find_all('div', class_='g', limit=max_results):
                title = g.find('h3')
                snippet = g.find('div', class_='VwiC3b')
                if title and snippet:
                    results.append(f"• {title.get_text(strip=True)}\n  {snippet.get_text(strip=True)}")
            return results
    except Exception as e:
        print(f"[GOOGLE ERROR] {e}")
    return []

def search_serper_api(query, api_key, max_results=2):
    try:
        url = "https://google.serper.dev/search"
        payload = {"q": query, "gl": "fr", "hl": "fr", "tbs": "qdr:d", "num": max_results}
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        resp = http_session.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get('organic', []):
                results.append(f"• {item.get('title')}\n  {item.get('snippet')}")
            return results
    except Exception as e:
        print(f"[SERPER ERROR] {e}")
    return []

def fetch_web_context(query, serper_key=None):
    key = f"{query}:{serper_key}"
    now = time.time()
    with web_cache_lock:
        cached = web_cache.get(key)
        if cached and (now - cached['time']) < WEB_CACHE_TTL:
            return cached['data']
        # Le cache est volontairement borné : les requêtes anciennes ne
        # doivent pas retenir indéfiniment des contextes potentiellement lourds.
        expired = [cache_key for cache_key, item in web_cache.items()
                   if now - item.get('time', 0) >= WEB_CACHE_TTL]
        for cache_key in expired:
            web_cache.pop(cache_key, None)
    results = []
    if serper_key:
        results = search_serper_api(query, serper_key)
    if not results:
        results = search_duckduckgo_recent(query)
    if not results:
        results = search_qwant(query)
    if not results:
        results = search_google_recent(query)
    data = "\n\n".join(results) if results else None
    with web_cache_lock:
        web_cache[key] = {'data': data, 'time': time.time()}
    return data

# ============================================================
# 4. GESTION UTILISATEURS (THREAD-SAFE & ROBUSTE)
# ============================================================
USERS_DIR = os.path.join(BASE_DIR, "users")
USERS_FILE = os.path.join(USERS_DIR, "users.json")
os.makedirs(USERS_DIR, exist_ok=True)

_users_lock = threading.RLock()
_history_lock = threading.RLock()
_ltm_lock = threading.RLock()

def load_users() -> dict:
    """Charge les utilisateurs avec verrou de synchronisation et fallback sécurisé."""
    with _users_lock:
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                print(f"[Users] Avertissement: Erreur lors de la lecture de {USERS_FILE} ({e}). Tentative de récupération.")
        return {}

def save_users(users: dict):
    """Sauvegarde atomique et thread-safe du fichier users.json."""
    with _users_lock:
        try:
            temp_file = USERS_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
            if os.path.exists(USERS_FILE):
                os.replace(temp_file, USERS_FILE)
            else:
                os.rename(temp_file, USERS_FILE)
        except Exception as e:
            print(f"[Users] Erreur sauvegarde: {e}")
            try:
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(users, f, ensure_ascii=False, indent=2)
            except Exception as e2:
                print(f"[Users] Erreur critique sauvegarde: {e2}")

def _find_username_key(users: dict, username: str) -> str:
    """Recherche flexible et insensible à la casse du nom d'utilisateur."""
    if not username:
        return None
    username_clean = username.strip()
    if username_clean in users:
        return username_clean
    username_lower = username_clean.lower()
    for key in users.keys():
        if key.lower() == username_lower:
            return key
    return None

def get_user_data(username: str):
    """Récupère les données d'un utilisateur de manière insensible à la casse."""
    users = load_users()
    key = _find_username_key(users, username)
    return users.get(key) if key else None

def create_user(username: str, password: str) -> bool:
    """Crée un utilisateur avec validation et protection contre les doublons insensibles à la casse."""
    if not username or not password:
        return False
    username_clean = username.strip()
    with _users_lock:
        users = load_users()
        if _find_username_key(users, username_clean) is not None:
            return False
        if len(username_clean) < 3 or len(username_clean) > 64 or len(password) < 8:
            return False
        users[username_clean] = {
            "password": bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('ascii'),
            "sessions": [],
            "files": [],
            "history": [],
            "tasks": [],
            "notifications": [],
            "preferences": {
                "theme": "dark",
                "language": "fr",
                "voice_enabled": True,
                "notifications_enabled": True
            },
            "clipboard": "",
            "devices": []
        }
        save_users(users)
        return True

def authenticate_user(username: str, password: str) -> bool:
    """Authentifie avec bcrypt et migre un ancien SHA-256 après succès."""
    if not username or not password:
        return False
    user = get_user_data(username)
    if not user:
        return False
    stored = user.get("password", "")
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(password.encode('utf-8'), stored.encode('ascii'))
        except (ValueError, TypeError):
            return False
    if len(stored) == 64:
        valid = secrets.compare_digest(stored, hashlib.sha256(password.encode('utf-8')).hexdigest())
        if valid:
            users = load_users()
            key = _find_username_key(users, username)
            if key:
                users[key]["password"] = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('ascii')
                save_users(users)
        return valid
    return False

def create_session(username: str) -> str:
    """Génère un identifiant de session unique et nettoie les sessions expirées (> 30)."""
    if not username:
        return ""
    with _users_lock:
        users = load_users()
        actual_user = _find_username_key(users, username) or username.strip()
        if actual_user not in users:
            return ""
        session_id = secrets.token_urlsafe(32)
        if "sessions" not in users[actual_user]:
            users[actual_user]["sessions"] = []
        # Limiter à 30 sessions actives max par utilisateur
        users[actual_user]["sessions"].append({"id": session_id, "created_at": time.time()})
        if len(users[actual_user]["sessions"]) > 30:
            users[actual_user]["sessions"] = users[actual_user]["sessions"][-30:]
        save_users(users)
        return session_id

ANONYMOUS_USERNAME = "Utilisateur"

def validate_session(session_id: str):
    """Valide strictement un jeton de session non expiré."""
    if not session_id or len(session_id) < 20:
        return None
    now = time.time()
    users = load_users()
    for username, user in users.items():
        valid = []
        found = False
        for item in user.get("sessions", []):
            item = item if isinstance(item, dict) else {"id": item, "created_at": now}
            if now - float(item.get("created_at", 0)) <= 86400:
                valid.append(item)
                found = found or item.get("id") == session_id
        if len(valid) != len(user.get("sessions", [])):
            user["sessions"] = valid
            save_users(users)
        if found:
            return username
    return None

def require_session(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not validate_session(request.headers.get("X-Session-ID")):
            return jsonify({"error": "Authentification requise"}), 401
        return view(*args, **kwargs)
    return wrapped

@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    logger.exception("Unhandled request error")
    return jsonify({"error": "Erreur interne du serveur"}), 500

def get_user_storage(username: str):
    """Alias sécurisé pour récupérer l'espace de stockage utilisateur."""
    return get_user_data(username)

# ============================================================
# 5. HISTORIQUE (THREAD-SAFE & ROBUSTE)
# ============================================================
HISTORY_DIR = os.path.join(BASE_DIR, "history")
os.makedirs(HISTORY_DIR, exist_ok=True)

def get_history_file(username: str):
    username_safe = "".join(c for c in username if c.isalnum() or c in ('_', '-')).strip() or "default"
    return os.path.join(HISTORY_DIR, f"{username_safe}.json")

def load_history(username: str) -> list:
    filepath = get_history_file(username)
    with _history_lock:
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("conversations", [])
            except Exception as e:
                print(f"[History] Erreur lecture historique ({e})")
                return []
        return []

def save_history(username: str, conversations: list):
    filepath = get_history_file(username)
    with _history_lock:
        try:
            temp_file = filepath + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({"conversations": conversations}, f, ensure_ascii=False, indent=2)
            if os.path.exists(filepath):
                os.replace(temp_file, filepath)
            else:
                os.rename(temp_file, filepath)
        except Exception as e:
            print(f"[History] Erreur sauvegarde historique: {e}")

def create_conversation_id() -> str:
    return f"conv_{int(time.time()*1000)}"

def get_current_conversation(username: str, conv_id: str):
    conversations = load_history(username)
    for conv in conversations:
        if conv.get("id") == conv_id:
            return conv
    return None

def update_conversation(username: str, conv_id: str, messages: list, title: str = None):
    with _history_lock:
        conversations = load_history(username)
        found = False
        for conv in conversations:
            if conv.get("id") == conv_id:
                conv["messages"] = messages
                conv["updated_at"] = datetime.now().isoformat()
                if title:
                    conv["title"] = title
                found = True
                break
        if not found:
            new_conv = {
                "id": conv_id,
                "title": title or "Nouvelle conversation",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "messages": messages
            }
            conversations.append(new_conv)
        save_history(username, conversations)

def delete_conversation(username: str, conv_id: str):
    with _history_lock:
        conversations = load_history(username)
        conversations = [c for c in conversations if c.get("id") != conv_id]
        save_history(username, conversations)

# ============================================================
# 6. FONCTIONS LLM
# ============================================================
def call_lm_studio(model, messages, temperature=0.2, max_tokens=2048, timeout=LLM_TIMEOUT_LONG):
    try:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        start = time.time()
        resp = http_session.post(LM_STUDIO_URL, json=payload, timeout=timeout)
        elapsed = time.time() - start
        print(f"[{model}] Réponse reçue en {elapsed:.1f}s")
        if resp.status_code == 200:
            return str(resp.json()["choices"][0]["message"]["content"])[:MAX_RESPONSE_LENGTH]
        else:
            print(f"[ERROR] {model} status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[ERROR] {model}: {e}")
    return None

def call_ministral(user_content, system_prompt, timeout=LLM_TIMEOUT_SHORT):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    return call_lm_studio(ORCHESTRATOR_BRAIN, messages, temperature=0.1, max_tokens=256, timeout=timeout)

def call_mistral_fast(user_content, timeout=LLM_TIMEOUT_MEDIUM):
    messages = [{"role": "user", "content": f"Tu es Onyx, francophone, réponds en français, concis.\n\n{user_content}"}]
    future = executor.submit(call_lm_studio, SUB_BRAIN, messages, 0.1, 256, timeout)
    try:
        return future.result(timeout=timeout+5)
    except TimeoutError:
        print(f"[TIMEOUT] Mistral > {timeout}s")
        return None
    except Exception as e:
        print(f"[ERROR] Mistral: {e}")
        return None

def call_qwen_deep(user_content, system_prompt, temperature=0.2, max_tokens=2048, timeout=LLM_TIMEOUT_LONG, model=None):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    return call_lm_studio(model or MAIN_BRAIN, messages, temperature, max_tokens, timeout)

# ============================================================
# 7. NEXUS-Ω (connecté au noyau unifié brain.nexus)
# ============================================================
class NexusOmega:
    @staticmethod
    def compress_prompt(text: str) -> str:
        if brain_nexus:
            return brain_nexus.compress(text)
        return text.strip()

    @staticmethod
    def is_simple_query(text: str) -> tuple:
        if brain_nexus:
            fast_res = brain_nexus.check_fast_path(text)
            if fast_res:
                return True, fast_res.get("content", "")
        text_lower = text.lower().strip()
        if text_lower in ["salut", "bonjour", "hello", "hi", "ping"]:
            return True, "Bonjour ! Comment puis-je vous aider aujourd'hui ?"
        return False, None

    @staticmethod
    def detect_tool_intent(user_input: str, username: str) -> tuple:
        """
        Détecte les intentions d'outils (système, fichiers, météo, news, tâches).
        Retourne ("tool", réponse) ou (None, None).
        """
        text_lower = user_input.lower()

        # Outils connectés via brain_nexus
        if brain_nexus:
            tools_bridge = {
                "get_weather": get_weather if 'get_weather' in globals() else None,
                "get_news": get_news if 'get_news' in globals() else None,
                "read_emails": read_emails if 'read_emails' in globals() else None,
            }
            ttype, tresp = brain_nexus.detect_tool_intent(user_input, username=username, tools_bridge=tools_bridge)
            if ttype == "tool":
                return ttype, tresp

        # Commandes système (fichiers, dossiers, etc.)
        sys_keywords = ['crée', 'créer', 'supprime', 'efface', 'copie', 'déplace', 'renomme', 'affiche le contenu',
                        'va dans le dossier', 'liste les fichiers', 'recherche', 'commande système', 'cmd', 'powershell',
                        'dossier', 'fichier', 'répertoire']
        if any(kw in text_lower for kw in sys_keywords):
            command = generate_command_from_intent(user_input)
            if command and command != "COMMANDE_NON_AUTORISEE":
                result = execute_system_command(command)
                if result.get("success"):
                    msg = f"Succès : commande exécutée : `{command}`\n\n"
                    if result.get("stdout"):
                        msg += f"**Sortie :**\n```\n{result['stdout']}\n```"
                    else:
                        msg += "*(Commande exécutée sans sortie)*"
                    return "tool", msg
                else:
                    msg = f"Erreur : échec lors de l'exécution de `{command}`\n\n```\n{result.get('stderr', '')}\n```"
                    return "tool", msg
            else:
                fallback = call_mistral_fast(f"Donne des instructions pour : {user_input}")
                return "tool", f"Attention : je n'ai pas pu exécuter la commande automatiquement. Voici des instructions :\n\n{fallback}"

        # Tâches (To-Do)
        if any(kw in text_lower for kw in ['ajoute la tâche', 'crée une tâche', 'nouvelle tâche', 'todo']):
            match = re.search(r'(?:tâche|todo)\s*(?::)?\s*(.+?)(?:\.|$)', text_lower)
            if match:
                title = match.group(1).strip()
                due_date = None
                date_match = re.search(r'(?:pour|avant|le)\s*(\d{1,2}/\d{1,2}/\d{4})', text_lower)
                if date_match:
                    try:
                        due_date = datetime.strptime(date_match.group(1), "%d/%m/%Y")
                    except Exception:
                        pass
                if username:
                    result = add_task(username, title, due_date)
                    if result.get("success"):
                        return "tool", f"Succès : tâche ajoutée : {title}" + (f" (échéance : {due_date.strftime('%d/%m/%Y')})" if due_date else "")
                    else:
                        return "tool", f"Erreur : {result.get('error')}"
        return None, None


# ============================================================
# 8. SYNAPSE-X (connecté au noyau unifié brain.synapse)
# ============================================================
class SynapseX:
    @classmethod
    def get_cached_response(cls, key: str) -> Optional[str]:
        if brain_synapse:
            return brain_synapse.get_cached_response(key)
        return None

    @classmethod
    def set_cached_response(cls, key: str, value: str):
        if brain_synapse:
            brain_synapse.set_cached_response(key, value)

    @classmethod
    def adjust_temperature(cls, base_temp: float = 0.7, repetition_detected: bool = False) -> float:
        if brain_synapse:
            return brain_synapse.adjust_temperature(base_temp=base_temp, repetition_detected=repetition_detected)
        return base_temp + (0.3 if repetition_detected else 0.0)

    @staticmethod
    def search_ltm(username: str, query: str, limit: int = 5) -> list:
        if brain_synapse:
            return brain_synapse.search_ltm(username=username, query=query, limit=limit)
        return []


# ============================================================
# 9. KAIROS (connecté au noyau unifié brain.kairos)
# ============================================================
class Kairos:
    @staticmethod
    def extract_consensus(thesis: str, antithesis: str) -> str:
        if brain_kairos:
            return brain_kairos.extract_consensus(thesis, antithesis)
        return "Consensus extrait."

    @classmethod
    def run_debate(cls, user_prompt: str) -> str:
        print(f"[KAIROS] Débat dialectique pour : {user_prompt[:60]}...")
        if brain_kairos:
            debate_res = brain_kairos.run_debate(
                user_prompt,
                call_qwen_fn=lambda p, s: call_qwen_deep(p, s, temperature=0.3, max_tokens=150, timeout=LLM_TIMEOUT_SHORT),
                call_mistral_fn=lambda p: call_mistral_fast(p, timeout=LLM_TIMEOUT_SHORT)
            )
            return debate_res.get("consensus", "Synthèse générale établie.")
        return "Aucun consensus disponible."

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

# ============================================================
# 11. ORCHESTRATEUR (Ministral) + Router
# ============================================================
class MultiAgentOrchestrator:
    def __init__(self):
        self.agents = {
            "code": CodeAgent(),
            "web": WebAgent(),
            "mail": MailAgent(),
            "system": SystemAgent(),
            "data": DataAgent(),
            "planner": PlannerAgent()
        }
        self.fallback_agent = "qwen"

    def route_task(self, user_input, context):
        system_prompt = """Tu es un routeur d'intentions. Analyse la requête utilisateur et retourne UNIQUEMENT le nom de l'agent à utiliser parmi : code, web, mail, system, data, planner, qwen.
Règles :
- Code, programmation, script, exécution → code
- Recherche web, actualités, information → web
- Email, mail, courrier → mail
- Contrôle système (volume, veille, redémarrage, statut) → system
- Analyse de données, NLP, statistiques, sentiment → data
- Planification, plan d'action, sous-tâches, objectif complexe → planner
- Sinon → qwen
Ne retourne que le nom de l'agent, rien d'autre."""
        response = call_ministral(user_input, system_prompt, timeout=LLM_TIMEOUT_SHORT)
        agent_name = response.strip().lower() if response else "qwen"
        if agent_name in self.agents:
            return agent_name
        else:
            return "qwen"

    def execute_task(self, user_input, context):
        agent_name = self.route_task(user_input, context)
        if agent_name == "qwen":
            return None
        else:
            agent = self.agents[agent_name]
            return agent.execute(user_input, context)

orchestrator = MultiAgentOrchestrator()

# ============================================================
# 11.B PIPELINE CERVEAU VOCAL & INTÉGRATION ONYX
# ============================================================
def process_voice_prompt(user_input: str) -> str:
    """
    Traite la transcription vocale via le cerveau Onyx V2 :
    - Routeur d'intention & Agents spécialisés
    - Nexus-Omega (requêtes directes & outils)
    - LLM Local (Qwen / Mistral)
    - Sauvegarde automatique dans l'historique et la mémoire LTM
    """
    try:
        user_input_clean = user_input.strip()
        if not user_input_clean:
            return ""

        print(f"[OnyxVoice -> Cerveau] Requête vocale reçue : {user_input_clean}")

        users = load_users()
        username = next(iter(users.keys())) if users else "Admin"
        user_data = get_user_storage(username) or {}

        # 1. Vérification par l'orchestrateur multi-agents (Code, Web, Mail, System)
        agent_result = orchestrator.execute_task(user_input_clean, {})
        if agent_result is not None and agent_result.get("success"):
            resp = agent_result.get("output", "")
            _save_voice_interaction(username, user_input_clean, resp)
            return resp

        # 2. Requêtes simples / Nexus-Omega
        is_simple, simple_resp = NexusOmega.is_simple_query(user_input_clean)
        if is_simple:
            _save_voice_interaction(username, user_input_clean, simple_resp)
            return simple_resp

        # 3. Intentions d'outils (Météo, News, Tâches, etc.)
        tool_type, tool_resp = NexusOmega.detect_tool_intent(user_input_clean, username)
        if tool_type == "tool":
            _save_voice_interaction(username, user_input_clean, tool_resp)
            return tool_resp

        # 4. LLM Principal Qwen / Mistral (optimisé pour la synthèse vocale)
        # Charger la personnalite complete d'Onyx (mode vocal)
        try:
            from brain.identity import ONYX_PERSONALITY as _OP_V
        except ImportError:
            try:
                from identity import ONYX_PERSONALITY as _OP_V
            except ImportError:
                _OP_V = "Tu es Onyx, un assistant IA vocal autonome."

        system_prompt = (
            f"{_OP_V.strip()}\n\n"
            "Pour les réponses vocales : sois concis (1 à 3 phrases max), "
            "sans markdown, en français naturel et fluide."
        )
        resp = call_qwen_deep(user_input_clean, system_prompt, temperature=0.3, max_tokens=250, timeout=LLM_TIMEOUT_SHORT)
        if not resp:
            resp = call_mistral_fast(user_input_clean, timeout=LLM_TIMEOUT_SHORT)
        if not resp:
            resp = "J'ai bien entendu votre demande, mais je n'ai pas pu obtenir de réponse pour le moment."

        _save_voice_interaction(username, user_input_clean, resp)
        return resp
    except Exception as e:
        print(f"[OnyxVoice -> Cerveau] Erreur de traitement : {e}")
        return "Désolé, une erreur est survenue lors du traitement vocal."

def _save_voice_interaction(username: str, user_msg: str, bot_msg: str):
    try:
        conversations = load_history(username)
        if conversations:
            conv = sorted(conversations, key=lambda x: x.get("updated_at", ""), reverse=True)[0]
            conv_id = conv["id"]
        else:
            conv_id = create_conversation_id()
        user_data = get_user_storage(username) or {}
        _save_chat_turn(username, user_data, conv_id, user_msg, bot_msg, "fr")
    except Exception as e:
        print(f"[OnyxVoice] Erreur sauvegarde interaction : {e}")

# Initialisation de l'assistant vocal 100% local (openwakeword, sounddevice, faster-whisper, pyttsx3, scipy)
voice_assistant = VoiceAssistant(
    socketio=socketio,
    brain_callback=process_voice_prompt,
    wakeword="hey_jarvis",
    whisper_model="base",
    tts_rate=175,
    tts_volume=1.0,
    sensitivity=0.5
)

# ============================================================
# 12. COMMANDES SYSTÈME (GÉNÉRATION ET EXÉCUTION)
# ============================================================
ALLOWED_COMMANDS_WINDOWS = {
    "cd", "dir", "mkdir", "rmdir", "copy", "xcopy", "move", "ren", "del", "erase",
    "type", "echo", "find", "where", "tree", "cls", "chdir", "pushd", "popd",
    "attrib", "assoc", "fc", "findstr", "for", "if", "pause", "ping",
    "start", "tasklist", "taskkill", "shutdown", "systeminfo", "ipconfig",
    "netstat", "nslookup", "tracert", "path", "set", "whoami", "hostname"
}
ALLOWED_COMMANDS_LINUX = {
    "cd", "pwd", "ls", "mkdir", "rmdir", "rm", "cp", "mv", "touch", "cat",
    "less", "head", "tail", "grep", "find", "which", "chmod", "chown",
    "echo", "clear", "pwd", "date", "whoami", "hostname", "ping",
    "ifconfig", "netstat", "ss", "ps", "kill", "df", "du", "free",
    "top", "htop", "nano", "vim", "vi", "history"
}
IS_WINDOWS = os.name == 'nt'
ALLOWED_COMMANDS = ALLOWED_COMMANDS_WINDOWS if IS_WINDOWS else ALLOWED_COMMANDS_LINUX
SENSITIVE_COMMANDS = {
    "rmdir", "rd", "del", "erase", "rm", "rm -r", "rm -rf", "del /s", "erase /s",
    "Remove-Item", "rm -rf", "rm -r", "rmdir /s", "rmdir /s /q",
    "del /f", "erase /f", "rm -f", "rm -rf /", "rm -r /", "del /q", "erase /q"
}

def detect_shell():
    if IS_WINDOWS:
        try:
            subprocess.run(["powershell", "-Command", "exit"], capture_output=True, timeout=1)
            return "powershell"
        except:
            return "cmd"
    else:
        return "bash"

def execute_system_command(command: str, timeout: int = 60) -> dict:
    command = command.strip()
    cmd_base = command.split()[0].lower() if command else ""
    if cmd_base not in ALLOWED_COMMANDS:
        return {"success": False, "stderr": f"Commande non autorisée : {cmd_base}"}
    shell = detect_shell()
    if IS_WINDOWS:
        if shell == "powershell":
            full_command = ["powershell", "-NoProfile", "-Command", command]
        else:
            full_command = ["cmd", "/c", command]
    else:
        full_command = ["bash", "-c", command]
    try:
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace'
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip() if result.stdout else "",
            "stderr": result.stderr.strip() if result.stderr else ""
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stderr": f"Commande timeout après {timeout}s"}
    except Exception as e:
        return {"success": False, "stderr": str(e)}

def generate_command_from_intent(user_input: str) -> str:
    """
    Utilise Qwen pour générer une commande système à partir d'une requête naturelle.
    """
    # Détection du système d'exploitation
    os_name = "Windows" if IS_WINDOWS else "Linux"
    system_prompt = f"""Tu es un assistant spécialisé dans la conversion de demandes en commandes système.
Le système d'exploitation est {os_name}.
Voici les commandes autorisées : {', '.join(sorted(ALLOWED_COMMANDS))}.
Tu dois retourner UNIQUEMENT la commande, sans explication ni formatage.
Pour créer un dossier sur le bureau (Windows), utilise la commande : mkdir "C:\\Users\\%USERNAME%\\Desktop\\nom_du_dossier"
Remplace %USERNAME% par le nom d'utilisateur réel ou utilise $env:USERNAME en PowerShell.
Si la demande ne correspond à aucune commande autorisée, retourne "COMMANDE_NON_AUTORISEE".
"""
    user_prompt = f"Demande de l'utilisateur : {user_input}\nGénère la commande système correspondante :"
    try:
        response = call_qwen_deep(
            user_content=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=150,
            timeout=LLM_TIMEOUT_SHORT
        )
        command = response.strip()
        if command.startswith("```"):
            command = re.sub(r'```[a-zA-Z]*\n?', '', command)
            command = re.sub(r'\n```', '', command)
        command = command.strip()
        if command and command.split()[0].lower() in ALLOWED_COMMANDS:
            return command
        else:
            return "COMMANDE_NON_AUTORISEE"
    except Exception as e:
        print(f"[Command Gen] Erreur: {e}")
        return ""

# ============================================================
# 13. TÂCHES ET NOTIFICATIONS
# ============================================================
def add_task(username, title, due_date=None, description=None):
    user_data = get_user_storage(username)
    if not user_data:
        return {"success": False, "error": "Utilisateur non trouvé"}
    task_id = str(int(time.time() * 1000))
    task = {
        "id": task_id,
        "title": title,
        "description": description or "",
        "due_date": due_date.isoformat() if due_date else None,
        "done": False,
        "created_at": datetime.now().isoformat()
    }
    user_data["tasks"].append(task)
    save_users(load_users())
    return {"success": True, "task": task}

def get_tasks(username, filter_done=False):
    user_data = get_user_storage(username)
    if not user_data:
        return []
    tasks = user_data.get("tasks", [])
    if filter_done is not None:
        tasks = [t for t in tasks if t.get("done", False) == filter_done]
    tasks.sort(key=lambda x: x.get("due_date") or "9999-12-31T23:59:59")
    return tasks

def toggle_task(username, task_id):
    user_data = get_user_storage(username)
    if not user_data:
        return {"success": False, "error": "Utilisateur non trouvé"}
    for t in user_data["tasks"]:
        if t["id"] == task_id:
            t["done"] = not t.get("done", False)
            save_users(load_users())
            return {"success": True, "task": t}
    return {"success": False, "error": "Tâche non trouvée"}

def delete_task(username, task_id):
    user_data = get_user_storage(username)
    if not user_data:
        return {"success": False, "error": "Utilisateur non trouvé"}
    user_data["tasks"] = [t for t in user_data["tasks"] if t["id"] != task_id]
    save_users(load_users())
    return {"success": True}

def add_notification(username, title, message, level="info"):
    user_data = get_user_storage(username)
    if not user_data:
        return
    notif = {
        "id": str(int(time.time() * 1000)),
        "title": title,
        "message": message,
        "level": level,
        "timestamp": datetime.now().isoformat(),
        "read": False
    }
    if "notifications" not in user_data:
        user_data["notifications"] = []
    user_data["notifications"].append(notif)
    save_users(load_users())
    send_notification(title, message)

# ============================================================
# 14. MODE VEILLE
# ============================================================
monitors = {}
pending_suggestions = {}

def on_file_change(session_id, filepath, new_content):
    error_keywords = ['error', 'exception', 'fail', 'critique', 'fatal']
    found_errors = [kw for kw in error_keywords if kw in new_content.lower()]
    if found_errors:
        title = f"Erreur détectée dans {os.path.basename(filepath)}"
        message = f"Nouvelle entrée contenant : {', '.join(found_errors)}\nExtrait : {new_content[:200]}..."
        username = validate_session(session_id)
        if username:
            add_notification(username, title, message, level="error")
        if session_id not in pending_suggestions:
            pending_suggestions[session_id] = []
        pending_suggestions[session_id].append({
            "timestamp": time.time(),
            "file": filepath,
            "content": new_content,
            "suggestion": f"J'ai détecté des erreurs dans {os.path.basename(filepath)}. Voulez-vous que j'analyse le fichier ?"
        })

# ============================================================
# 15. FONCTIONS LTM (THREAD-SAFE & ROBUSTE)
# ============================================================
LTM_FILE = os.path.join(BASE_DIR, "ltm.json")

def load_ltm() -> dict:
    with _ltm_lock:
        if os.path.exists(LTM_FILE):
            try:
                with open(LTM_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "conversations" in data:
                        return data
            except Exception as e:
                print(f"[LTM] Erreur lecture: {e}")
        return {"conversations": []}

def save_ltm(data: dict):
    with _ltm_lock:
        try:
            temp_file = LTM_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if os.path.exists(LTM_FILE):
                os.replace(temp_file, LTM_FILE)
            else:
                os.rename(temp_file, LTM_FILE)
        except Exception as e:
            print(f"[LTM] Erreur sauvegarde: {e}")

def add_to_ltm(username: str, user_msg: str, ai_response: str, language: str = "fr"):
    """Enregistre un échange dans ltm.json (format legacy) et déclenche la consolidation STM->LTM."""
    with _ltm_lock:
        data = load_ltm()
        data["conversations"].append({
            "username": username,
            "timestamp": datetime.now().isoformat(),
            "user": user_msg,
            "assistant": ai_response,
            "language": language
        })
        if len(data["conversations"]) > 1000:
            data["conversations"] = data["conversations"][-1000:]
        save_ltm(data)

    # Consolidation intelligente vers le nouveau système de mémoire (brain/memory.py)
    if memory_manager:
        try:
            memory_manager.consolidate_to_ltm(
                username=username,
                conv_id="",
                conversation_messages=[
                    {"role": "user", "content": user_msg, "timestamp": datetime.now().isoformat()},
                    {"role": "assistant", "content": ai_response, "timestamp": datetime.now().isoformat()}
                ],
                importance_threshold=0.25
            )
        except Exception as e:
            print(f"[LTM] Erreur consolidation : {e}")

def search_ltm_simple(username: str, query: str, limit: int = 5) -> list:
    """Délégue vers la recherche intelligente du brain memory manager si disponible."""
    if memory_manager:
        try:
            results = memory_manager.search_ltm_smart(username, query, limit=limit)
            if results:
                return results
        except Exception as e:
            print(f"[MemoryManager] Erreur recherche LTM : {e}")

    # Fallback : recherche simple legacy sur ltm.json
    data = load_ltm()
    query_words = set(query.lower().split())
    results = []
    now_ts = time.time()
    for conv in data.get("conversations", []):
        if conv.get("username") != username:
            continue
        combined = (conv.get("user", "") + " " + conv.get("assistant", "")).lower()
        score = sum(1 for w in query_words if w in combined)
        # Bonus de récence
        item_date_str = conv.get("timestamp", "")
        if item_date_str:
            try:
                item_ts = datetime.fromisoformat(str(item_date_str)[:19]).timestamp()
                days_old = max(0, (now_ts - item_ts) / 86400.0)
                recency_bonus = max(0.5, 1.0 - (math.log(1 + days_old) * 0.05))
                score *= recency_bonus
            except Exception:
                pass
        if score > 0:
            results.append((score, conv))
    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:limit]]

# ============================================================
# 16. INTERFACE HTML (inchangée)
# ============================================================
ONYX_UI_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>Onyx — Assistant Intelligent</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,500;14..32,600;14..32,700&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #000000;
            color: #f5f5f7;
            height: 100vh;
            overflow: hidden;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }
        /* --- Styles du Système Vocal Local --- */
        .voice-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--glass);
            border: 1px solid var(--glass-border);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
        }
        .voice-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #30d158;
            box-shadow: 0 0 8px rgba(48, 209, 88, 0.6);
        }
        .voice-pill.listening .voice-dot { background: #30d158; animation: pulseGreen 2s infinite; }
        .voice-pill.wake_detected .voice-dot { background: #ff9500; animation: pulseFast 0.4s infinite; }
        .voice-pill.recording .voice-dot { background: #ff3b30; animation: pulseRed 1s infinite; }
        .voice-pill.transcribing .voice-dot { background: #ffd60a; animation: pulseYellow 1s infinite; }
        .voice-pill.thinking .voice-dot { background: #007aff; animation: pulseBlue 1.2s infinite; }
        .voice-pill.speaking .voice-dot { background: #bf5af2; animation: pulsePurple 1s infinite; }
        .voice-pill.paused .voice-dot, .voice-pill.idle .voice-dot { background: #8e8e93; animation: none; }

        @keyframes pulseGreen { 0% { transform: scale(0.9); opacity: 0.7; } 50% { transform: scale(1.25); opacity: 1; box-shadow: 0 0 10px #30d158; } 100% { transform: scale(0.9); opacity: 0.7; } }
        @keyframes pulseRed { 0% { transform: scale(0.9); opacity: 0.8; } 50% { transform: scale(1.35); opacity: 1; box-shadow: 0 0 12px #ff3b30; } 100% { transform: scale(0.9); opacity: 0.8; } }
        @keyframes pulseYellow { 0% { transform: scale(0.9); } 50% { transform: scale(1.2); box-shadow: 0 0 10px #ffd60a; } 100% { transform: scale(0.9); } }
        @keyframes pulseBlue { 0% { transform: scale(0.9); opacity: 0.8; } 50% { transform: scale(1.25); opacity: 1; box-shadow: 0 0 10px #007aff; } 100% { transform: scale(0.9); opacity: 0.8; } }
        @keyframes pulsePurple { 0% { transform: scale(0.9); opacity: 0.8; } 50% { transform: scale(1.3); opacity: 1; box-shadow: 0 0 12px #bf5af2; } 100% { transform: scale(0.9); opacity: 0.8; } }
        @keyframes pulseFast { 0% { transform: scale(0.8); } 50% { transform: scale(1.4); box-shadow: 0 0 12px #ff9500; } 100% { transform: scale(0.8); } }

        .voice-icon-btn {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2px;
            border-radius: 4px;
            transition: 0.2s;
        }
        .voice-icon-btn:hover { color: var(--text-primary); }

        /* --- Linear / Vercel Design System --- */
        :root {
            --accent: #007aff;
            --accent-hover: #0055b3;
            --accent-subtle: rgba(0,122,255,0.12);
            --glass: rgba(255,255,255,0.06);
            --glass-hover: rgba(255,255,255,0.1);
            --glass-border: rgba(255,255,255,0.08);
            --glass-border-hover: rgba(255,255,255,0.15);
            --text-primary: #f5f5f7;
            --text-secondary: #86868b;
            --text-tertiary: #636366;
            --bg-primary: #000000;
            --bg-secondary: #0d0d0f;
            --bg-tertiary: #141416;
            --bg-chat: #08080a;
            --input-bg: rgba(255,255,255,0.05);
            --success: #30d158;
            --warning: #ff9f0a;
            --error: #ff3b30;
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-xl: 20px;
            --radius-full: 9999px;
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
            --shadow-lg: 0 12px 40px rgba(0,0,0,0.6);
            --transition-fast: 0.15s cubic-bezier(0.4, 0, 0.2, 1);
            --transition-medium: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            --transition-slow: 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .light-mode {
            --accent: #007aff;
            --accent-hover: #0055b3;
            --accent-subtle: rgba(0,122,255,0.08);
            --glass: rgba(0,0,0,0.03);
            --glass-hover: rgba(0,0,0,0.06);
            --glass-border: rgba(0,0,0,0.06);
            --glass-border-hover: rgba(0,0,0,0.12);
            --text-primary: #1c1c1e;
            --text-secondary: #6e6e73;
            --text-tertiary: #aeaeb2;
            --bg-primary: #f5f5f7;
            --bg-secondary: #ffffff;
            --bg-tertiary: #f2f2f7;
            --bg-chat: #ffffff;
            --input-bg: rgba(0,0,0,0.03);
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 12px 40px rgba(0,0,0,0.12);
        }
        #app { display: flex; height: 100vh; width: 100vw; background: var(--bg-primary); overflow: hidden; }
        #sidebar {
            position: fixed; top: 0; left: 0; width: 280px; height: 100%;
            background: var(--bg-secondary); border-right: 1px solid var(--glass-border);
            display: flex; flex-direction: column;
            padding: calc(20px + var(--safe-top)) 16px calc(20px + var(--safe-bottom)) 16px;
            overflow-y: auto; z-index: 100;
            transform: translateX(-100%); transition: transform 0.3s cubic-bezier(0.4,0,0.2,1);
            box-shadow: 2px 0 20px rgba(0,0,0,0.3);
        }
        #sidebar.open { transform: translateX(0); }
        #sidebar-backdrop {
            position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 99;
            opacity: 0; pointer-events: none; transition: opacity 0.3s;
        }
        #sidebar-backdrop.show { opacity: 1; pointer-events: auto; }
        #sidebar-search:focus { border-color: var(--accent); background: var(--bg-tertiary); }
        #sidebar-search::placeholder { color: var(--text-tertiary); }
        .system-context-card {
            margin: 4px 0 14px; padding: 12px 13px; border-radius: var(--radius-lg);
            background: linear-gradient(145deg, var(--accent-subtle), var(--glass));
            border: 1px solid rgba(0,122,255,0.18); box-shadow: var(--shadow-sm);
        }
        .system-context-card .context-title { display:flex; align-items:center; gap:7px; color:var(--text-primary); font-size:12px; font-weight:600; margin-bottom:8px; }
        .context-pulse { width:7px; height:7px; border-radius:50%; background:var(--success); box-shadow:0 0 0 4px rgba(48,209,88,.12); }
        .context-copy { color:var(--text-secondary); font-size:11px; line-height:1.45; }
        .context-tags { display:flex; gap:5px; flex-wrap:wrap; margin-top:9px; }
        .context-tag { padding:3px 7px; border-radius:var(--radius-full); background:var(--glass); color:var(--text-secondary); font-size:10px; border:1px solid var(--glass-border); }
        #sentiment-pill { display:inline-flex; align-items:center; gap:5px; padding:4px 8px; border-radius:var(--radius-full); background:var(--glass); border:1px solid var(--glass-border); color:var(--text-secondary); font-size:10px; white-space:nowrap; transition:all var(--transition-fast); }
        #sentiment-pill.active { color:var(--text-primary); border-color:rgba(0,122,255,.28); background:var(--accent-subtle); }
        #sidebar-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
        #sidebar-header h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; background: linear-gradient(135deg, #007aff, #5ac8fa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        #new-chat-btn { background: var(--accent); border: none; border-radius: 50%; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; color: #fff; cursor: pointer; transition: all var(--transition-fast); }
        #new-chat-btn:hover { background: var(--accent-hover); transform: scale(1.05); }
        .sidebar-section { margin-bottom: 20px; }
        .sidebar-section-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-tertiary); padding: 0 14px 8px; }
        #new-chat-btn:hover { background: var(--accent-hover); transform: scale(1.05); }
        #conversation-list { flex: 1; overflow-y: auto; margin-top: 4px; }
        .conv-item { padding: 10px 12px; border-radius: var(--radius-md); cursor: pointer; transition: all var(--transition-fast); margin-bottom: 2px; display: flex; align-items: center; gap: 10px; border: 1px solid transparent; }
        .conv-item:hover { background: var(--glass); border-color: var(--glass-border); }
        .conv-item.active { background: var(--accent-subtle); border-color: rgba(0,122,255,0.2); }
        .conv-item .title { flex: 1; font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .conv-item .date { font-size: 10px; color: var(--text-tertiary); white-space: nowrap; }
        .conv-item .delete-btn { color: var(--text-tertiary); cursor: pointer; opacity: 0; transition: all var(--transition-fast); padding: 2px; border-radius: 4px; }
        .conv-item:hover .delete-btn { opacity: 0.7; }
        .conv-item .delete-btn:hover { opacity: 1; color: var(--error); background: rgba(255,59,48,0.1); }
        #user-info { display: flex; align-items: center; gap: 10px; padding: 12px 0; border-top: 1px solid var(--glass-border); margin-top: 12px; }
        #user-avatar { width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), #5ac8fa); display: flex; align-items: center; justify-content: center; font-weight: 600; color: #fff; font-size: 13px; flex-shrink: 0; }
        #user-name { font-size: 13px; font-weight: 500; flex: 1; }
        #logout-btn { margin-left: auto; background: none; border: none; color: var(--text-tertiary); cursor: pointer; font-size: 16px; padding: 4px; border-radius: 6px; transition: all var(--transition-fast); }
        #logout-btn:hover { color: var(--error); background: rgba(255,59,48,0.1); }
        #main { flex: 1; display: flex; flex-direction: column; background: var(--bg-chat); position: relative; width: 100%; max-width: 100vw; }
        #chat-header { padding: 12px 16px; padding-top: calc(12px + var(--safe-top)); border-bottom: 1px solid var(--glass-border); display: flex; align-items: center; gap: 10px; backdrop-filter: blur(12px); background: rgba(0,0,0,0.6); flex-shrink: 0; z-index: 10; }
        #menu-toggle { background: none; border: none; color: var(--text-secondary); font-size: 20px; cursor: pointer; padding: 4px; display: flex; align-items: center; border-radius: 6px; transition: all var(--transition-fast); }
        #menu-toggle:hover { background: var(--glass); color: var(--text-primary); }
        #chat-header-title { font-size: 15px; font-weight: 600; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        #chat-header { box-shadow: 0 1px 0 rgba(255,255,255,.02), 0 8px 24px rgba(0,0,0,.12); }
        .header-action-btn { background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 6px; border-radius: 8px; transition: all var(--transition-fast); font-size: 18px; }
        .header-action-btn:hover { background: var(--glass); color: var(--text-primary); }
        #messages { flex: 1; padding: 16px; padding-bottom: 8px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; -webkit-overflow-scrolling: touch; position: relative; }
        .empty-state { display: none; flex-direction: column; align-items: center; justify-content: center; height: 100%; text-align: center; padding: 40px; color: var(--text-secondary); }
        .empty-state.visible { display: flex; }
        .empty-state-icon { width: 64px; height: 64px; background: var(--glass); border-radius: var(--radius-xl); display: flex; align-items: center; justify-content: center; margin-bottom: 20px; border: 1px solid var(--glass-border); box-shadow: 0 0 0 8px rgba(0,122,255,.04), 0 14px 35px rgba(0,0,0,.24); }
        .empty-state h3 { font-size: 18px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
        .empty-state p { font-size: 14px; max-width: 320px; line-height: 1.5; margin-bottom: 24px; }
        .empty-state-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; }
        .empty-state-btn { padding: 8px 16px; background: var(--glass); border: 1px solid var(--glass-border); border-radius: var(--radius-full); color: var(--text-primary); font-size: 13px; font-weight: 500; cursor: pointer; transition: all var(--transition-fast); }
        .empty-state-btn:hover { background: var(--glass-hover); border-color: var(--glass-border-hover); transform: translateY(-1px); }
        .empty-state-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
        .empty-state-btn.primary:hover { background: var(--accent-hover); }
        .msg { max-width: 85%; padding: 10px 14px; border-radius: 18px; font-size: 15px; line-height: 1.5; word-wrap: break-word; animation: fadeIn 0.3s ease-out; }
        .msg.user { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
        .msg.onyx { align-self: flex-start; background: var(--glass); border: 1px solid var(--glass-border); border-bottom-left-radius: 4px; }
        .msg .time { font-size: 10px; opacity: 0.6; margin-top: 4px; display: block; }
        .msg pre { background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px; overflow-x: auto; margin-top: 8px; font-size: 13px; }
        @keyframes fadeIn { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:translateY(0); } }
        #input-area {
            padding: 14px 12px;
            padding-bottom: calc(14px + var(--safe-bottom));
            border-top: 1px solid var(--glass-border);
            display: flex; gap: 10px; align-items: center;
            background: rgba(0,0,0,0.6); backdrop-filter: blur(12px);
            flex-shrink: 0;
        }
        #input-area:focus-within { border-color: rgba(0,122,255,.42); box-shadow: 0 -8px 30px rgba(0,122,255,.06); }
        #cmd-input { flex:1; min-height:44px; max-height:160px; resize:none; background:var(--input-bg); border:1px solid var(--glass-border); border-radius:18px; padding:12px 15px; font:inherit; font-size:15px; line-height:1.4; color:var(--text-primary); outline:none; transition:border-color var(--transition-fast), background var(--transition-fast); }
        #cmd-input:focus { border-color:rgba(0,122,255,.55); background:var(--bg-tertiary); }
        #cmd-input::placeholder { color:var(--text-secondary); }
        #input-area input {
            flex: 1;
            background: var(--input-bg);
            border: 1px solid var(--glass-border);
            border-radius: 24px;
            padding: 10px 16px;
            font-size: 15px;
            color: var(--text-primary);
            outline: none;
            transition: 0.2s;
            min-height: 44px;
        }
        #input-area input:focus { border-color: var(--accent); }
        #input-area input::placeholder { color: var(--text-secondary); }
        #input-area button {
            background: var(--accent);
            border: none;
            border-radius: 50%;
            width: 44px; height: 44px;
            display: flex; align-items: center; justify-content: center;
            color: #fff; cursor: pointer; transition: 0.2s;
            flex-shrink: 0;
        }
        #input-area button:hover { background: var(--accent-hover); transform: scale(1.04); }
        #input-area button:disabled { opacity: 0.4; pointer-events: none; }
        #file-upload-btn { background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 20px; padding: 6px; border-radius: 50%; transition: 0.2s; }
        #file-upload-btn:hover { background: var(--glass); color: var(--text-primary); }
        #login-screen { display: none !important; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--glass); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
        @media (min-width: 768px) {
            #sidebar { position: relative; transform: translateX(0) !important; width: 296px; box-shadow: 12px 0 40px rgba(0,0,0,.14); border-right: 1px solid var(--glass-border); padding: 22px 18px; }
            #sidebar-backdrop { display: none; }
            #menu-toggle { display: none; }
            #main { max-width: calc(100vw - 296px); }
            .msg { max-width: 75%; }
        }
        @media (max-width: 480px) {
            .msg { max-width: 90%; font-size: 14px; }
            #input-area { padding: 16px 12px; padding-bottom: calc(16px + var(--safe-bottom)); }
            #input-area input { padding: 12px 16px; min-height: 50px; font-size: 16px; }
            #input-area button { width: 50px; height: 50px; }
            #chat-header-title { font-size: 14px; }
            .login-card { padding: 24px 16px; }
        }

        /* --- Command Palette (Linear / Raycast) --- */
        #cmd-palette-overlay {
            position: fixed; inset: 0; background: rgba(0,0,0,0.65); backdrop-filter: blur(12px);
            z-index: 2000; display: none; align-items: flex-start; justify-content: center;
            padding-top: min(20vh, 160px); opacity: 0; transition: opacity var(--transition-medium);
        }
        #cmd-palette-overlay.open { display: flex; opacity: 1; }
        .cmd-palette {
            width: 92%; max-width: 560px; background: var(--bg-secondary);
            border: 1px solid var(--glass-border); border-radius: var(--radius-xl);
            box-shadow: var(--shadow-lg); overflow: hidden;
            transform: translateY(-12px) scale(0.98); transition: transform var(--transition-medium);
        }
        #cmd-palette-overlay.open .cmd-palette { transform: translateY(0) scale(1); }
        .cmd-palette-input {
            width: 100%; padding: 16px 20px; background: transparent; border: none;
            border-bottom: 1px solid var(--glass-border); color: var(--text-primary);
            font-size: 16px; font-family: inherit; outline: none;
        }
        .cmd-palette-input::placeholder { color: var(--text-tertiary); }
        .cmd-palette-list { max-height: 320px; overflow-y: auto; padding: 8px; }
        .cmd-palette-item {
            display: flex; align-items: center; gap: 12px; padding: 10px 14px;
            border-radius: var(--radius-md); cursor: pointer; transition: background var(--transition-fast);
            font-size: 14px; color: var(--text-primary);
        }
        .cmd-palette-item:hover, .cmd-palette-item.active { background: var(--glass-hover); }
        .cmd-palette-item .icon { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; background: var(--glass); border-radius: var(--radius-sm); color: var(--text-secondary); }
        .cmd-palette-item .shortcut { margin-left: auto; font-size: 11px; color: var(--text-tertiary); background: var(--glass); padding: 2px 8px; border-radius: var(--radius-full); }

        /* --- Toast Notifications (Vercel) --- */
        #toast-container { position: fixed; top: 16px; right: 16px; z-index: 3000; display: flex; flex-direction: column; gap: 8px; pointer-events: none; }
        .toast {
            pointer-events: auto; display: flex; align-items: center; gap: 10px;
            padding: 12px 16px; background: var(--bg-tertiary); border: 1px solid var(--glass-border);
            border-radius: var(--radius-lg); box-shadow: var(--shadow-md); color: var(--text-primary);
            font-size: 13px; font-weight: 500; min-width: 280px; max-width: 400px;
            animation: toastIn 0.35s cubic-bezier(0.16, 1, 0.3, 1);
            transition: all var(--transition-medium);
        }
        .toast.success { border-left: 3px solid var(--success); }
        .toast.error { border-left: 3px solid var(--error); }
        .toast.info { border-left: 3px solid var(--accent); }
        .toast.removing { opacity: 0; transform: translateX(20px); }
        @keyframes toastIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }

        /* --- Skeleton Loaders (Loom) --- */
        .skeleton { background: linear-gradient(90deg, var(--glass) 25%, var(--glass-hover) 50%, var(--glass) 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: var(--radius-sm); }
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .typing-indicator { display: flex; gap: 4px; padding: 4px 0; }
        .typing-indicator span { width: 6px; height: 6px; background: var(--text-tertiary); border-radius: 50%; animation: bounce 1.4s infinite ease-in-out both; }
        .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
        .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }

        /* --- Quick Actions (Raycast) --- */
        .quick-actions { display: flex; gap: 6px; flex-wrap: wrap; padding: 0 16px 8px; }
        .quick-action-chip {
            display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px;
            background: var(--glass); border: 1px solid var(--glass-border); border-radius: var(--radius-full);
            color: var(--text-secondary); font-size: 12px; font-weight: 500; cursor: pointer;
            transition: all var(--transition-fast); user-select: none;
        }
        .quick-action-chip:hover { background: var(--glass-hover); border-color: var(--glass-border-hover); color: var(--text-primary); transform: translateY(-1px); }
        .quick-action-chip kbd { font-size: 10px; background: var(--bg-tertiary); padding: 1px 5px; border-radius: 4px; color: var(--text-tertiary); font-family: inherit; }

        /* --- Improved Message Animations --- */
        .msg { animation: messageIn 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
        @keyframes messageIn { from { opacity: 0; transform: translateY(8px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }

        /* --- Improved Scrollbar --- */
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--glass); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--glass-hover); }

        /* --- Keyboard Shortcut Hints --- */
        .kbd-hint { font-size: 11px; color: var(--text-tertiary); background: var(--glass); padding: 2px 6px; border-radius: 4px; border: 1px solid var(--glass-border); }

        /* --- ONYX Icon System --- */
        .onyx-icon-slot { display: inline-flex; align-items: center; justify-content: center; color: currentColor; flex-shrink: 0; }
        .onyx-icon { display: block; width: 100%; height: 100%; color: currentColor; }
        .onyx-icon--xs { width: 12px; height: 12px; }
        .onyx-icon--sm { width: 14px; height: 14px; }
        .onyx-icon--md { width: 16px; height: 16px; }
        .onyx-icon--lg { width: 18px; height: 18px; }
        .onyx-icon--xl { width: 20px; height: 20px; }
        .conv-item-icon { display: inline-flex; align-items: center; justify-content: center; color: var(--text-tertiary); flex-shrink: 0; }
        .msg-body { display: flex; align-items: flex-start; gap: 10px; }
        .msg-content { min-width: 0; flex: 1; }
        .msg-prefix-icon {
            display: inline-flex; align-items: center; justify-content: center;
            width: 28px; height: 28px; border-radius: 999px;
            background: var(--glass); border: 1px solid var(--glass-border);
            color: var(--text-secondary); flex-shrink: 0; margin-top: 1px;
        }
        .msg-prefix-icon.is-success { color: var(--success); }
        .msg-prefix-icon.is-error { color: var(--error); }
        .msg-prefix-icon.is-warning { color: var(--warning); }
         .toast-icon {
             display: inline-flex; align-items: center; justify-content: center;
             width: 18px; height: 18px; color: currentColor; flex-shrink: 0;
         }

         /* --- Notification Bell with Badge --- */
         .notif-badge {
             position: absolute;
             top: 4px;
             right: 4px;
             min-width: 18px;
             height: 18px;
             padding: 0 4px;
             background: var(--error);
             color: #fff;
             font-size: 11px;
             font-weight: 700;
             border-radius: 9px;
             display: flex;
             align-items: center;
             justify-content: center;
             line-height: 1;
             opacity: 0;
             transform: scale(0.8);
             transition: all var(--transition-fast);
         }
         .header-action-btn.has-notif .notif-badge { opacity: 1; transform: scale(1); }

         /* --- Notification Panel --- */
         #notif-panel {
             position: fixed;
             top: 56px;
             right: 16px;
             width: 340px;
             max-height: 60vh;
             background: var(--bg-secondary);
             border: 1px solid var(--glass-border);
             border-radius: var(--radius-xl);
             box-shadow: var(--shadow-lg);
             backdrop-filter: blur(16px);
             z-index: 999;
             display: none;
             flex-direction: column;
             overflow: hidden;
         }
         #notif-panel.show { display: flex; animation: panelIn 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
         @keyframes panelIn { from { opacity: 0; transform: translateY(-8px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
         #notif-panel .notif-header {
             padding: 14px 16px 10px;
             border-bottom: 1px solid var(--glass-border);
             font-size: 13px;
             font-weight: 600;
             color: var(--text-secondary);
             text-transform: uppercase;
             letter-spacing: 0.5px;
             display: flex;
             justify-content: space-between;
             align-items: center;
         }
         #notif-panel .notif-header .clear-all {
             font-size: 11px;
             color: var(--accent);
             cursor: pointer;
             font-weight: 500;
         }
         .notif-list { flex: 1; overflow-y: auto; }
         .notif-item {
             padding: 10px 14px;
             border-bottom: 1px solid var(--glass-border);
             cursor: pointer;
             transition: all var(--transition-fast);
         }
         .notif-item:hover { background: var(--glass); }
         .notif-item .notif-title {
             font-size: 12px;
             font-weight: 600;
             color: var(--text-primary);
             margin-bottom: 2px;
         }
         .notif-item .notif-msg {
             font-size: 12px;
             color: var(--text-secondary);
             line-height: 1.4;
         }
         .notif-item .notif-time {
             font-size: 10px;
             color: var(--text-tertiary);
             margin-top: 4px;
         }
         .notif-item.unread { border-left: 2px solid var(--accent); }

         /* --- Settings Modal --- */
         #settings-modal {
             position: fixed; inset: 0;
             background: rgba(0,0,0,0.7);
             backdrop-filter: blur(12px);
             z-index: 1000;
             display: none;
             align-items: center;
             justify-content: center;
             opacity: 0;
             transition: opacity 0.3s;
         }
         #settings-modal.show { display: flex; opacity: 1; }
         .settings-card {
             background: var(--bg-secondary);
             border: 1px solid var(--glass-border);
             border-radius: var(--radius-xl);
             padding: 24px;
             width: 90%;
             max-width: 420px;
             box-shadow: var(--shadow-lg);
             animation: cardIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
         }
         @keyframes cardIn { from { opacity: 0; transform: scale(0.95) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }
         .settings-card h2 { font-size: 20px; font-weight: 700; margin-bottom: 16px; }
         .settings-card .setting-group { margin-bottom: 16px; }
         .settings-card .setting-group label {
             display: block;
             font-size: 12px;
             font-weight: 600;
             text-transform: uppercase;
             letter-spacing: 0.5px;
             color: var(--text-tertiary);
             margin-bottom: 6px;
         }
         .settings-card .setting-group input,
         .settings-card .setting-group select {
             width: 100%;
             padding: 10px 14px;
             background: var(--input-bg);
             border: 1px solid var(--glass-border);
             border-radius: var(--radius-md);
             font-size: 14px;
             color: var(--text-primary);
             outline: none;
             transition: var(--transition-fast);
         }
         .settings-card .setting-group input:focus,
         .settings-card .setting-group select:focus { border-color: var(--accent); }
         .settings-card .setting-row {
             display: flex;
             align-items: center;
             justify-content: space-between;
             padding: 10px 0;
             border-bottom: 1px solid var(--glass-border);
         }
         .settings-card .setting-row:last-child { border-bottom: none; }
         .settings-card .setting-row .label {
             font-size: 14px;
             color: var(--text-primary);
         }
         .settings-actions { display: flex; gap: 12px; margin-top: 20px; }
         .settings-actions button {
             flex: 1;
             padding: 12px;
             border-radius: var(--radius-md);
             font-size: 14px;
             font-weight: 600;
             cursor: pointer;
             transition: var(--transition-fast);
         }
         .settings-actions .cancel {
             background: var(--glass);
             border: 1px solid var(--glass-border);
             color: var(--text-secondary);
         }
         .settings-actions .cancel:hover { background: var(--glass-hover); }
         .settings-actions .save {
             background: var(--accent);
             border: none;
             color: #fff;
         }
         .settings-actions .save:hover { background: var(--accent-hover); }

         /* --- Apple-inspired settings surface --- */
         .settings-card-apple { max-width: 560px; padding: 28px; border-radius: 24px; background: color-mix(in srgb, var(--bg-secondary) 88%, #fff 12%); }
         .settings-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
         .settings-eyebrow { color:var(--text-tertiary); font-size:10px; letter-spacing:1.4px; font-weight:700; }
         .settings-card-apple h2 { margin:4px 0 0; font-size:28px; letter-spacing:-.6px; }
         .settings-subtitle { margin:-8px 0 22px; color:var(--text-secondary); font-size:13px; }
         .settings-close { width:30px; height:30px; border:0; border-radius:50%; background:var(--glass); color:var(--text-secondary); font-size:22px; line-height:1; cursor:pointer; }
         .settings-close:hover { background:var(--glass-hover); color:var(--text-primary); }
         .settings-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
         .settings-card-apple output { float:right; color:var(--accent); font-variant-numeric:tabular-nums; }
         .settings-card-apple input[type=range] { padding:0; accent-color:var(--accent); }
         .settings-card-apple .setting-row small { display:block; margin-top:3px; color:var(--text-tertiary); font-size:11px; }
         @media (max-width:600px) { .settings-grid { grid-template-columns:1fr; } .settings-card-apple { padding:22px; } }

         /* --- Copy Button on Messages --- */
         .msg { position: relative; }
         .copy-btn {
             position: absolute;
             top: 6px;
             right: 6px;
             width: 28px;
             height: 28px;
             border-radius: 8px;
             background: var(--glass);
             border: 1px solid var(--glass-border);
             color: var(--text-tertiary);
             display: flex;
             align-items: center;
             justify-content: center;
             opacity: 0;
             transition: all var(--transition-fast);
             cursor: pointer;
             z-index: 2;
         }
         .msg.onyx:hover .copy-btn { opacity: 1; }
         .copy-btn:hover {
             background: var(--glass-hover);
             color: var(--text-primary);
             transform: scale(1.05);
         }
         .copy-btn.copied { color: var(--success); }

         /* --- Suggestion Chips --- */
         .suggestion-chips {
             display: flex;
             flex-wrap: wrap;
             gap: 8px;
             padding: 0 16px 16px;
             justify-content: center;
         }
         .suggestion-chip {
             padding: 8px 16px;
             background: var(--glass);
             border: 1px solid var(--glass-border);
             border-radius: var(--radius-full);
             font-size: 13px;
             color: var(--text-secondary);
             cursor: pointer;
             transition: all var(--transition-fast);
             user-select: none;
         }
         .suggestion-chip:hover {
             background: var(--glass-hover);
             color: var(--text-primary);
             transform: translateY(-1px);
         }

         /* --- Enhanced Input Area (Textarea) --- */
         #input-area textarea {
             flex: 1;
             background: var(--input-bg);
             border: 1px solid var(--glass-border);
             border-radius: 24px;
             padding: 12px 16px;
             font-size: 15px;
             color: var(--text-primary);
             outline: none;
             transition: 0.2s;
             min-height: 44px;
             max-height: 160px;
             resize: none;
             font-family: inherit;
             overflow-y: auto;
         }
         #input-area textarea:focus { border-color: var(--accent); }
         #input-area textarea::placeholder { color: var(--text-secondary); }
         #emoji-toggle {
             background: none;
             border: none;
             color: var(--text-secondary);
             cursor: pointer;
             font-size: 18px;
             padding: 4px;
             border-radius: 6px;
             transition: var(--transition-fast);
         }
         #emoji-toggle:hover { background: var(--glass); color: var(--text-primary); }

         /* --- Emoji Picker --- */
         #emoji-picker {
             position: absolute;
             bottom: 70px;
             right: 16px;
             background: var(--bg-secondary);
             border: 1px solid var(--glass-border);
             border-radius: var(--radius-lg);
             padding: 8px;
             box-shadow: var(--shadow-lg);
             z-index: 900;
             display: none;
             flex-wrap: wrap;
             gap: 4px;
             max-width: 220px;
         }
         #emoji-picker.show { display: flex; }
         #emoji-picker button {
             width: 32px;
             height: 32px;
             border: none;
             background: transparent;
             font-size: 18px;
             cursor: pointer;
             border-radius: 6px;
             transition: var(--transition-fast);
             padding: 0;
         }
         #emoji-picker button:hover { background: var(--glass); }

         /* --- Connection Status Dot --- */
         .conn-status {
             display: inline-flex;
             align-items: center;
             gap: 4px;
             font-size: 11px;
             color: var(--success);
         }
         .conn-status.offline { color: var(--error); }

         /* --- Scroll to Bottom Button --- */
         #scroll-to-bottom {
             position: absolute;
             bottom: 90px;
             right: 24px;
             width: 36px;
             height: 36px;
             border-radius: 50%;
             background: var(--accent);
             color: #fff;
             border: none;
             display: none;
             align-items: center;
             justify-content: center;
             cursor: pointer;
             box-shadow: var(--shadow-md);
             transition: all var(--transition-fast);
             z-index: 10;
         }
         #scroll-to-bottom.show { display: flex; }
         #scroll-to-bottom:hover { transform: scale(1.05); }
         #scroll-to-bottom.fade-out { opacity: 0; }
     </style>
</head>
<body>
    <!-- Command Palette -->
    <div id="cmd-palette-overlay">
        <div class="cmd-palette">
            <input type="text" class="cmd-palette-input" placeholder="Tapez une commande ou recherchez..." autocomplete="off">
            <div class="cmd-palette-list"></div>
        </div>
    </div>

    <!-- Toast Container -->
    <div id="toast-container"></div>

    <!-- Notification Panel -->
    <div id="notif-panel">
        <div class="notif-header">
            <span>Notifications</span>
            <span class="clear-all" id="notif-clear-all">Tout effacer</span>
        </div>
        <div class="notif-list" id="notif-list"></div>
    </div>

    <!-- Settings Modal -->
    <div id="settings-modal">
        <div class="settings-card settings-card-apple">
            <div class="settings-heading"><div><span class="settings-eyebrow">ONYX CONTROL CENTER</span><h2>Paramètres</h2></div><button class="settings-close" id="settings-close" aria-label="Fermer">×</button></div>
            <p class="settings-subtitle">Personnalisez votre espace et le comportement de l’assistant.</p>
            <div class="setting-group">
                <label for="setting-serper">Clé API Serper (recherche web)</label>
                <input type="password" id="setting-serper" placeholder="Clé API Serper (optionnel)">
            </div>
            <div class="setting-group">
                <label for="setting-language">Langue</label>
                <select id="setting-language">
                    <option value="fr">Français</option>
                    <option value="en">English</option>
                    <option value="es">Español</option>
                    <option value="de">Deutsch</option>
                    <option value="it">Italiano</option>
                </select>
            </div>
            <div class="setting-group">
                <label for="setting-model">Modèle principal</label>
                <select id="setting-model"><option value="qwen2.5-7b-instruct">Qwen 2.5 · équilibré</option><option value="mistral-7b-instruct-v0.2">Mistral · rapide</option></select>
            </div>
            <div class="settings-grid">
                <div class="setting-group"><label for="setting-temperature">Créativité <output id="setting-temperature-value">0.3</output></label><input type="range" id="setting-temperature" min="0" max="1.5" step="0.1" value="0.3"></div>
                <div class="setting-group"><label for="setting-max-tokens">Limite de réponse</label><input type="number" id="setting-max-tokens" min="128" max="4096" step="128" value="1024"></div>
            </div>
            <div class="setting-group"><label for="setting-timeout">Délai maximal (secondes)</label><input type="number" id="setting-timeout" min="15" max="300" step="15" value="120"></div>
            <div class="setting-row">
                <span class="label">Thème sombre</span>
                <label class="toggle-switch" style="position:relative;width:44px;height:24px;">
                    <input type="checkbox" id="setting-dark-mode" checked style="opacity:0;width:0;height:0;">
                    <span style="position:absolute;inset:0;border-radius:9999px;background:var(--glass);border:1px solid var(--glass-border);"></span>
                    <span style="position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:var(--accent);transition:transform 0.2s;"></span>
                </label>
            </div>
            <div class="setting-row">
                <span class="label">Sauvegarde cloud (bêta)</span>
                <label class="toggle-switch" style="position:relative;width:44px;height:24px;">
                    <input type="checkbox" id="setting-cloud-sync" style="opacity:0;width:0;height:0;">
                    <span style="position:absolute;inset:0;border-radius:9999px;background:var(--glass);border:1px solid var(--glass-border);"></span>
                    <span style="position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:var(--accent);transition:transform 0.2s;"></span>
                </label>
            </div>
            <div class="setting-row">
                <span class="label">Synthèse vocale</span>
                <label class="toggle-switch" style="position:relative;width:44px;height:24px;">
                    <input type="checkbox" id="setting-voice" checked style="opacity:0;width:0;height:0;">
                    <span style="position:absolute;inset:0;border-radius:9999px;background:var(--glass);border:1px solid var(--glass-border);"></span>
                    <span style="position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:var(--accent);transition:transform 0.2s;"></span>
                </label>
            </div>
            <div class="setting-row"><span class="label">Mémoire compacte <small>Réduit l’empreinte en contexte</small></span><label class="toggle-switch" style="position:relative;width:44px;height:24px;"><input type="checkbox" id="setting-compact-memory" checked style="opacity:0;width:0;height:0;"><span style="position:absolute;inset:0;border-radius:9999px;background:var(--glass);border:1px solid var(--glass-border);"></span><span style="position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:var(--accent);transition:transform 0.2s;"></span></label></div>
            <div class="settings-actions">
                <button class="cancel" id="settings-cancel">Annuler</button>
                <button class="save" id="settings-save">Enregistrer</button>
            </div>
        </div>
    </div>

    <!-- Main App -->
    <div id="app">
        <div id="sidebar-backdrop"></div>
        <div id="sidebar">
            <div id="sidebar-header">
                <h1>Onyx</h1>
                <button id="new-chat-btn" aria-label="Nouvelle conversation"><span class="onyx-icon-slot" data-onyx-icon="new-chat" data-icon-size="md"></span></button>
            </div>
            <div style="padding: 0 14px 8px;">
                <input type="text" id="sidebar-search" placeholder="Rechercher..." style="width:100%; padding:8px 12px; background:var(--glass); border:1px solid var(--glass-border); border-radius:var(--radius-md); color:var(--text-primary); font-size:13px; outline:none; transition:all var(--transition-fast);">
            </div>
            <div class="system-context-card" aria-label="État du système Onyx">
                <div class="context-title"><span class="context-pulse"></span> Noyau Onyx opérationnel</div>
                <div class="context-copy">Assistant local francophone avec mémoire persistante et routage cognitif adaptatif.</div>
                <div class="context-tags">
                    <span class="context-tag">NEXUS</span><span class="context-tag">SYNAPSE-X</span><span class="context-tag">KAIROS</span><span class="context-tag">STM / LTM</span>
                </div>
            </div>
            <div id="conversation-list"></div>
            <div id="user-info">
                <div id="user-avatar">O</div>
                <span id="user-name">Utilisateur</span>
            </div>
        </div>
        <div id="main">
            <div id="chat-header">
                <button id="menu-toggle" aria-label="Ouvrir la navigation"><span class="onyx-icon-slot" data-onyx-icon="menu" data-icon-size="lg"></span></button>
                <span id="chat-header-title">Conversation</span>
                <div id="voice-indicator-pill" class="voice-pill listening" title="Système vocal local (Mot-clé: hey_jarvis)">
                    <span class="voice-dot"></span>
                    <span id="voice-status-text">Écoute "hey_jarvis"</span>
                    <button id="voice-toggle-btn" class="voice-icon-btn" aria-label="Mettre le micro en pause"><span class="onyx-icon-slot" data-onyx-icon="voice" data-icon-size="sm"></span></button>
                </div>
                <span id="sentiment-pill" title="État émotionnel détecté dans le dernier message">◌ <span id="sentiment-label">Neutre</span></span>
                <button class="header-action-btn" id="theme-toggle" aria-label="Basculer le thème"><span class="onyx-icon-slot" data-onyx-icon="theme-dark" data-icon-size="lg"></span></button>
                <button class="header-action-btn" id="export-btn" aria-label="Exporter la conversation"><span class="onyx-icon-slot" data-onyx-icon="export" data-icon-size="lg"></span></button>
                <button class="header-action-btn" id="history-btn" aria-label="Voir l’historique"><span class="onyx-icon-slot" data-onyx-icon="history" data-icon-size="lg"></span></button>
                <button class="header-action-btn" id="notif-btn" aria-label="Notifications"><span class="onyx-icon-slot" data-onyx-icon="bell" data-icon-size="lg"></span><span class="notif-badge" id="notif-badge"></span></button>
                <button class="header-action-btn" id="settings-btn" aria-label="Paramètres"><span class="onyx-icon-slot" data-onyx-icon="settings" data-icon-size="lg"></span></button>
            </div>
            <div id="messages">
                <div id="empty-state" class="empty-state visible">
                    <div class="empty-state-icon"><span class="onyx-icon-slot" data-onyx-icon="assistant" data-icon-size="xl" style="color:var(--accent);"></span></div>
                    <h3>Bonjour, je suis Onyx</h3>
                    <p>Votre assistant intelligent local. Posez-moi une question ou utilisez une commande rapide ci-dessous.</p>
                    <div class="empty-state-actions">
                        <button class="empty-state-btn primary" onclick="cmdInput.focus()">Nouvelle conversation</button>
                        <button class="empty-state-btn" onclick="openCmdPalette()">Voir les commandes</button>
                    </div>
                    <div class="suggestion-chips">
                        <span class="suggestion-chip" onclick="quickPrompt('Quelle est la météo à Paris ?')">Météo Paris</span>
                        <span class="suggestion-chip" onclick="quickPrompt('Donne-moi les dernières actualités')">Actualités</span>
                        <span class="suggestion-chip" onclick="quickPrompt('Explique-moi la théorie de la relativité')">Expliquer un concept</span>
                        <span class="suggestion-chip" onclick="quickPrompt('Rédige une fonction Python pour trier une liste')">Code Python</span>
                        <span class="suggestion-chip" onclick="quickPrompt('Quelle est la capital du Brésil ?')">Question factuelle</span>
                        <span class="suggestion-chip" onclick="quickPrompt('Crée une tâche pour demain')">Gérer tâches</span>
                    </div>
                </div>
            </div>
            <div style="position:relative;">
                <div id="input-area">
                    <button id="file-upload-btn" title="Joindre un fichier" aria-label="Joindre un fichier"><span class="onyx-icon-slot" data-onyx-icon="attach" data-icon-size="lg"></span></button>
                    <textarea id="cmd-input" placeholder="Posez votre question ou utilisez /cmd... (Shift+Entrée pour un saut de ligne)" rows="1" autocomplete="off" spellcheck="true"></textarea>
                    <button id="emoji-toggle" title="Emoji" aria-label="Emoji"><span class="onyx-icon-slot" data-onyx-icon="smile" data-icon-size="lg"></span></button>
                    <button id="send-btn" title="Envoyer" aria-label="Envoyer"><span class="onyx-icon-slot" data-onyx-icon="send" data-icon-size="lg"></span></button>
                </div>
                <div id="emoji-picker">
                    <button onclick="insertEmoji(' ')" style="font-size:16px;">+</button>
                    <button onclick="insertEmoji('')"></button>
                    <button onclick="insertEmoji('')"></button>
                    <button onclick="insertEmoji('')"></button>
                    <button onclick="insertEmoji('')"></button>
                    <button onclick="insertEmoji('')"></button>
                    <button onclick="insertEmoji('')"></button>
                    <button onclick="insertEmoji('')"></button>
                    <button onclick="insertEmoji('')"></button>
                </div>
                <button id="scroll-to-bottom" title="Descendre"><span class="onyx-icon-slot" data-onyx-icon="arrow-down" data-icon-size="sm"></span></button>
            </div>
            <div class="quick-actions">
                <button class="quick-action-chip" data-action="new-chat"><span class="onyx-icon-slot" data-onyx-icon="new-chat" data-icon-size="xs"></span> Nouveau chat <kbd>Cmd+N</kbd></button>
                <button class="quick-action-chip" data-action="export"><span class="onyx-icon-slot" data-onyx-icon="export" data-icon-size="xs"></span> Exporter <kbd>Cmd+E</kbd></button>
                <button class="quick-action-chip" data-action="theme"><span class="onyx-icon-slot" data-onyx-icon="theme-light" data-icon-size="xs"></span> Thème <kbd>Cmd+D</kbd></button>
                <button class="quick-action-chip" data-action="palette"><span class="onyx-icon-slot" data-onyx-icon="search" data-icon-size="xs"></span> Commandes <kbd>Cmd+K</kbd></button>
            </div>
            <input type="file" id="file-input" style="display:none" multiple>
        </div>
    </div>

    <!-- History Modal -->
    <div id="history-modal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.6); backdrop-filter:blur(8px); z-index:999; align-items:center; justify-content:center; padding:20px;">
        <div style="background:var(--bg-secondary); border-radius:24px; padding:20px; max-width:500px; width:100%; max-height:80vh; overflow-y:auto;">
            <h2 style="margin-bottom:16px;">Historique</h2>
            <div id="history-list"></div>
            <button id="close-history" style="margin-top:16px; background:var(--glass); border:none; border-radius:12px; padding:10px 20px; color:var(--text-primary); cursor:pointer; width:100%;">Fermer</button>
        </div>
    </div>

    <script type="importmap">
        {
            "imports": {
                "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"
            }
        }
    </script>
    <script type="module">
        import * as THREE from 'three';

        // --- DOM refs ---
        const convList = document.getElementById('conversation-list');
        const messages = document.getElementById('messages');
        const cmdInput = document.getElementById('cmd-input');
        const sendBtn = document.getElementById('send-btn');
        const newChatBtn = document.getElementById('new-chat-btn');
        const themeToggle = document.getElementById('theme-toggle');
        const exportBtn = document.getElementById('export-btn');
        const historyBtn = document.getElementById('history-btn');
        const fileUploadBtn = document.getElementById('file-upload-btn');
        const fileInput = document.getElementById('file-input');
        const historyModal = document.getElementById('history-modal');
        const historyList = document.getElementById('history-list');
        const closeHistory = document.getElementById('close-history');
        const chatHeaderTitle = document.getElementById('chat-header-title');
        const menuToggle = document.getElementById('menu-toggle');
        const sidebar = document.getElementById('sidebar');
        const sidebarBackdrop = document.getElementById('sidebar-backdrop');
        const notifBtn = document.getElementById('notif-btn');
        const settingsBtn = document.getElementById('settings-btn');
        const notifPanel = document.getElementById('notif-panel');
        const notifList = document.getElementById('notif-list');
        const notifBadge = document.getElementById('notif-badge');
        const notifClearAll = document.getElementById('notif-clear-all');
        const settingsModal = document.getElementById('settings-modal');
        const settingsClose = document.getElementById('settings-close');
        const settingsCancel = document.getElementById('settings-cancel');
        const settingsSave = document.getElementById('settings-save');
        const settingSerper = document.getElementById('setting-serper');
        const settingLanguage = document.getElementById('setting-language');
        const settingDarkMode = document.getElementById('setting-dark-mode');
        const settingCloudSync = document.getElementById('setting-cloud-sync');
        const settingVoice = document.getElementById('setting-voice');
        const settingCompactMemory = document.getElementById('setting-compact-memory');
        const settingModel = document.getElementById('setting-model');
        const settingTemperature = document.getElementById('setting-temperature');
        const settingTemperatureValue = document.getElementById('setting-temperature-value');
        const settingMaxTokens = document.getElementById('setting-max-tokens');
        const settingTimeout = document.getElementById('setting-timeout');
        const emojiToggle = document.getElementById('emoji-toggle');
        const emojiPicker = document.getElementById('emoji-picker');
        const scrollToBottomBtn = document.getElementById('scroll-to-bottom');

        let sessionId = localStorage.getItem('onyx_session_id') || '';
        let username = '';
        let currentConvId = localStorage.getItem('onyx_current_conv') || null;
        let messageCounter = 0;
        let docMode = false;
        let isDark = true;
        let notifCount = 0;
        let emojiOpen = false;
        const EMOJIS = ['😀','😉','😎','🤔','👍','🎉','❤️','😊','😂','👏'];

        const ONYX_ICON_MAP = {
            'new-chat': 'plus',
            'logout': 'log-out',
            'menu': 'menu',
            'voice': 'mic',
            'voice-off': 'mic-off',
            'theme-dark': 'moon',
            'theme-light': 'sun',
            'export': 'download',
            'history': 'history',
            'bell': 'bell',
            'settings': 'settings',
            'copy': 'copy',
            'check': 'check',
            'assistant': 'sparkles',
            'attach': 'paperclip',
            'send': 'arrow-up',
            'search': 'search',
            'delete': 'trash-2',
            'close': 'x',
            'smile': 'smile',
            'arrow-down': 'arrow-down',
            'success': 'circle-check',
            'error': 'circle-x',
            'info': 'info',
            'warning': 'triangle-alert',
            'news': 'newspaper',
            'email': 'mail',
            'memory': 'brain',
            'todo': 'list-todo',
            'system': 'monitor',
            'weather': 'cloud-sun',
            'volume': 'volume-2',
            'summary': 'file-text',
            'analytics': 'chart-column',
            'tool': 'wrench',
            'conversation': 'message-square',
            'command': 'terminal'
        };

        function iconMarkup(name, { size = 'md', className = '' } = {}) {
            const lucideName = ONYX_ICON_MAP[name] || name;
            const classes = ['onyx-icon', `onyx-icon--${size}`, className].filter(Boolean).join(' ');
            return `<i data-lucide="${lucideName}" class="${classes}" aria-hidden="true"></i>`;
        }

        function refreshIcons() {
            lucide.createIcons({
                attrs: {
                    'stroke-width': '1.75',
                    'stroke-linecap': 'round',
                    'stroke-linejoin': 'round'
                }
            });
        }

        function setOnyxIcon(element, name, options = {}) {
            if (!element) return;
            element.innerHTML = iconMarkup(name, options);
            refreshIcons();
        }

        function hydrateOnyxIcons(root = document) {
            root.querySelectorAll('[data-onyx-icon]').forEach(slot => {
                slot.innerHTML = iconMarkup(slot.dataset.onyxIcon, {
                    size: slot.dataset.iconSize || 'md',
                    className: slot.dataset.iconClass || ''
                });
            });
            refreshIcons();
        }

        function normalizeUiCopy(text) {
            if (!text) return '';
            return text
                .replace(/(^|\n)\s*📰\s+/g, '$1')
                .replace(/(^|\n)\s*📬\s+/g, '$1')
                .replace(/(^|\n)\s*🌤️\s+/g, '$1')
                .replace(/(^|\n)\s*💻\s+/g, '$1')
                .replace(/(^|\n)\s*📊\s+/g, '$1')
                .replace(/(^|\n)\s*📋\s+/g, '$1')
                .replace(/(^|\n)\s*🔍\s+/g, '$1')
                .replace(/(^|\n)\s*💾\s+/g, '$1')
                .replace(/(^|\n)\s*📝\s+/g, '$1')
                .replace(/(^|\n)\s*🔊\s+/g, '$1Réponse vocale : ')
                .replace(/(^|\n)\s*🎙️\s+/g, '$1Transcription vocale : ')
                .replace(/(^|\n)\s*✅\s+/g, '$1Succès : ')
                .replace(/(^|\n)\s*❌\s+/g, '$1Erreur : ')
                .replace(/(^|\n)\s*⚠️\s+/g, '$1Attention : ')
                .replace(/(^|\n)\s*⚙️\s+/g, '$1Outil : ')
                .replace(/(^|\n)\s*⬜\s+/g, '$1À faire : ');
        }

        function detectMessageMeta(sender, text) {
            if (sender === 'user') return null;
            const plain = (text || '').replace(/\*\*/g, '').trim().toLowerCase();
            if (!plain) return null;
            if (plain.startsWith('erreur')) return { icon: 'error', tone: 'error' };
            if (plain.startsWith('attention')) return { icon: 'warning', tone: 'warning' };
            if (plain.startsWith('succès') || plain.startsWith('exécution réussie')) return { icon: 'success', tone: 'success' };
            if (plain.startsWith('actualités')) return { icon: 'news' };
            if (plain.startsWith('derniers emails') || plain.startsWith('emails non lus') || plain.startsWith('aucun email')) return { icon: 'email' };
            if (plain.startsWith('résultats de la mémoire') || plain.startsWith('aucun souvenir')) return { icon: 'memory' };
            if (plain.startsWith('vos tâches') || plain.startsWith('planification d\'objectif') || plain.startsWith('aucune tâche')) return { icon: 'todo' };
            if (plain.startsWith('statut système') || plain.startsWith("rapport d'état système")) return { icon: 'system' };
            if (plain.startsWith('météo')) return { icon: 'weather' };
            if (plain.startsWith('analyse de données')) return { icon: 'analytics' };
            if (plain.startsWith('résumé du fichier') || plain.startsWith('conversation exportée')) return { icon: 'summary' };
            if (plain.startsWith('outil')) return { icon: 'tool' };
            if (plain.startsWith('réponse vocale')) return { icon: 'volume' };
            if (plain.startsWith('transcription vocale')) return { icon: 'voice' };
            return null;
        }

        function formatMessageContent(sender, text) {
            const source = sender === 'user' ? text : normalizeUiCopy(text);
            return source
                .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
                .replace(/```python([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.+?)\*/g, '<em>$1</em>')
                .replace(/\n/g, '<br>');
        }

        function buildMessageMarkup(sender, text) {
            const normalized = sender === 'user' ? text : normalizeUiCopy(text);
            const meta = detectMessageMeta(sender, normalized);
            const formatted = formatMessageContent(sender, text);
            const body = meta?.icon
                ? `<div class="msg-body"><span class="msg-prefix-icon${meta.tone ? ` is-${meta.tone}` : ''}">${iconMarkup(meta.icon, { size: 'md' })}</span><div class="msg-content">${formatted}</div></div>`
                : formatted;
            let copyHtml = '';
            if (sender === 'onyx') {
                copyHtml = `<button class="copy-btn" onclick="copyMessage(this)" aria-label="Copier"><span class="onyx-icon-slot" data-onyx-icon="copy" data-icon-size="sm"></span></button>`;
            }
            return body + copyHtml + `<span class="time">${new Date().toLocaleTimeString()}</span>`;
        }

        function toggleSidebar() {
            const open = sidebar.classList.toggle('open');
            sidebarBackdrop.classList.toggle('show', open);
        }
        menuToggle.addEventListener('click', toggleSidebar);
        sidebarBackdrop.addEventListener('click', toggleSidebar);

        function showLogin() { /* auth désactivée */ }
        function hideLogin() { /* auth désactivée */ }

        async function login(user, pass) {
            return true;
        }

        loginBtn && loginBtn.addEventListener('click', async () => {
            await login();
        });
        registerLink && registerLink.addEventListener('click', async () => {
            await login();
        });
        logoutBtn && logoutBtn.addEventListener('click', () => {
            return;
        });

        themeToggle.addEventListener('click', () => {
            isDark = !isDark;
            document.body.classList.toggle('light-mode', !isDark);
            setOnyxIcon(themeToggle, isDark ? 'theme-dark' : 'theme-light', { size: 'lg' });
        });

        async function loadConversations() {
            if (!sessionId) return;
            const res = await fetch('/api/history/list', { headers: { 'X-Session-ID': sessionId } });
            const data = await res.json();
            if (data.conversations) {
                convList.innerHTML = data.conversations.map(conv => `
                    <div class="conv-item ${conv.id === currentConvId ? 'active' : ''}" data-id="${conv.id}">
                        <span class="conv-item-icon">${iconMarkup('conversation', { size: 'sm' })}</span>
                        <span class="title">${conv.title || 'Sans titre'}</span>
                        <span class="date">${conv.updated_at ? conv.updated_at.slice(5,16).replace('T',' ') : ''}</span>
                        <button class="delete-btn" data-id="${conv.id}" aria-label="Supprimer cette conversation">${iconMarkup('delete', { size: 'sm' })}</button>
                    </div>
                `).join('');
                refreshIcons();
                document.querySelectorAll('.conv-item').forEach(el => {
                    el.addEventListener('click', (e) => {
                        if (e.target.closest('.delete-btn')) return;
                        const id = el.dataset.id;
                        loadConversation(id);
                        if (window.innerWidth < 768 && sidebar.classList.contains('open')) toggleSidebar();
                    });
                });
                document.querySelectorAll('.delete-btn').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const id = btn.dataset.id;
                        deleteConversation(id);
                    });
                });
            }
        }

        async function loadConversation(convId) {
            if (!sessionId) return;
            const res = await fetch('/api/history/load', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                body: JSON.stringify({ conv_id: convId })
            });
            const data = await res.json();
            if (data.messages) {
                const emptyState = document.getElementById('empty-state');
                if (emptyState) emptyState.classList.remove('visible');
                messages.innerHTML = '';
                data.messages.forEach(msg => {
                    const sender = msg.role === 'user' ? 'user' : 'onyx';
                    appendMessage(sender, msg.content, false);
                });
                currentConvId = convId;
                localStorage.setItem('onyx_current_conv', currentConvId);
                chatHeaderTitle.textContent = data.messages.length > 0 ? data.messages[0].content.slice(0,40) : 'Conversation';
                await loadConversations();
                messages.scrollTop = messages.scrollHeight;
            }
        }

        async function deleteConversation(convId) {
            if (!confirm('Supprimer cette conversation ?')) return;
            await fetch('/api/history/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                body: JSON.stringify({ conv_id: convId })
            });
            if (currentConvId === convId) {
                currentConvId = null;
                messages.innerHTML = '';
                const emptyState = document.getElementById('empty-state');
                if (emptyState) emptyState.classList.add('visible');
                chatHeaderTitle.textContent = 'Conversation';
            }
            await loadConversations();
        }

        async function newConversation() {
            const res = await fetch('/api/history/new', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }
            });
            const data = await res.json();
            if (data.conv_id) {
                currentConvId = data.conv_id;
                localStorage.setItem('onyx_current_conv', currentConvId);
                messages.innerHTML = '';
                const emptyState = document.getElementById('empty-state');
                if (emptyState) emptyState.classList.add('visible');
                chatHeaderTitle.textContent = 'Nouvelle conversation';
                await loadConversations();
                if (window.innerWidth < 768 && sidebar.classList.contains('open')) toggleSidebar();
            }
        }
        newChatBtn.addEventListener('click', newConversation);

        async function loadLastConversation() {
            const res = await fetch('/api/history/last', { headers: { 'X-Session-ID': sessionId } });
            const data = await res.json();
            if (data.conversation) {
                await loadConversation(data.conversation.id);
            } else {
                await newConversation();
            }
        }

        function appendMessage(sender, text, save = true) {
            const div = document.createElement('div');
            div.className = `msg ${sender}`;
            const formatted = text
                .replace(/```python([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
                .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
                .replace(/\n/g, '<br>');
            div.innerHTML = formatted + `<span class="time">${new Date().toLocaleTimeString()}</span>`;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
            return div;
        }

        async function sendMessage() {
            const text = cmdInput.value.trim();
            if (!text) return;
            cmdInput.value = '';
            const handled = await handleCommand(text);
            if (handled) return;

            appendMessage('user', text);
            const loadingId = appendMessage('onyx', 'Réflexion en cours...');

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                    body: JSON.stringify({
                        prompt: text,
                        language: 'fr',
                        doc_mode: docMode,
                        conv_id: currentConvId,
                        settings: {
                            serper_key: localStorage.getItem('serperKey') || '',
                            model: settingModel?.value || 'qwen2.5-7b-instruct',
                            temperature: Number(settingTemperature?.value || 0.3),
                            max_tokens: Number(settingMaxTokens?.value || 1024),
                            request_timeout: Number(settingTimeout?.value || 120),
                            compact_memory: settingCompactMemory?.checked !== false
                        }
                    })
                });
                const data = await res.json();
                const loadingEl = messages.querySelector(`.msg.onyx:last-child`);
                if (loadingEl) {
                    const formatted = data.response
                        .replace(/```python([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
                        .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
                        .replace(/\n/g, '<br>');
                    loadingEl.innerHTML = formatted + `<span class="time">${new Date().toLocaleTimeString()}</span>`;
                    if (data.model_used) {
                        loadingEl.innerHTML += `<span style="font-size:10px; opacity:0.5; display:block; margin-top:4px;">modèle: ${data.model_used}</span>`;
                    }
                    if (data.conv_id) {
                        await loadConversations();
                    }
                }
            } catch (err) {
                const loadingEl = messages.querySelector(`.msg.onyx:last-child`);
                if (loadingEl) loadingEl.innerHTML = 'Erreur serveur.';
                console.error(err);
            }
        }

        async function handleCommand(text) {
            if (text.startsWith('/weather')) {
                const city = text.replace('/weather', '').trim() || 'Paris';
                appendMessage('user', text);
                const res = await fetch('/api/weather', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }, body: JSON.stringify({ city }) });
                const data = await res.json();
                appendMessage('onyx', data.message || 'Erreur météo');
                return true;
            }
            if (text.startsWith('/news')) {
                let query = text.replace('/news', '').trim() || 'actualités';
                appendMessage('user', text);
                const res = await fetch('/api/news', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }, body: JSON.stringify({ query }) });
                const data = await res.json();
                let msg = '**Actualités**\n\n';
                data.articles.forEach((a, i) => {
                    msg += `${i+1}. ${a.title}\n${a.description || ''}\n[Lien](${a.url || '#'})\n\n`;
                });
                appendMessage('onyx', msg);
                return true;
            }
            if (text.startsWith('/mail') || text.startsWith('/email')) {
                const rest = text.startsWith('/mail') ? text.replace('/mail','').trim() : text.replace('/email','').trim();
                if (rest.startsWith('read') || rest === '') {
                    const parts = rest.split(' ');
                    let limit = 5;
                    if (parts.length>1 && !isNaN(parts[1])) limit = parseInt(parts[1]);
                    appendMessage('user', text);
                    const res = await fetch('/api/email/read', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }, body: JSON.stringify({ limit }) });
                    const data = await res.json();
                    if (data.success && data.emails && data.emails.length>0) {
                        let msg = '**Derniers emails non lus**\n\n';
                        data.emails.forEach((e,i) => {
                            msg += `${i+1}. **De :** ${e.from}\n   **Sujet :** ${e.subject}\n   **Aperçu :** ${e.snippet || '(vide)'}\n\n`;
                        });
                        appendMessage('onyx', msg);
                    } else {
                        appendMessage('onyx', 'Aucun email non lu trouvé.');
                    }
                    return true;
                } else {
                    const parts = rest.split('|');
                    if (parts.length < 3) {
                        appendMessage('onyx', 'Erreur : format attendu `/mail destinataire|sujet|message`.');
                        return true;
                    }
                    const [to, subject, body] = parts.map(s=>s.trim());
                    appendMessage('user', text);
                    const res = await fetch('/api/email/send', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }, body: JSON.stringify({ to, subject, body }) });
                    const data = await res.json();
                    appendMessage('onyx', data.message || data.error || 'Email envoyé');
                    return true;
                }
            }
            if (text.startsWith('/system')) {
                const cmd = text.replace('/system', '').trim();
                if (cmd.startsWith('lock')) {
                    appendMessage('user', text);
                    const res = await fetch('/api/system/lock', { method: 'POST', headers: { 'X-Session-ID': sessionId } });
                    const data = await res.json();
                    appendMessage('onyx', data.message || 'Commande exécutée');
                    return true;
                }
                if (cmd.startsWith('sleep')) {
                    appendMessage('user', text);
                    const res = await fetch('/api/system/sleep', { method: 'POST', headers: { 'X-Session-ID': sessionId } });
                    const data = await res.json();
                    appendMessage('onyx', data.message || 'Commande exécutée');
                    return true;
                }
                if (cmd.startsWith('restart')) {
                    appendMessage('user', text);
                    const res = await fetch('/api/system/restart', { method: 'POST', headers: { 'X-Session-ID': sessionId } });
                    const data = await res.json();
                    appendMessage('onyx', data.message || 'Commande exécutée');
                    return true;
                }
                if (cmd.startsWith('volume')) {
                    const parts = cmd.split(' ');
                    if (parts.length > 1) {
                        const vol = parseInt(parts[1]);
                        if (!isNaN(vol)) {
                            appendMessage('user', text);
                            const res = await fetch('/api/system/volume', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }, body: JSON.stringify({ level: vol }) });
                            const data = await res.json();
                            appendMessage('onyx', data.message || 'Volume réglé');
                            return true;
                        }
                    }
                    appendMessage('onyx', 'Erreur : utilisation `/system volume <niveau>`.');
                    return true;
                }
                if (cmd.startsWith('brightness')) {
                    const parts = cmd.split(' ');
                    if (parts.length > 1) {
                        const bright = parseInt(parts[1]);
                        if (!isNaN(bright)) {
                            appendMessage('user', text);
                            const res = await fetch('/api/system/brightness', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }, body: JSON.stringify({ level: bright }) });
                            const data = await res.json();
                            appendMessage('onyx', data.message || 'Luminosité réglée');
                            return true;
                        }
                    }
                    appendMessage('onyx', 'Erreur : utilisation `/system brightness <niveau>`.');
                    return true;
                }
                if (cmd.startsWith('status')) {
                    appendMessage('user', text);
                    const res = await fetch('/api/system/status', { method: 'GET', headers: { 'X-Session-ID': sessionId } });
                    const data = await res.json();
                    appendMessage('onyx', data.message || 'Statut système');
                    return true;
                }
                appendMessage('onyx', 'Erreur : commandes système disponibles `/system lock`, `/system sleep`, `/system restart`, `/system volume <n>`, `/system brightness <n>`, `/system status`.');
                return true;
            }
            if (text.startsWith('/launch')) {
                const app = text.replace('/launch', '').trim();
                if (app) {
                    appendMessage('user', text);
                    const res = await fetch('/api/system/launch', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }, body: JSON.stringify({ app_name: app }) });
                    const data = await res.json();
                    appendMessage('onyx', data.message || 'Lancement effectué');
                    return true;
                } else {
                    appendMessage('onyx', 'Erreur : veuillez spécifier une application, par exemple `/launch notepad`.');
                    return true;
                }
            }
            if (text.startsWith('/script')) {
                const script = text.replace('/script', '').trim();
                if (script) {
                    appendMessage('user', text);
                    const res = await fetch('/api/system/script', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }, body: JSON.stringify({ script_path: script }) });
                    const data = await res.json();
                    appendMessage('onyx', data.output || 'Script exécuté');
                    return true;
                } else {
                    appendMessage('onyx', 'Erreur : veuillez spécifier le chemin du script.');
                    return true;
                }
            }
            if (text.startsWith('/cmd')) {
                const cmd = text.replace('/cmd', '').trim();
                if (!cmd) { appendMessage('onyx', 'Erreur : veuillez fournir une commande après `/cmd`.'); return true; }
                appendMessage('user', text);
                const res = await fetch('/api/command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                    body: JSON.stringify({ command: cmd, confirm: true })
                });
                const data = await res.json();
                if (data.success) {
                    let msg = `Succès : commande exécutée : \`${cmd}\`\n\n`;
                    if (data.stdout) msg += `**Sortie :**\n\`\`\`\n${data.stdout}\n\`\`\``;
                    else msg += '*(Commande exécutée sans sortie)*';
                    appendMessage('onyx', msg);
                } else {
                    appendMessage('onyx', `Erreur : ${data.stderr || data.error}`);
                }
                return true;
            }
            if (text.startsWith('/code')) {
                const code = text.replace('/code','').trim();
                if (!code) { appendMessage('onyx','Erreur : veuillez fournir du code après `/code`.'); return true; }
                appendMessage('user', text);
                const res = await fetch('/api/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                    body: JSON.stringify({ code })
                });
                const data = await res.json();
                if (data.success) {
                    appendMessage('onyx', `Succès : **Exécution réussie**\n\n\`\`\`\n${data.output}\n\`\`\``);
                } else {
                    appendMessage('onyx', `Erreur : **Exécution**\n\n\`\`\`\n${data.error}\n\`\`\``);
                }
                return true;
            }
            if (text.startsWith('/ltm')) {
                const query = text.replace('/ltm','').trim();
                if (!query) { appendMessage('onyx','Erreur : veuillez fournir une recherche après `/ltm`.'); return true; }
                appendMessage('user', text);
                const res = await fetch('/api/ltm/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                    body: JSON.stringify({ query })
                });
                const data = await res.json();
                if (data.results && data.results.length>0) {
                    let msg = '**Résultats de la mémoire long terme :**\n\n';
                    data.results.forEach((item,i) => {
                        msg += `**${i+1}.** (${item.timestamp.slice(0,10)})\nVous : ${item.user}\nOnyx : ${item.assistant}\n\n`;
                    });
                    appendMessage('onyx', msg);
                } else {
                    appendMessage('onyx', 'Aucun souvenir trouvé.');
                }
                return true;
            }
            if (text.startsWith('/todo')) {
                const task = text.replace('/todo','').trim();
                if (task) {
                    await fetch('/api/todos/add', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId }, body: JSON.stringify({ title: task }) });
                    appendMessage('onyx', `Succès : tâche ajoutée : "${task}"`);
                } else {
                    const res = await fetch('/api/todos', { headers: { 'X-Session-ID': sessionId } });
                    const data = await res.json();
                    if (data.todos && data.todos.length>0) {
                        let list = '**Vos tâches :**\n';
                        data.todos.forEach((t,i) => {
                            list += `${i+1}. ${t.done ? 'Terminée :' : 'À faire :'} ${t.title}\n`;
                        });
                        appendMessage('onyx', list);
                    } else {
                        appendMessage('onyx', 'Aucune tâche en cours.');
                    }
                }
                appendMessage('user', text);
                return true;
            }
            if (text.startsWith('/tot')) {
                const problem = text.replace('/tot', '').trim();
                if (!problem) { appendMessage('onyx', 'Erreur : veuillez fournir un problème à résoudre.'); return true; }
                appendMessage('user', text);
                const res = await fetch('/api/tot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                    body: JSON.stringify({ problem })
                });
                const data = await res.json();
                appendMessage('onyx', data.result || 'Erreur');
                return true;
            }
            // Si aucune commande, on laisse passer pour le chat normal
            return false;
        }

        // --- File upload ---
        fileUploadBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch('/api/upload', {
                method: 'POST',
                headers: { 'X-Session-ID': sessionId },
                body: formData
            });
            const data = await res.json();
            appendMessage('onyx', data.message || (data.success ? 'Succès : fichier téléversé.' : 'Erreur : échec du téléversement.'));
            fileInput.value = '';
        });

        exportBtn.addEventListener('click', async () => {
            if (!currentConvId) { appendMessage('onyx', 'Erreur : aucune conversation en cours.'); return; }
            const res = await fetch('/api/history/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                body: JSON.stringify({ conv_id: currentConvId })
            });
            const data = await res.json();
            if (data.success) {
                const blob = new Blob([data.content], { type: 'text/markdown' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = data.filename;
                a.click();
                appendMessage('onyx', `Conversation exportée : ${data.filename}`);
            } else {
                appendMessage('onyx', `Erreur : ${data.error}`);
            }
        });

        historyBtn.addEventListener('click', async () => {
            historyModal.style.display = 'flex';
            const res = await fetch('/api/history/list', { headers: { 'X-Session-ID': sessionId } });
            const data = await res.json();
            if (data.conversations) {
                historyList.innerHTML = data.conversations.map(conv => `
                    <div style="padding:8px 12px; margin:4px 0; background:var(--glass); border-radius:10px; display:flex; justify-content:space-between; align-items:center;">
                        <span>${conv.title || 'Sans titre'} <span style="font-size:11px; color:var(--text-secondary);">${conv.updated_at ? conv.updated_at.slice(5,16).replace('T',' ') : ''}</span></span>
                        <button onclick="loadConversationFromHistory('${conv.id}')" style="background:var(--accent); border:none; border-radius:6px; padding:4px 12px; color:#fff; cursor:pointer;">Charger</button>
                    </div>
                `).join('');
            } else {
                historyList.innerHTML = '<div style="color:var(--text-secondary);padding:12px;">Aucune conversation.</div>';
            }
        });
        closeHistory.addEventListener('click', () => historyModal.style.display = 'none');
        window.loadConversationFromHistory = async (convId) => {
            await loadConversation(convId);
            historyModal.style.display = 'none';
        };

        // --- Three.js background ---
        const canvas = document.createElement('canvas');
        canvas.style.position = 'fixed';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.zIndex = '-1';
        canvas.style.pointerEvents = 'none';
        document.body.prepend(canvas);
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        const geometry = new THREE.IcosahedronGeometry(1.8, 1);
        const material = new THREE.MeshPhysicalMaterial({
            color: 0x007aff,
            roughness: 0.2,
            metalness: 0.1,
            transparent: true,
            opacity: 0.08
        });
        const orb = new THREE.Mesh(geometry, material);
        scene.add(orb);
        const light = new THREE.PointLight(0x007aff, 0.5);
        light.position.set(2, 3, 4);
        scene.add(light);
        const ambient = new THREE.AmbientLight(0xffffff, 0.1);
        scene.add(ambient);
        camera.position.z = 4;
        function animate() {
            requestAnimationFrame(animate);
            orb.rotation.x += 0.001;
            orb.rotation.y += 0.002;
            renderer.render(scene, camera);
        }
        animate();
        window.addEventListener('resize', () => {
            renderer.setSize(window.innerWidth, window.innerHeight);
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
        });

        sendBtn.addEventListener('click', sendMessage);
        cmdInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        const sidebarSearch = document.getElementById('sidebar-search');
        if (sidebarSearch) {
            sidebarSearch.addEventListener('input', (e) => {
                const filter = e.target.value.toLowerCase();
                document.querySelectorAll('.conv-item').forEach(el => {
                    const title = el.querySelector('.title')?.textContent?.toLowerCase() || '';
                    el.style.display = title.includes(filter) ? 'flex' : 'none';
                });
            });
        }

        // --- Initialize ---
        hydrateOnyxIcons();
        if (userAvatar) userAvatar.textContent = 'O';
        if (userName) userName.textContent = 'Utilisateur';
        loadConversations();
        loadLastConversation();

        // --- Intégration Système Vocal Local (SocketIO & UI) ---
        const socket = io();
        const voicePill = document.getElementById('voice-indicator-pill');
        const voiceStatusText = document.getElementById('voice-status-text');
        const voiceToggleBtn = document.getElementById('voice-toggle-btn');

        const voiceStateLabels = {
            'listening': 'Écoute "hey_jarvis"',
            'wake_detected': 'Mot-clé détecté !',
            'recording': 'Enregistrement...',
            'transcribing': 'Transcription...',
            'thinking': 'Réflexion...',
            'speaking': 'Onyx parle...',
            'paused': 'Micro en pause',
            'idle': 'Vocal inactif'
        };

        function updateVoiceUI(status) {
            if (!voicePill || !voiceStatusText) return;
            voicePill.className = 'voice-pill ' + (status || 'idle');
            voiceStatusText.textContent = voiceStateLabels[status] || status;
            if (voiceToggleBtn) {
                voiceToggleBtn.setAttribute('aria-label', (status === 'paused' || status === 'idle') ? 'Activer le micro' : 'Mettre le micro en pause');
                setOnyxIcon(voiceToggleBtn, (status === 'paused' || status === 'idle') ? 'voice-off' : 'voice', { size: 'sm' });
            }
        }

        socket.on('connect', () => {
            console.log('[SocketIO] Connecté au serveur Onyx V2');
        });

        socket.on('voice_status', (data) => {
            if (data && data.status) {
                updateVoiceUI(data.status);
            }
        });

        socket.on('voice_wake_detected', (data) => {
            updateVoiceUI('wake_detected');
        });

        socket.on('voice_transcription', (data) => {
            if (data && data.text) {
                appendMessage('user', data.text);
            }
        });

        socket.on('voice_response', (data) => {
            if (data && data.response) {
                appendMessage('onyx', 'Réponse vocale : ' + data.response);
            }
        });

        if (voiceToggleBtn) {
            voiceToggleBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                try {
                    const res = await fetch('/api/voice/toggle', { method: 'POST' });
                    const data = await res.json();
                    if (data.success) {
                        updateVoiceUI(data.state);
                    }
                } catch (err) {
                    console.error('[Voice] Erreur toggle:', err);
                }
            });
        }

        // Récupérer le statut initial du système vocal
        fetch('/api/voice/status')
            .then(res => res.json())
            .then(data => {
                if (data.state) updateVoiceUI(data.state);
            })
            .catch(() => {});

        // --- Toast Notifications (Vercel style) ---
        function showToast(message, type = 'info', duration = 3000) {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            const iconName = type === 'success' ? 'success' : type === 'error' ? 'error' : 'info';
            toast.innerHTML = `<span class="toast-icon">${iconMarkup(iconName, { size: 'sm' })}</span><span>${message}</span>`;
            container.appendChild(toast);
            refreshIcons();
            setTimeout(() => {
                toast.classList.add('removing');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }

        // --- Command Palette (Linear / Raycast style) ---
        const cmdPaletteOverlay = document.getElementById('cmd-palette-overlay');
        const cmdPaletteInput = document.querySelector('.cmd-palette-input');
        const cmdPaletteList = document.querySelector('.cmd-palette-list');
        let cmdPaletteIndex = -1;
        const commands = [
            { id: 'new-chat', label: 'Nouvelle conversation', icon: 'new-chat', shortcut: 'Cmd+N', action: () => newConversation() },
            { id: 'export', label: 'Exporter la conversation', icon: 'export', shortcut: 'Cmd+E', action: () => exportBtn.click() },
            { id: 'theme', label: 'Basculer le thème', icon: 'theme-light', shortcut: 'Cmd+D', action: () => themeToggle.click() },
            { id: 'history', label: 'Voir l\'historique', icon: 'history', shortcut: 'Cmd+H', action: () => historyBtn.click() },
            { id: 'clear', label: 'Effacer la conversation', icon: 'delete', shortcut: '', action: () => { if(confirm('Effacer cette conversation ?')) { messages.innerHTML = ''; showToast('Conversation effacée', 'success'); } } },
            { id: 'focus-input', label: 'Focus sur la saisie', icon: 'command', shortcut: 'Cmd+/', action: () => cmdInput.focus() },
            { id: 'voice-toggle', label: 'Activer/Désactiver le micro', icon: 'voice', shortcut: 'Cmd+M', action: () => voiceToggleBtn && voiceToggleBtn.click() },
            { id: 'upload', label: 'Joindre un fichier', icon: 'attach', shortcut: '', action: () => fileUploadBtn.click() },
        ];

        function openCmdPalette() {
            cmdPaletteOverlay.classList.add('open');
            cmdPaletteInput.value = '';
            cmdPaletteIndex = -1;
            renderCmdPalette('');
            setTimeout(() => cmdPaletteInput.focus(), 50);
        }
        function closeCmdPalette() {
            cmdPaletteOverlay.classList.remove('open');
            cmdPaletteIndex = -1;
        }
        function renderCmdPalette(filter) {
            const filtered = commands.filter(c => c.label.toLowerCase().includes(filter.toLowerCase()));
            cmdPaletteList.innerHTML = filtered.map((c, i) => `
                <div class="cmd-palette-item ${i === cmdPaletteIndex ? 'active' : ''}" data-id="${c.id}">
                    <div class="icon">${iconMarkup(c.icon, { size: 'md' })}</div>
                    <span>${c.label}</span>
                    ${c.shortcut ? `<span class="shortcut">${c.shortcut}</span>` : ''}
                </div>
            `).join('');
            refreshIcons();
            cmdPaletteList.querySelectorAll('.cmd-palette-item').forEach(el => {
                el.addEventListener('click', () => {
                    const cmd = commands.find(c => c.id === el.dataset.id);
                    if (cmd) { closeCmdPalette(); cmd.action(); }
                });
            });
        }
        cmdPaletteInput.addEventListener('input', (e) => { cmdPaletteIndex = -1; renderCmdPalette(e.target.value); });
        cmdPaletteInput.addEventListener('keydown', (e) => {
            const items = cmdPaletteList.querySelectorAll('.cmd-palette-item');
            if (e.key === 'ArrowDown') { e.preventDefault(); cmdPaletteIndex = Math.min(cmdPaletteIndex + 1, items.length - 1); items.forEach((it,i) => it.classList.toggle('active', i === cmdPaletteIndex)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); cmdPaletteIndex = Math.max(cmdPaletteIndex - 1, 0); items.forEach((it,i) => it.classList.toggle('active', i === cmdPaletteIndex)); }
            else if (e.key === 'Enter') { e.preventDefault(); if (items[cmdPaletteIndex]) items[cmdPaletteIndex].click(); }
            else if (e.key === 'Escape') { closeCmdPalette(); }
        });
        cmdPaletteOverlay.addEventListener('click', (e) => { if (e.target === cmdPaletteOverlay) closeCmdPalette(); });

        // --- Keyboard Shortcuts (Superhuman style) ---
        document.addEventListener('keydown', (e) => {
            const mod = e.metaKey || e.ctrlKey;
            if (mod && e.key === 'k') { e.preventDefault(); openCmdPalette(); }
            else if (mod && e.key === 'n') { e.preventDefault(); newConversation(); showToast('Nouvelle conversation', 'success'); }
            else if (mod && e.key === 'e') { e.preventDefault(); exportBtn.click(); }
            else if (mod && e.key === 'd') { e.preventDefault(); themeToggle.click(); }
            else if (mod && e.key === 'h') { e.preventDefault(); historyBtn.click(); }
            else if (mod && e.key === '/') { e.preventDefault(); cmdInput.focus(); }
            else if (mod && e.key === 'm') { e.preventDefault(); if (voiceToggleBtn) voiceToggleBtn.click(); }
            else if (e.key === 'Escape') { closeCmdPalette(); historyModal.style.display = 'none'; }
        });

        // --- Quick Actions ---
        document.querySelectorAll('.quick-action-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const action = chip.dataset.action;
                if (action === 'new-chat') { newConversation(); showToast('Nouvelle conversation', 'success'); }
                else if (action === 'export') { exportBtn.click(); }
                else if (action === 'theme') { themeToggle.click(); }
                else if (action === 'palette') { openCmdPalette(); }
            });
        });

        // --- Improved Message Rendering ---
        async function copyMessage(btn) {
            const msgDiv = btn.closest('.msg');
            const text = msgDiv.innerText || msgDiv.textContent;
            try {
                await navigator.clipboard.writeText(text);
                btn.classList.add('copied');
                btn.innerHTML = iconMarkup('check', { size: 'sm' });
                setTimeout(() => {
                    btn.classList.remove('copied');
                    btn.innerHTML = iconMarkup('copy', { size: 'sm' });
                    refreshIcons();
                }, 1500);
            } catch (e) {
                console.error('Copy failed:', e);
            }
        }

        function resetTextarea() {
            cmdInput.value = '';
            cmdInput.rows = 1;
        }

        function autoResize() {
            cmdInput.style.height = 'auto';
            cmdInput.style.height = Math.min(cmdInput.scrollHeight, 160) + 'px';
        }

        function quickPrompt(text) {
            cmdInput.value = text;
            autoResize();
            sendMessage();
        }

        function insertEmoji(emoji) {
            const start = cmdInput.selectionStart;
            const end = cmdInput.selectionEnd;
            const value = cmdInput.value;
            cmdInput.value = value.substring(0, start) + emoji + value.substring(end);
            autoResize();
            cmdInput.focus();
            cmdInput.setSelectionRange(start + emoji.length, start + emoji.length);
        }

        function toggleEmojiPicker() {
            emojiOpen = !emojiOpen;
            if (emojiPicker) {
                emojiPicker.classList.toggle('show', emojiOpen);
                if (emojiOpen) {
                    refreshIcons();
                }
            }
        }

        function updateNotifBadge(count) {
            notifCount = count;
            if (notifBadge) {
                if (count > 0) {
                    notifBadge.textContent = count > 99 ? '99+' : count;
                    notifBtn?.classList.add('has-notif');
                } else {
                    notifBadge.textContent = '';
                    notifBtn?.classList.remove('has-notif');
                }
            }
        }

        async function loadNotifications() {
            if (!sessionId) return;
            try {
                const res = await fetch('/api/notifications', { headers: { 'X-Session-ID': sessionId } });
                const data = await res.json();
                if (notifList) {
                    const notifs = data.notifications || [];
                    const unread = notifs.filter(n => !n.read);
                    updateNotifBadge(unread.length);
                    notifList.innerHTML = notifs.map(n => `
                        <div class="notif-item ${n.read ? '' : 'unread'}" onclick="handleNotifClick('${n.id}')">
                            <div class="notif-title">${n.title}</div>
                            <div class="notif-msg">${n.message}</div>
                            <div class="notif-time">${n.timestamp ? n.timestamp.slice(0,10) : ''}</div>
                        </div>
                    `).join('') || '<div style="padding:16px;text-align:center;color:var(--text-secondary);">Aucune notification</div>';
                }
            } catch (e) {
                console.error('[Notif] Erreur:', e);
            }
        }

        function toggleNotifPanel() {
            notifPanel?.classList.toggle('show');
            if (notifPanel?.classList.contains('show')) {
                loadNotifications();
            }
        }

        async function handleNotifClick(notifId) {
            try {
                await fetch('/api/notifications/mark_read', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                    body: JSON.stringify({ notif_id: notifId })
                });
            } catch (e) { console.error(e); }
            loadNotifications();
        }

        async function clearAllNotifications() {
            try {
                const res = await fetch('/api/notifications/clear', { method: 'POST', headers: { 'X-Session-ID': sessionId } });
                const data = await res.json();
                showToast(data.message || 'Notifications effacées', 'success');
                updateNotifBadge(0);
                notifList.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-secondary);">Aucune notification</div>';
            } catch (e) {
                console.error('[Notif] Erreur clear:', e);
            }
        }

        function openSettings() {
            settingsModal?.classList.add('show');
            fetch('/api/settings', { headers: { 'X-Session-ID': sessionId } }).then(r => r.ok ? r.json() : null).then(data => {
                const s = data?.settings || {};
                if (settingSerper && s.serper_key !== undefined) settingSerper.value = s.serper_key === '••••••••' ? '' : s.serper_key;
                if (settingLanguage) settingLanguage.value = s.language || localStorage.getItem('onyx_language') || 'fr';
                if (settingDarkMode) settingDarkMode.checked = (s.theme || (isDark ? 'dark' : 'light')) !== 'light';
                if (settingCloudSync) settingCloudSync.checked = !!s.cloud_sync;
                if (settingVoice) settingVoice.checked = s.voice_enabled !== false;
                if (settingCompactMemory) settingCompactMemory.checked = s.compact_memory !== false;
                if (settingModel) settingModel.value = s.model || 'qwen2.5-7b-instruct';
                if (settingTemperature) { settingTemperature.value = s.temperature ?? 0.3; if (settingTemperatureValue) settingTemperatureValue.textContent = settingTemperature.value; }
                if (settingMaxTokens) settingMaxTokens.value = s.max_tokens || 1024;
                if (settingTimeout) settingTimeout.value = s.request_timeout || 120;
            }).catch(() => {});
        }

        function closeSettings() {
            settingsModal?.classList.remove('show');
        }

        async function saveSettings() {
            if (settingSerper) localStorage.setItem('serperKey', settingSerper.value);
            if (settingLanguage) {
                localStorage.setItem('onyx_language', settingLanguage.value);
            }
            if (settingDarkMode) {
                const dark = settingDarkMode.checked;
                isDark = dark;
                document.body.classList.toggle('light-mode', !dark);
                setOnyxIcon(themeToggle, dark ? 'theme-dark' : 'theme-light', { size: 'lg' });
                localStorage.setItem('onyx_dark_mode', dark ? 'true' : 'false');
            }
            if (settingCloudSync) localStorage.setItem('onyx_cloud_sync', settingCloudSync.checked ? 'true' : 'false');
            if (settingVoice) localStorage.setItem('onyx_voice', settingVoice.checked ? 'true' : 'false');
            const settings = {
                serper_key: settingSerper?.value || '', language: settingLanguage?.value || 'fr',
                theme: settingDarkMode?.checked ? 'dark' : 'light', cloud_sync: !!settingCloudSync?.checked,
                voice_enabled: settingVoice?.checked !== false, compact_memory: settingCompactMemory?.checked !== false,
                model: settingModel?.value || 'qwen2.5-7b-instruct', temperature: Number(settingTemperature?.value || 0.3),
                max_tokens: Number(settingMaxTokens?.value || 1024), request_timeout: Number(settingTimeout?.value || 120)
            };
            try { await fetch('/api/settings', { method:'PUT', headers:{'Content-Type':'application/json','X-Session-ID':sessionId}, body:JSON.stringify({settings}) }); } catch (e) { console.warn('Paramètres non synchronisés', e); }
            closeSettings();
            showToast('Paramètres enregistrés', 'success');
        }

        function setupToggle(toggleId) {
            const cb = document.getElementById(toggleId);
            if (!cb) return;
            const track = cb.closest('.toggle-switch')?.querySelector('span');
            if (!track) return;
            const updateToggle = () => {
                track.style.background = cb.checked ? 'var(--accent)' : 'var(--glass)';
                track.style.transform = cb.checked ? 'translateX(20px)' : 'translateX(0)';
                track.style.background = cb.checked ? 'var(--accent)' : 'var(--glass)';
            };
            cb.addEventListener('change', updateToggle);
            updateToggle();
        }

        function checkScrollPosition() {
            if (!messages || !scrollToBottomBtn) return;
            const scrollTop = messages.scrollTop;
            const scrollBottom = messages.scrollHeight - messages.clientHeight - scrollTop;
            if (scrollBottom > 60) {
                scrollToBottomBtn.classList.add('show');
            } else {
                scrollToBottomBtn.classList.remove('show');
            }
        }

        function appendMessage(sender, text, save = true) {
            const emptyState = document.getElementById('empty-state');
            if (emptyState) emptyState.classList.remove('visible');
            const div = document.createElement('div');
            div.className = `msg ${sender}`;
            div.innerHTML = buildMessageMarkup(sender, text);
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
            refreshIcons();
            return div;
        }

        async function sendMessage() {
            const text = cmdInput.value.trim();
            if (!text) return;
            const handled = await handleCommand(text);
            if (handled) return;
            cmdInput.value = '';
            resetTextarea();

            appendMessage('user', text);
            const loadingEl = appendMessage('onyx', '<div class="typing-indicator"><span></span><span></span><span></span></div> Réflexion en cours...');

            try {
                const selectedLang = settingLanguage ? settingLanguage.value : (localStorage.getItem('onyx_language') || 'fr');
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
                    body: JSON.stringify({
                        prompt: text,
                        language: selectedLang || 'fr',
                        doc_mode: docMode,
                        conv_id: currentConvId,
                        settings: {
                            serper_key: localStorage.getItem('serperKey') || '',
                            model: settingModel?.value || 'qwen2.5-7b-instruct',
                            temperature: Number(settingTemperature?.value || 0.3),
                            max_tokens: Number(settingMaxTokens?.value || 1024),
                            request_timeout: Number(settingTimeout?.value || 120),
                            compact_memory: settingCompactMemory?.checked !== false
                        }
                    })
                });
                const data = await res.json();
                if (data.sentiment) {
                    const pill = document.getElementById('sentiment-pill');
                    const label = document.getElementById('sentiment-label');
                    if (pill && label) {
                        pill.classList.toggle('active', data.sentiment.label !== 'neutral');
                        pill.firstChild.textContent = `${data.sentiment.emoji || '◌'} `;
                        label.textContent = data.sentiment.name || 'Neutre';
                        pill.title = `Humeur détectée : ${data.sentiment.name || 'Neutre'} — le ton d'Onyx s'adapte.`;
                    }
                }
                if (loadingEl) {
                    loadingEl.innerHTML = buildMessageMarkup('onyx', data.response);
                    if (data.model_used) {
                        loadingEl.innerHTML += `<div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;">` +
                            (data.web_used ? `<span class="kbd-hint">Web</span>` : '') +
                            (data.file_used ? `<span class="kbd-hint">Fichier</span>` : '') +
                            `<span class="kbd-hint">${data.model_used}</span></div>`;
                    }
                    if (data.conv_id) await loadConversations();
                    refreshIcons();
                }
                showToast('Réponse reçue', 'success', 2000);
            } catch (err) {
                if (loadingEl) loadingEl.innerHTML = buildMessageMarkup('onyx', 'Erreur serveur.');
                showToast('Erreur de connexion', 'error');
                console.error(err);
            }
        }

        // --- Initialize ---
        hydrateOnyxIcons();
        if (settingDarkMode) setupToggle('setting-dark-mode');
        if (settingCloudSync) setupToggle('setting-cloud-sync');
        if (settingVoice) setupToggle('setting-voice');
        if (settingCompactMemory) setupToggle('setting-compact-memory');
        settingTemperature?.addEventListener('input', () => { if (settingTemperatureValue) settingTemperatureValue.textContent = settingTemperature.value; });

        notifBtn?.addEventListener('click', toggleNotifPanel);
        settingsBtn?.addEventListener('click', openSettings);
        if (settingsCancel) settingsCancel.addEventListener('click', closeSettings);
        if (settingsClose) settingsClose.addEventListener('click', closeSettings);
        if (settingsSave) settingsSave.addEventListener('click', saveSettings);
        if (settingsModal) settingsModal.addEventListener('click', (e) => { if (e.target === settingsModal) closeSettings(); });
        if (notifClearAll) notifClearAll.addEventListener('click', clearAllNotifications);
        if (emojiToggle) emojiToggle.addEventListener('click', (e) => { e.stopPropagation(); toggleEmojiPicker(); });
        document.addEventListener('click', (e) => { if (emojiOpen && !emojiPicker?.contains(e.target) && e.target !== emojiToggle) { emojiOpen = false; emojiPicker?.classList.remove('show'); } });
        if (scrollToBottomBtn) scrollToBottomBtn.addEventListener('click', () => { messages.scrollTop = messages.scrollHeight; });
        if (messages) messages.addEventListener('scroll', checkScrollPosition);
        if (cmdInput) cmdInput.addEventListener('input', autoResize);
        if (cmdInput) cmdInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
        });

        if (sessionId) {
            fetch('/api/me', { headers: { 'X-Session-ID': sessionId } })
                .then(res => {
                    if (res.ok) return res.json();
                    else throw new Error('Invalid session');
                })
                .then(data => {
                    username = data.username;
                    userAvatar.textContent = username[0].toUpperCase();
                    userName.textContent = username;
                    hideLogin();
                    loadConversations();
                    loadLastConversation();
                    loadNotifications();
                    setInterval(loadNotifications, 15000);
                })
                .catch(() => { showLogin(); });
        } else {
            showLogin();
        }
    </script>
</body>
</html>
</body>
</html>
"""

# ============================================================
# 17. ROUTES (TOUTES)
# ============================================================
@app.route("/")
def index():
    return render_template_string(ONYX_UI_HTML)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not create_user(username, password):
        return jsonify({"success": False, "message": "Identifiant déjà utilisé ou données invalides"}), 400
    return jsonify({"success": True}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not authenticate_user(username, password):
        return jsonify({"success": False, "message": "Identifiants invalides"}), 401
    session_id = create_session(username)
    return jsonify({"success": True, "session_id": session_id, "username": _find_username_key(load_users(), username)})

@app.route('/api/me', methods=['GET'])
def me():
    username = validate_session(request.headers.get("X-Session-ID"))
    if not username:
        return jsonify({"error": "Authentification requise"}), 401
    return jsonify({"username": username, "anonymous": False})

@app.route('/api/settings', methods=['GET', 'PUT'])
def user_settings_route():
    """Lit ou met à jour les paramètres de l'utilisateur connecté."""
    username = validate_session(request.headers.get('X-Session-ID'))
    if not username:
        return jsonify({"error": "Authentification requise"}), 401
    user_data = get_user_data(username) or {}
    current = normalize_user_settings(user_data.get("preferences", {}))
    if request.method == 'GET':
        # Ne jamais renvoyer une clé secrète au navigateur après sauvegarde.
        safe = dict(current)
        safe["serper_key"] = "••••••••" if safe["serper_key"] else ""
        return jsonify({"settings": safe})
    payload = request.get_json(silent=True) or {}
    incoming = dict(current)
    incoming.update(payload.get("settings", payload))
    normalized = normalize_user_settings(incoming)
    if normalized["serper_key"] == "••••••••":
        normalized["serper_key"] = current["serper_key"]
    user_data["preferences"] = normalized
    save_user_data(username, user_data)
    return jsonify({"success": True, "settings": {**normalized, "serper_key": "••••••••" if normalized["serper_key"] else ""}})

@app.route('/api/logout', methods=['POST'])
def logout():
    session_id = request.headers.get("X-Session-ID")
    users = load_users()
    for user in users.values():
        user["sessions"] = [s for s in user.get("sessions", []) if (s.get("id") if isinstance(s, dict) else s) != session_id]
    save_users(users)
    return jsonify({"success": True})

# --- Historique ---
@app.route('/api/history/list', methods=['GET'])
def history_list():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    conversations = load_history(username)
    return jsonify({"conversations": conversations})

@app.route('/api/history/last', methods=['GET'])
def history_last():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    conversations = load_history(username)
    if conversations:
        convs = sorted(conversations, key=lambda x: x.get("updated_at", ""), reverse=True)
        return jsonify({"conversation": convs[0]})
    return jsonify({"conversation": None})

@app.route('/api/history/search', methods=['GET'])
def history_search():
    username = validate_session(request.headers.get('X-Session-ID'))
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    query = request.args.get('q', '').strip()
    if not query or len(query) > 200:
        return jsonify({"error": "Requête de recherche invalide"}), 400
    try:
        results = onyx_storage.search_messages(
            username, query, limit=request.args.get('limit', 50), offset=request.args.get('offset', 0)
        )
    except (ValueError, TypeError):
        return jsonify({"error": "Pagination invalide"}), 400
    return jsonify({"results": results})

@app.route('/api/history/load', methods=['POST'])
def history_load():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    conv_id = data.get('conv_id')
    if not conv_id:
        return jsonify({"error": "conv_id manquant"}), 400
    conv = get_current_conversation(username, conv_id)
    if conv:
        return jsonify({"messages": conv.get("messages", [])})
    return jsonify({"messages": []}), 404

@app.route('/api/history/new', methods=['POST'])
def history_new():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    conv_id = create_conversation_id()
    update_conversation(username, conv_id, [], "Nouvelle conversation")
    return jsonify({"conv_id": conv_id})

@app.route('/api/history/delete', methods=['POST'])
def history_delete():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    conv_id = data.get('conv_id')
    if not conv_id:
        return jsonify({"error": "conv_id manquant"}), 400
    delete_conversation(username, conv_id)
    return jsonify({"success": True})

@app.route('/api/history/export', methods=['POST'])
def history_export():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    conv_id = data.get('conv_id')
    if not conv_id:
        return jsonify({"error": "conv_id manquant"}), 400
    conv = get_current_conversation(username, conv_id)
    if not conv:
        return jsonify({"error": "Conversation non trouvée"}), 404
    messages = conv.get("messages", [])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"onyx_conversation_{conv_id}_{timestamp}.md"
    lines = [f"# {conv.get('title', 'Conversation')}\n"]
    lines.append(f"*Exporté le {datetime.now().isoformat()}*\n\n")
    for msg in messages:
        role = msg.get('role', 'unknown').upper()
        content = msg.get('content', '')
        lines.append(f"## {role}\n{content}\n")
    content = "\n".join(lines)
    return jsonify({"success": True, "content": content, "filename": filename})

# --- Upload ---
@app.route('/api/upload', methods=['POST'])
def upload_file():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    if 'file' not in request.files:
        return jsonify({"error": "Aucun fichier"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nom vide"}), 400
    allowed = ['.txt','.py','.js','.html','.css','.json','.csv','.md','.xml','.yml','.yaml','.log','.sql','.c','.cpp','.h','.java','.go','.rs','.sh','.bat','.ps1','.ini','.cfg','.conf','.toml']
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"error": "Type de fichier non supporté"}), 400
    content = file.read().decode('utf-8', errors='replace')
    if len(content) > 3000:
        summary = call_qwen_deep(f"Résume ce texte en 200 mots :\n{content[:5000]}", "Tu es un assistant de résumé.", max_tokens=512)
        if summary:
            content = f"RÉSUMÉ DU FICHIER ({file.filename}) :\n{summary}\n\n--- FIN DU RÉSUMÉ ---"
        else:
            content = content[:3000] + "\n... (tronqué)"
    user_data = get_user_storage(username)
    if user_data:
        user_data["files"].append({
            "filename": file.filename,
            "content": content,
            "timestamp": time.time()
        })
        save_users(load_users())
    return jsonify({"success": True, "message": f"Fichier {file.filename} uploadé"})

# --- Mode veille ---
@app.route('/api/monitor/start', methods=['POST'])
def monitor_start():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    filepath = data.get('filepath')
    resolved_filepath = os.path.realpath(filepath) if filepath else ""
    if (not filepath or not os.path.exists(resolved_filepath) or
            os.path.commonpath([resolved_filepath, os.path.realpath(BASE_DIR)]) != os.path.realpath(BASE_DIR)):
        return jsonify({"error": "Chemin invalide"}), 400
    if session_id in monitors:
        monitors[session_id].stop()
    def callback(path, content):
        on_file_change(session_id, path, content)
    monitor = FileMonitor(callback)
    monitor.add_file(resolved_filepath)
    monitor.start(interval=15)
    monitors[session_id] = monitor
    return jsonify({"success": True})

@app.route('/api/monitor/stop', methods=['POST'])
def monitor_stop():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    if session_id in monitors:
        monitors[session_id].stop()
        del monitors[session_id]
        return jsonify({"success": True})
    return jsonify({"error": "Aucune surveillance active"}), 404

# --- API externes ---
@app.route('/api/weather', methods=['POST'])
def weather_api():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    city = data.get('city', 'Paris')
    result = get_weather(city)
    if result.get("success"):
        message = f"Météo à {result['city']}: {result['temp']}°C, {result['description']}, humidité {result['humidity']}%, vent {result['wind_speed']} m/s"
        return jsonify({"message": message})
    else:
        return jsonify({"message": f"Erreur : {result.get('error', 'Erreur inconnue')}"})

@app.route('/api/news', methods=['POST'])
def news_api():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    query = data.get('query', 'actualités')
    articles = get_news(query=query, max_results=5)
    return jsonify({"articles": articles})

@app.route('/api/email/send', methods=['POST'])
def email_send():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    to = data.get('to')
    subject = data.get('subject')
    body = data.get('body')
    if not all([to, subject, body]):
        return jsonify({"error": "Paramètres manquants"}), 400
    result = send_email(to, subject, body)
    return jsonify(result)

@app.route('/api/email/read', methods=['POST'])
def email_read():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    limit = data.get('limit', 5)
    unread_only = data.get('unread_only', True)
    result = read_emails(limit=limit, unread_only=unread_only)
    return jsonify(result)

# --- Commandes système standard ---
@app.route('/api/command', methods=['POST'])
def command_endpoint():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    command = data.get('command', '').strip()
    confirm = data.get('confirm', False)
    simulate = bool(data.get('simulate', False))
    if not command:
        return jsonify({"error": "Commande vide"}), 400
    cmd_base = command.split()[0].lower() if command else ""
    if cmd_base not in ALLOWED_COMMANDS:
        return jsonify({"success": False, "stderr": f"Commande non autorisée : {cmd_base}"})
    is_sensitive = any(sens in command.lower() for sens in SENSITIVE_COMMANDS)
    if is_sensitive and not confirm:
        return jsonify({"success": False, "simulation": True, "error": "Confirmation explicite requise"}), 400
    if simulate:
        return jsonify({"success": True, "simulation": True, "command": command, "message": "Action autorisée mais non exécutée"})
    result = execute_system_command(command)
    if result["success"]:
        add_notification(username, "Commande exécutée", f"Commande : {command}", level="info")
        return jsonify({"success": True, "stdout": result["stdout"], "stderr": result["stderr"]})
    else:
        return jsonify({"success": False, "stderr": result["stderr"]}), 500

# --- Tâches ---
@app.route('/api/tasks', methods=['GET'])
def get_tasks_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    filter_done = request.args.get('done', 'false').lower() == 'true'
    tasks = get_tasks(username, filter_done)
    return jsonify({"tasks": tasks})

@app.route('/api/tasks/add', methods=['POST'])
def add_task_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    title = data.get('title', '').strip()
    due_date_str = data.get('due_date')
    description = data.get('description', '')
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.fromisoformat(due_date_str)
        except:
            pass
    if not title:
        return jsonify({"error": "Titre requis"}), 400
    result = add_task(username, title, due_date, description)
    if result.get("success"):
        return jsonify({"success": True, "task": result["task"]})
    else:
        return jsonify({"error": result.get("error")}), 500

@app.route('/api/tasks/toggle', methods=['POST'])
def toggle_task_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({"error": "task_id manquant"}), 400
    result = toggle_task(username, task_id)
    if result.get("success"):
        return jsonify({"success": True, "task": result["task"]})
    else:
        return jsonify({"error": result.get("error")}), 404

@app.route('/api/tasks/delete', methods=['POST'])
def delete_task_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({"error": "task_id manquant"}), 400
    result = delete_task(username, task_id)
    if result.get("success"):
        return jsonify({"success": True})
    else:
        return jsonify({"error": result.get("error")}), 404

# --- Notifications ---
@app.route('/api/notifications', methods=['GET'])
def get_notifications_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    unread_only = request.args.get('unread', 'false').lower() == 'true'
    notifs = get_notifications(username, unread_only)
    return jsonify({"notifications": notifs})

@app.route('/api/notifications/mark_read', methods=['POST'])
def mark_notification_read_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    notif_id = data.get('notif_id')
    if not notif_id:
        return jsonify({"error": "notif_id manquant"}), 400
    mark_notification_read(username, notif_id)
    return jsonify({"success": True})

# --- LTM ---
@app.route('/api/ltm/search', methods=['POST'])
def ltm_search_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    query = data.get('query', '').strip()
    if not query:
        return jsonify({"error": "Requête vide"}), 400
    results = search_ltm_simple(username, query, limit=5)
    return jsonify({"results": results})

# --- Memory Management ---
@app.route('/api/memory/stats', methods=['GET'])
def memory_stats_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    if memory_manager:
        stats = memory_manager.get_memory_stats(username)
    else:
        stats = {"error": "MemoryManager non disponible"}
    return jsonify({"success": True, "stats": stats})

@app.route('/api/memory/consolidate', methods=['POST'])
def consolidate_memory_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json or {}
    conv_id = data.get('conv_id', '')
    if memory_manager and conv_id:
        conv = get_current_conversation(username, conv_id)
        if conv and conv.get("messages"):
            entry = memory_manager.consolidate_to_ltm(
                username=username,
                conv_id=conv_id,
                conversation_messages=conv.get("messages", []),
                importance_threshold=0.2
            )
            return jsonify({"success": True, "consolidated": entry is not None})
    return jsonify({"success": False, "error": "Aucune conversation à consolider"})

@app.route('/api/memory/clear_stm', methods=['POST'])
def clear_stm_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    if memory_manager:
        memory_manager.reset_stm(username)
        return jsonify({"success": True, "message": "STM vidée"})
    return jsonify({"success": False, "error": "MemoryManager non disponible"})

@app.route('/api/memory/facts', methods=['GET'])
def memory_facts_route():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    if memory_manager:
        facts = memory_manager.get_user_facts(username)
    else:
        facts = []
    return jsonify({"success": True, "facts": facts})

# --- Export simple ---
@app.route('/api/export', methods=['POST'])
def export_conversation_simple():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    user_data = get_user_storage(username)
    if not user_data:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    history = user_data.get("history", [])
    if not history:
        return jsonify({"error": "Aucun message"}), 400
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"onyx_conversation_{timestamp}.md"
    lines = [f"# Onyx Conversation - {timestamp}\n"]
    for entry in history:
        lines.append(f"## {entry.get('role', 'unknown').upper()}\n{entry.get('content', '')}\n")
    content = "\n".join(lines)
    return jsonify({"success": True, "content": content, "filename": filename})

# --- Autres (CORRIGÉS) ---
@app.route('/api/files/lint', methods=['POST'])
def lint_endpoint():
    try:
        with open(__file__, 'r', encoding='utf-8') as f:
            code = f.read()
        ast.parse(code)
        return jsonify({"status": "ok"})
    except SyntaxError as e:
        return jsonify({"status": "error", "error": e.msg, "line": e.lineno})
    except Exception:
        logger.exception("Lint endpoint failed")
        return jsonify({"status": "error", "error": "Analyse indisponible", "line": 0})

@app.route('/api/network/fetch', methods=['POST'])
def network_fetch_endpoint():
    if not validate_session(request.headers.get('X-Session-ID')):
        return jsonify({"error": "Authentification requise"}), 401
    data = request.json or {}
    query = data.get('query', '').strip()
    if len(query) > 4000:
        return jsonify({"error": "Requête trop longue"}), 413
    serper_key = data.get('serperKey', '')
    if not query:
        return jsonify({"result": "Requête vide."})
    results = fetch_web_context(query, serper_key=serper_key)
    return jsonify({"result": results or "Aucun résultat."})

@app.route('/api/execute', methods=['POST'])
def execute_endpoint():
    if not validate_session(request.headers.get('X-Session-ID')):
        return jsonify({"error": "Authentification requise"}), 401
    data = request.json or {}
    code = data.get('code', '').strip()
    if not code:
        return jsonify({"error": "Code vide"}), 400
    if len(code) > MAX_CODE_LENGTH:
        return jsonify({"error": "Code trop volumineux"}), 413
    if not data.get("confirm", False):
        return jsonify({"success": False, "simulation": True, "message": "Confirmation explicite requise avant exécution"})
    result = execute_python_sandbox(code, timeout=15)
    return jsonify(result)

# ============================================================
# 18. SYNCHRONISATION INTER-APPAREILS (WebSockets)
# ============================================================
@socketio.on('connect')
def handle_connect():
    print('Client connecté')

@socketio.on('clipboard_sync')
def handle_clipboard_sync(data):
    username = validate_session(data.get('session_id'))
    if username:
        user_data = get_user_storage(username)
        if user_data:
            user_data['clipboard'] = data.get('content', '')
            save_users(load_users())
            emit('clipboard_update', {'content': data.get('content', '')}, broadcast=True)

@socketio.on('file_transfer')
def handle_file_transfer(data):
    username = validate_session(data.get('session_id'))
    if username:
        file_data = data.get('file')
        filename = data.get('filename')
        if file_data and filename:
            safe_name = secure_filename(str(filename))
            shared_dir = os.path.join(BASE_DIR, 'shared', username)
            if not safe_name or safe_name != os.path.basename(str(filename)):
                return
            filepath = os.path.join(shared_dir, safe_name)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'wb') as f:
                f.write(file_data)
            emit('file_received', {'filename': filename, 'status': 'ok'})

# ============================================================
# 19. NOUVELLES ROUTES PHASE 4
# ============================================================
@app.route('/api/clipboard', methods=['GET'])
def get_clipboard():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    user_data = get_user_storage(username)
    if user_data:
        return jsonify({"clipboard": user_data.get('clipboard', '')})
    return jsonify({"clipboard": ""})

@app.route('/api/clipboard', methods=['POST'])
def set_clipboard():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    content = data.get('content', '')
    user_data = get_user_storage(username)
    if user_data:
        user_data['clipboard'] = content
        save_users(load_users())
        socketio.emit('clipboard_update', {'content': content}, broadcast=True)
        return jsonify({"success": True})
    return jsonify({"error": "Utilisateur non trouvé"}), 404

@app.route('/api/upload_shared', methods=['POST'])
def upload_shared_file():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    if 'file' not in request.files:
        return jsonify({"error": "Aucun fichier"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nom vide"}), 400
    safe_name = secure_filename(file.filename)
    if not safe_name or safe_name != os.path.basename(safe_name):
        return jsonify({"error": "Nom de fichier invalide"}), 400
    shared_dir = os.path.join(BASE_DIR, 'shared', username)
    os.makedirs(shared_dir, exist_ok=True)
    filepath = os.path.join(shared_dir, safe_name)
    file.save(filepath)
    socketio.emit('file_received', {'filename': file.filename, 'path': filepath}, broadcast=True)
    return jsonify({"success": True, "filename": safe_name})

@app.route('/api/shared_files', methods=['GET'])
def list_shared_files():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    shared_dir = os.path.join('shared', username)
    if not os.path.exists(shared_dir):
        return jsonify({"files": []})
    files = [f for f in os.listdir(shared_dir) if os.path.isfile(os.path.join(shared_dir, f))]
    return jsonify({"files": files})

@app.route('/api/download_shared/<filename>', methods=['GET'])
def download_shared_file(filename):
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    safe_name = secure_filename(filename)
    shared_dir = os.path.join(BASE_DIR, 'shared', username)
    filepath = os.path.realpath(os.path.join(shared_dir, safe_name))
    if safe_name != os.path.basename(filename) or os.path.commonpath([filepath, os.path.realpath(shared_dir)]) != os.path.realpath(shared_dir):
        return jsonify({"error": "Nom de fichier invalide"}), 400
    if not os.path.exists(filepath):
        return jsonify({"error": "Fichier non trouvé"}), 404
    return send_file(filepath, as_attachment=True)

@app.route('/api/tot', methods=['POST'])
def tree_of_thoughts_endpoint():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    problem = data.get('problem', '').strip()
    if not problem:
        return jsonify({"error": "Problème vide"}), 400
    result = tree_of_thoughts(problem)
    return jsonify({"result": result})

# Orchestrator pour les agents (instance globale)
orchestrator = MultiAgentOrchestrator()

@app.route('/api/agent', methods=['POST'])
def agent_endpoint():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    task = data.get('task', '').strip()
    if not task:
        return jsonify({"error": "Tâche vide"}), 400
    context = data.get('context', {})
    result = orchestrator.execute_task(task, context)
    if result is None:
        return jsonify({"fallback": True, "message": "Requête redirigée vers le chat standard"})
    else:
        return jsonify(result)

# --- Système (contrôle avancé) ---
@app.route('/api/system/lock', methods=['POST'])
def lock_pc():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    try:
        if IS_WINDOWS:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
            return jsonify({"message": "PC verrouillé"})
        else:
            return jsonify({"error": "Non supporté"}), 400
    except Exception:
        logger.exception("System lock failed")
        return jsonify({"error": "Action système impossible"}), 500

@app.route('/api/system/sleep', methods=['POST'])
def sleep_pc():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    try:
        if IS_WINDOWS:
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"], check=True)
            return jsonify({"message": "Mise en veille"})
        else:
            return jsonify({"error": "Non supporté"}), 400
    except Exception:
        logger.exception("System sleep failed")
        return jsonify({"error": "Action système impossible"}), 500

@app.route('/api/system/restart', methods=['POST'])
def restart_pc():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    try:
        if IS_WINDOWS:
            subprocess.run(["shutdown", "/r", "/t", "5"], check=True)
            return jsonify({"message": "Redémarrage dans 5 secondes"})
        else:
            return jsonify({"error": "Non supporté"}), 400
    except Exception:
        logger.exception("System restart failed")
        return jsonify({"error": "Action système impossible"}), 500

@app.route('/api/system/volume', methods=['POST'])
def set_volume():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    level = data.get('level', 50)
    agent = SystemAgent()
    result = agent._set_volume("+", level) if level > 0 else agent._set_volume("-", 0)
    return jsonify({"message": result.get('output', 'Volume réglé')})

@app.route('/api/system/brightness', methods=['POST'])
def set_brightness():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    level = data.get('level', 50)
    agent = SystemAgent()
    result = agent._set_brightness(level)
    return jsonify({"message": result.get('output', 'Luminosité réglée')})

@app.route('/api/system/status', methods=['GET'])
def system_status():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    agent = SystemAgent()
    result = agent._get_system_status()
    return jsonify({"message": result.get('output', 'Statut non disponible')})

@app.route('/api/system/launch', methods=['POST'])
def launch_app():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    app_name = data.get('app_name', '').strip()
    if not app_name:
        return jsonify({"error": "Nom d'application requis"}), 400
    try:
        if IS_WINDOWS:
            os.startfile(app_name)
            return jsonify({"message": f"Lancement de {app_name}"})
        else:
            subprocess.Popen([app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return jsonify({"message": f"Lancement de {app_name}"})
    except Exception:
        logger.exception("System launch failed")
        return jsonify({"error": "Lancement impossible"}), 500

@app.route('/api/system/script', methods=['POST'])
def run_script():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)
    if not username:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.json
    script_path = data.get('script_path', '').strip()
    if not script_path:
        return jsonify({"error": "Chemin de script requis"}), 400
    script_root = os.path.realpath(os.path.join(BASE_DIR, "scripts"))
    resolved_script = os.path.realpath(script_path)
    if os.path.commonpath([resolved_script, script_root]) != script_root:
        return jsonify({"error": "Script non autorisé"}), 403
    if not os.path.exists(resolved_script) or not os.path.isfile(resolved_script):
        return jsonify({"error": "Script non trouvé"}), 404
    if not data.get("confirm", False):
        return jsonify({"success": False, "simulation": True, "message": "Confirmation explicite requise"}), 400
    try:
        if resolved_script.endswith('.py'):
            result = subprocess.run([sys.executable, resolved_script], capture_output=True, text=True, timeout=60)
        else:
            result = subprocess.run([resolved_script], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return jsonify({"output": result.stdout})
        else:
            return jsonify({"output": result.stderr, "error": "Erreur d'exécution"}), 500
    except (subprocess.SubprocessError, OSError):
        logger.exception("Script execution failed")
        return jsonify({"error": "Échec de l'exécution du script"}), 500

# ============================================================
# 19.B API DU SYSTÈME VOCAL (openwakeword, sounddevice, faster-whisper, pyttsx3, scipy)
# ============================================================
@app.route('/api/voice/status', methods=['GET'])
def get_voice_status():
    """Retourne l'état actuel du système vocal."""
    return jsonify({
        "success": True,
        "state": voice_assistant.state,
        "wakeword": voice_assistant.wakeword,
        "running": voice_assistant._running,
        "paused": voice_assistant._paused,
        "tts_rate": voice_assistant.tts.rate,
        "tts_volume": voice_assistant.tts.volume,
        "sensitivity": voice_assistant.sensitivity
    })

@app.route('/api/voice/toggle', methods=['POST'])
def toggle_voice_api():
    """Active ou met en pause l'écoute continue du mot-clé."""
    is_active = voice_assistant.toggle()
    return jsonify({
        "success": True,
        "active": is_active,
        "state": voice_assistant.state,
        "message": f"Écoute vocale {'activée' if is_active else 'en pause'}"
    })

@app.route('/api/voice/speak', methods=['POST'])
def speak_text_api():
    """Synthèse vocale hors-ligne via pyttsx3."""
    data = request.json or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({"error": "Texte vide"}), 400
    voice_assistant.tts.speak(text)
    return jsonify({"success": True, "message": "Lecture lancée"})

@app.route('/api/voice/config', methods=['POST'])
def config_voice_api():
    """Ajuste les paramètres du système vocal."""
    data = request.json or {}
    if 'tts_rate' in data:
        voice_assistant.tts.rate = int(data['tts_rate'])
    if 'tts_volume' in data:
        voice_assistant.tts.volume = float(data['tts_volume'])
    if 'sensitivity' in data:
        sens = float(data['sensitivity'])
        voice_assistant.sensitivity = sens
        if hasattr(voice_assistant, 'wakeword_engine') and voice_assistant.wakeword_engine:
            voice_assistant.wakeword_engine.threshold = sens
    return jsonify({"success": True, "message": "Configuration vocale mise à jour"})

@socketio.on('voice_toggle')
def handle_socket_voice_toggle():
    is_active = voice_assistant.toggle()
    socketio.emit('voice_status', {'status': voice_assistant.state, 'active': is_active})

# ============================================================
# 20. CHAT ENDPOINT (PIPELINE COMPLET) - VERSION CORRIGÉE
# ============================================================

def save_user_data(username, user_data):
    """
    Sauvegarde correctement les données d'un utilisateur.
    """
    users = load_users()
    users[username] = user_data
    save_users(users)


def _save_chat_turn(username, user_data, conv_id, user_input, response, language):
    """
    Sauvegarde un échange utilisateur / assistant dans :
    - l'historique utilisateur
    - la mémoire long terme
    - la conversation courante
    """
    if "history" not in user_data:
        user_data["history"] = []

    user_data["history"].append({
        "role": "user",
        "content": user_input
    })

    user_data["history"].append({
        "role": "assistant",
        "content": response
    })

    save_user_data(username, user_data)

    try:
        add_to_ltm(username, user_input, response, language)
    except Exception as e:
        print(f"[LTM] Erreur lors de la sauvegarde LTM: {e}")

    try:
        if memory_manager:
            memory_manager.record_turn(username, conv_id or "default", user_input, response)
    except Exception as e:
        print(f"[MemoryManager] Erreur enregistrement tour: {e}")

    # Auto-consolidation STM -> LTM lorsqu'une conversation atteint un seuil
    try:
        if memory_manager and conv_id:
            conv = get_current_conversation(username, conv_id)
            if conv and len(conv.get("messages", [])) >= 10:
                if memory_manager:
                    memory_manager.consolidate_to_ltm(
                        username=username,
                        conv_id=conv_id,
                        conversation_messages=conv.get("messages", []),
                        importance_threshold=0.25
                    )
    except Exception as e:
        print(f"[MemoryManager] Erreur consolidation : {e}")

    if conv_id:
        conv = get_current_conversation(username, conv_id)
        if conv:
            messages = conv.get("messages", [])

            messages.append({
                "role": "user",
                "content": user_input
            })

            messages.append({
                "role": "assistant",
                "content": response
            })

            title = None
            if len(messages) <= 2:
                title = user_input[:50] + ("..." if len(user_input) > 50 else "")

            update_conversation(username, conv_id, messages, title)


@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    session_id = request.headers.get('X-Session-ID')
    username = validate_session(session_id)

    if not username:
        return jsonify({"error": "Non authentifié"}), 401

    data = request.json or {}
    user_input = data.get('prompt', '').strip()

    if not user_input:
        return jsonify({"error": "Prompt vide"}), 400
    if len(user_input) > MAX_PROMPT_LENGTH:
        return jsonify({"error": "Prompt trop volumineux"}), 413

    detected_sentiment = sentiment_engine.observe(username, user_input) if sentiment_engine else {"label": "neutral", "name": "Neutre", "emoji": "◌", "confidence": 0}

    if user_input.lower().startswith("hey_jarvis"):
        user_input = user_input[len("hey_jarvis"):].strip()

    language = data.get('language', 'fr')
    doc_mode = data.get('doc_mode', False)
    conv_id = data.get('conv_id')
    request_settings = normalize_user_settings(data.get('settings') or {})

    user_data = get_user_storage(username)
    if user_data is None:
        return jsonify({"error": "Utilisateur non trouvé"}), 404

    compressed_input = user_input
    response = None
    model_used = "Qwen"
    web_used = False
    file_used = False
    ltm_context = ""

    cache_key = f"{username}:{compressed_input}:{language}:{doc_mode}"

    # --------------------------------------------------------
    # 1. ORCHESTRATEUR / AGENTS SPÉCIALISÉS
    # --------------------------------------------------------
    try:
        agent_result = orchestrator.execute_task(user_input, {})

        if agent_result is not None and agent_result.get("success"):
            response = agent_result.get("output", "")
            model_used = "Agent spécialisé"

            _save_chat_turn(
                username=username,
                user_data=user_data,
                conv_id=conv_id,
                user_input=user_input,
                response=response,
                language=language
            )

            return jsonify({
                "response": response,
                "model_used": model_used,
                "web_used": False,
                "file_used": False,
                "doc_mode": doc_mode,
                "language": LANGUAGE_NAMES.get(language, "Français")
            })

    except Exception as e:
        print(f"[Agent] Erreur: {e}")
        traceback.print_exc()

    # --------------------------------------------------------
    # 2. NEXUS-Ω : REQUÊTES SIMPLES / INTENTIONS OUTILS
    # --------------------------------------------------------
    try:
        is_simple, simple_response = NexusOmega.is_simple_query(user_input)

        if is_simple:
            response = simple_response
            model_used = "NEXUS-Standardiste"

            _save_chat_turn(
                username=username,
                user_data=user_data,
                conv_id=conv_id,
                user_input=user_input,
                response=response,
                language=language
            )

            return jsonify({
                "response": response,
                "model_used": model_used,
                "web_used": False,
                "file_used": False,
                "doc_mode": doc_mode,
                "language": LANGUAGE_NAMES.get(language, "Français")
            })

        compressed_input = NexusOmega.compress_prompt(user_input)
        cache_key = f"{username}:{compressed_input}:{language}:{doc_mode}"

        tool_type, tool_response = NexusOmega.detect_tool_intent(compressed_input, username)

        if tool_type == "tool":
            response = tool_response
            model_used = "NEXUS-Tool"

            _save_chat_turn(
                username=username,
                user_data=user_data,
                conv_id=conv_id,
                user_input=user_input,
                response=response,
                language=language
            )

            return jsonify({
                "response": response,
                "model_used": model_used,
                "web_used": False,
                "file_used": False,
                "doc_mode": doc_mode,
                "language": LANGUAGE_NAMES.get(language, "Français")
            })

    except Exception as e:
        print(f"[NEXUS] Erreur: {e}")
        traceback.print_exc()

    # --------------------------------------------------------
    # 3. SYNAPSE-X : MÉMOIRE / CACHE
    # --------------------------------------------------------
    try:
        # Recherche LTM améliorée via brain memory manager
        past_convs = load_history(username)
        if memory_manager:
            ltm_results = memory_manager.search_ltm_smart(
                username, compressed_input,
                ltm_data_source=past_convs,
                limit=3
            )
        else:
            ltm_results = SynapseX.search_ltm(username, compressed_input, limit=3)

        if ltm_results:
            first_memory = ltm_results[0]
            timestamp = str(first_memory.get("timestamp", ""))[:10]
            summary = first_memory.get("summary", "")
            if summary:
                ltm_context = f"Souvenir pertinent ({timestamp}) : {summary}"
            else:
                ltm_context = (
                    f"Contexte mémorisé ({timestamp}) : "
                    f"Vous aviez dit : {first_memory.get('user', '')} | "
                    f"Onyx avait répondu : {first_memory.get('assistant', '')}"
                )

        cached_response = SynapseX.get_cached_response(cache_key)

        if cached_response:
            response = cached_response
            model_used = "SYNAPSE-Cache"

            _save_chat_turn(
                username=username,
                user_data=user_data,
                conv_id=conv_id,
                user_input=user_input,
                response=response + " *(cache)*",
                language=language
            )

            return jsonify({
                "response": response + " *(cache)*",
                "model_used": model_used,
                "web_used": False,
                "file_used": False,
                "doc_mode": doc_mode,
                "language": LANGUAGE_NAMES.get(language, "Français")
            })

    except Exception as e:
        print(f"[SYNAPSE] Erreur: {e}")
        traceback.print_exc()

    # --------------------------------------------------------
    # 4. KAIROS : DÉBAT CONTRADICTOIRE
    # --------------------------------------------------------
    try:
        complex_indicators = [
            "pourquoi",
            "comment",
            "explique",
            "analyse",
            "compare",
            "différence",
            "qu'est-ce que"
        ]

        is_complex = (
            len(compressed_input.split()) > 20
            or any(kw in compressed_input.lower() for kw in complex_indicators)
        )

        if is_complex:
            consensus = Kairos.run_debate(compressed_input)

            if consensus and consensus != "Aucun consensus clair trouvé. Voici une synthèse des deux positions.":
                final_prompt = (
                    "Rédige une réponse définitive, équilibrée et intelligente, "
                    f"en utilisant UNIQUEMENT ces points de consensus : {consensus}"
                )

                system_prompt_final = (
                    "Tu es le juge final, tu synthétises les points de consensus "
                    "en une réponse claire."
                )

                final_response = call_qwen_deep(
                    final_prompt,
                    system_prompt_final,
                    temperature=0.3,
                    max_tokens=500,
                    timeout=LLM_TIMEOUT_MEDIUM
                )

                if final_response:
                    response = final_response
                    model_used = "QWEN (synthèse KAIROS)"

    except Exception as e:
        print(f"[KAIROS] Erreur: {e}")
        traceback.print_exc()

    # --------------------------------------------------------
    # 5. FALLBACK : PIPELINE STANDARD
    # --------------------------------------------------------
    if response is None:
        try:
            current_time = time.time()

            files = [
                f for f in user_data.get("files", [])
                if current_time - f.get("timestamp", 0) < 600
            ]

            user_data["files"] = files
            save_user_data(username, user_data)

            file_used = bool(files)
            web_data = None

            # Mode document : on répond uniquement à partir du fichier fourni
            if doc_mode and files:
                ref_file = files[0]

                system_prompt = (
                    f"Tu es Onyx, assistant IA. Réponds UNIQUEMENT basé sur le contenu du fichier :\n"
                    f"=== {ref_file.get('filename', 'fichier')} ===\n"
                    f"{ref_file.get('content', '')}\n"
                    f"=== FIN ===\n"
                    f"Réponds en {LANGUAGE_NAMES.get(language, 'Français')}."
                )

                enriched_prompt = compressed_input

            # Mode normal : fichiers + web + question utilisateur
            else:
                recent_keywords = [
                    "actuel",
                    "aujourd'hui",
                    "récent",
                    "2024",
                    "2025",
                    "2026",
                    "prix",
                    "qui est",
                    "dernier"
                ]

                if any(kw in compressed_input.lower() for kw in recent_keywords):
                    serper_key = request_settings.get('serper_key', '') or (data.get('settings') or {}).get('serperKey', '')
                    web_data = fetch_web_context(compressed_input, serper_key=serper_key)

                web_used = bool(web_data)

                enriched_parts = []

                # ✅ CORRECTION DE L'ERREUR D'INDENTATION ICI
                if files:
                    for f in files[:2]:
                        enriched_parts.append(
                            f"=== {f.get('filename', 'fichier')} ===\n"
                            f"{f.get('content', '')[:1500]}"
                        )

                if web_data:
                    enriched_parts.append(
                        f"=== Contexte web ===\n{web_data}"
                    )

                if ltm_context:
                    enriched_parts.append(ltm_context)

                enriched_parts.append(
                    f"Question utilisateur: {compressed_input}"
                )

                enriched_prompt = "\n\n".join(enriched_parts)

                # Charger la personnalite complete d'Onyx
                try:
                    from brain.identity import ONYX_PERSONALITY as _OP
                except ImportError:
                    try:
                        from identity import ONYX_PERSONALITY as _OP
                    except ImportError:
                        _OP = "Tu es Onyx, un assistant IA autonome."

                system_prompt = (
                    f"{_OP.strip()}\n\n"
                    f"Réponds toujours en {LANGUAGE_NAMES.get(language, 'Français')}. "
                    f"Sois direct, technique et orienté solution. "
                    f"{sentiment_engine.guidance(detected_sentiment) if sentiment_engine else ''} "
                    f"Si l'utilisateur demande d'exécuter une commande ou de lire un fichier, "
                    f"fais-le immédiatement sans hésitation."
                )

            fallback_response = call_qwen_deep(
                enriched_prompt,
                system_prompt,
                temperature=request_settings["temperature"],
                max_tokens=request_settings["max_tokens"],
                timeout=request_settings["request_timeout"],
                model=request_settings.get("model") if request_settings.get("model") in {MAIN_BRAIN, SUB_BRAIN} else MAIN_BRAIN
            )

            if fallback_response:
                response = fallback_response
                model_used = "Qwen"
            else:
                response = "Désolé, je n'ai pas pu générer une réponse."
                model_used = "Qwen"

        except Exception as e:
            print(f"[FALLBACK] Erreur: {e}")
            traceback.print_exc()
            response = "Désolé, une erreur est survenue dans le pipeline principal."
            model_used = "Erreur"
            web_used = False
            file_used = False

    # --------------------------------------------------------
    # 6. CACHE + SAUVEGARDE FINALE
    # --------------------------------------------------------
    try:
        if response and model_used not in ("SYNAPSE-Cache", "Erreur"):
            SynapseX.set_cached_response(cache_key, response)
    except Exception as e:
        print(f"[SYNAPSE CACHE] Erreur lors de la mise en cache: {e}")

    _save_chat_turn(
        username=username,
        user_data=user_data,
        conv_id=conv_id,
        user_input=user_input,
        response=response,
        language=language
    )

    return jsonify({
        "response": response,
        "model_used": model_used,
        "web_used": web_used,
        "file_used": file_used,
        "doc_mode": doc_mode,
        "language": LANGUAGE_NAMES.get(language, "Français"),
        "sentiment": detected_sentiment
    })


# ============================================================
# FONCTIONS MANQUANTES (SAFE STUBS)
# ============================================================

if "execute_python_sandbox" not in globals():
    def execute_python_sandbox(code, timeout=15):
        import subprocess
        import tempfile
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(code)
                tmp_path = f.name

            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            try:
                os.remove(tmp_path)
            except Exception:
                pass

            return {
                "success": result.returncode == 0,
                "output": result.stdout.strip(),
                "error": result.stderr.strip()
            }
        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}


if "tree_of_thoughts" not in globals():
    def tree_of_thoughts(problem):
        system_prompt = "Tu es un raisonneur structuré. Décompose le problème, explore plusieurs pistes, puis donne une conclusion claire."
        prompt = f"Problème : {problem}\n\nPropose une analyse structurée avec : 1) hypothèses, 2) pistes, 3) risques, 4) conclusion."
        result = call_qwen_deep(
            prompt,
            system_prompt,
            temperature=0.3,
            max_tokens=800,
            timeout=LLM_TIMEOUT_MEDIUM
        )
        return result or "Impossible de générer une analyse."


if "get_notifications" not in globals():
    def get_notifications(username, unread_only=False):
        user_data = get_user_storage(username)
        if not user_data:
            return []
        notifications = user_data.get("notifications", [])
        if unread_only:
            notifications = [n for n in notifications if not n.get("read", False)]
        return sorted(notifications, key=lambda x: x.get("timestamp", ""), reverse=True)


if "mark_notification_read" not in globals():
    def mark_notification_read(username, notif_id):
        user_data = get_user_storage(username)
        if not user_data:
            return

        for notification in user_data.get("notifications", []):
            if notification.get("id") == notif_id:
                notification["read"] = True
                break

        all_users = load_users()
        if username in all_users:
            all_users[username] = user_data
            save_users(all_users)


if "SystemAgent" in globals() and not hasattr(SystemAgent, "_get_system_status"):
    def _get_system_status(self):
        try:
            import psutil
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("C:/" if IS_WINDOWS else "/")
            msg = (
                f"Statut système\n"
                f"CPU : {cpu}%\n"
                f"RAM : {ram.percent}% ({ram.used // (1024 ** 2)} MB / {ram.total // (1024 ** 2)} MB)\n"
                f"Disque : {disk.percent}% ({disk.used // (1024 ** 3)} GB / {disk.total // (1024 ** 3)} GB)"
            )
            return {"success": True, "output": msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    SystemAgent._get_system_status = _get_system_status


# ============================================================
# LANCEMENT DU SERVEUR & DU MOTEUR VOCAL
# ============================================================

def run_web_mode():
    try:
        print("[Onyx V2] Démarrage du système vocal local en arrière-plan...")
        voice_assistant.start()
    except Exception as e:
        print(f"[Onyx V2] Erreur démarrage vocal : {e}")

    try:
        socketio.run(
            app,
            host="0.0.0.0",
            port=5000,
            debug=False,
            allow_unsafe_werkzeug=True
        )
    except TypeError:
        socketio.run(
            app,
            host="0.0.0.0",
            port=5000,
            debug=False
        )


def run_terminal_mode():
    print("=== Onyx V2 - Mode Terminal ===")
    print("Tapez 'hey_jarvis <message>' pour parler à l'IA")
    print("Tapez 'quit' ou 'exit' pour quitter\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir !")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q", "quitter"):
            print("Au revoir !")
            break

        if user_input.startswith("hey_jarvis"):
            prompt = user_input[len("hey_jarvis"):].strip()
            if not prompt:
                print("Usage: hey_jarvis <message>")
                continue

            print("[Onyx traite...]")
            try:
                response = process_voice_prompt(prompt)
                if response:
                    print(f"\nOnyx: {response}\n")
                else:
                    print("\nOnyx: [Pas de réponse]\n")
            except Exception as e:
                print(f"\nOnyx: [Erreur] {e}\n")
        else:
            print("Utilisez 'hey_jarvis <message>' pour me parler")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onyx V2")
    parser.add_argument("--terminal", "-t", action="store_true", help="Lancer en mode terminal")
    parser.add_argument("--web", "-w", action="store_true", help="Lancer en mode web uniquement")
    args = parser.parse_args()

    if args.terminal:
        run_terminal_mode()
    elif args.web:
        try:
            print("[Onyx V2] Démarrage du système vocal local en arrière-plan...")
            voice_assistant.start()
        except Exception as e:
            print(f"[Onyx V2] Erreur démarrage vocal : {e}")

        try:
            socketio.run(
                app,
                host="0.0.0.0",
                port=5000,
                debug=False,
                allow_unsafe_werkzeug=True
            )
        except TypeError:
            socketio.run(
                app,
                host="0.0.0.0",
                port=5000,
                debug=False
            )
    else:
        web_thread = threading.Thread(target=run_web_mode, daemon=True)
        web_thread.start()
        print("[Onyx V2] Interface web démarrée en arrière-plan sur http://localhost:5000")
        run_terminal_mode()

