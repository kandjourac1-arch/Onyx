"""
Onyx V2 - Backend de Persistance Unifié SQLite avec FTS5
Remplace tous les fichiers JSON (users.json, ltm.json, history/*.json, facts.json)
"""

import sqlite3
import json
import threading
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Iterator
from contextlib import contextmanager
from pathlib import Path
import hashlib


class OnyxStorage:
    """Backend SQLite unifié avec FTS5 pour recherche full-text < 5ms."""

    def __init__(self, db_path: str = "onyx.db", batch_interval: float = 2.0):
        self.db_path = db_path
        self.batch_interval = batch_interval
        self._local = threading.local()
        self._write_buffer: List[Tuple[str, Tuple]] = []
        self._buffer_lock = threading.Lock()
        self._flush_thread: Optional[threading.Thread] = None
        self._stop_flush = threading.Event()
        self._init_db()
        self._start_flush_thread()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-32768")
            conn.execute("PRAGMA mmap_size=268435456")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        with self.transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    sessions TEXT DEFAULT '[]',
                    files TEXT DEFAULT '[]',
                    tasks TEXT DEFAULT '[]',
                    notifications TEXT DEFAULT '[]',
                    preferences TEXT DEFAULT '{}',
                    clipboard TEXT DEFAULT '',
                    devices TEXT DEFAULT '[]',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(username);
                CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    conversation_id UNINDEXED,
                    role UNINDEXED,
                    content,
                    content=messages,
                    content_rowid=id
                );

                CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(rowid, conversation_id, role, content)
                    VALUES (new.id, new.conversation_id, new.role, new.content);
                END;

                CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, conversation_id, role, content)
                    VALUES ('delete', old.id, old.conversation_id, old.role, old.content);
                END;

                CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, conversation_id, role, content)
                    VALUES ('delete', old.id, old.conversation_id, old.role, old.content);
                    INSERT INTO messages_fts(rowid, conversation_id, role, content)
                    VALUES (new.id, new.conversation_id, new.role, new.content);
                END;

                CREATE TABLE IF NOT EXISTS ltm (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    user_msg TEXT NOT NULL,
                    assistant_msg TEXT NOT NULL,
                    language TEXT DEFAULT 'fr',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_ltm_user ON ltm(username);
                CREATE INDEX IF NOT EXISTS idx_ltm_timestamp ON ltm(timestamp DESC);

                CREATE VIRTUAL TABLE IF NOT EXISTS ltm_fts USING fts5(
                    username UNINDEXED,
                    user_msg,
                    assistant_msg,
                    content=ltm,
                    content_rowid=id
                );

                CREATE TRIGGER IF NOT EXISTS ltm_ai AFTER INSERT ON ltm BEGIN
                    INSERT INTO ltm_fts(rowid, username, user_msg, assistant_msg)
                    VALUES (new.id, new.username, new.user_msg, new.assistant_msg);
                END;

                CREATE TRIGGER IF NOT EXISTS ltm_ad AFTER DELETE ON ltm BEGIN
                    INSERT INTO ltm_fts(ltm_fts, rowid, username, user_msg, assistant_msg)
                    VALUES ('delete', old.id, old.username, old.user_msg, old.assistant_msg);
                END;

                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(username, fact)
                );
                CREATE INDEX IF NOT EXISTS idx_facts_user ON facts(username);

                CREATE TABLE IF NOT EXISTS stm (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_stm_conv ON stm(username, conversation_id);

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

    def _start_flush_thread(self):
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def _flush_loop(self):
        while not self._stop_flush.is_set():
            time.sleep(self.batch_interval)
            if not self._stop_flush.is_set():
                self._flush_buffer()

    def _flush_buffer(self):
        with self._buffer_lock:
            if not self._write_buffer:
                return
            buffer = self._write_buffer
            self._write_buffer = []

        try:
            with self.transaction() as conn:
                for query, params in buffer:
                    conn.execute(query, params)
        except Exception as e:
            print(f"[Storage] Erreur flush buffer: {e}")

    def _buffer_write(self, query: str, params: Tuple):
        with self._buffer_lock:
            self._write_buffer.append((query, params))

    def execute(self, query: str, params: Tuple = ()) -> sqlite3.Cursor:
        return self._get_conn().execute(query, params)

    def executemany(self, query: str, params_list: List[Tuple]) -> sqlite3.Cursor:
        return self._get_conn().executemany(query, params_list)

    def fetchone(self, query: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
        return self._get_conn().execute(query, params).fetchone()

    def fetchall(self, query: str, params: Tuple = ()) -> List[sqlite3.Row]:
        return self._get_conn().execute(query, params).fetchall()

    # ============================================================
    # USERS
    # ============================================================
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone("SELECT * FROM users WHERE username = ?", (username,))
        if row:
            data = dict(row)
            for key in ["sessions", "files", "tasks", "notifications", "preferences", "devices"]:
                try:
                    data[key] = json.loads(data[key]) if data[key] else ([] if key != "preferences" else {})
                except Exception:
                    data[key] = [] if key != "preferences" else {}
            return data
        return None

    def get_user_ci(self, username: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone("SELECT * FROM users WHERE lower(username) = lower(?)", (username,))
        if row:
            data = dict(row)
            for key in ["sessions", "files", "tasks", "notifications", "preferences", "devices"]:
                try:
                    data[key] = json.loads(data[key]) if data[key] else ([] if key != "preferences" else {})
                except Exception:
                    data[key] = [] if key != "preferences" else {}
            return data
        return None

    def create_user(self, username: str, password_hash: str) -> bool:
        try:
            with self.transaction() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash)
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def update_user(self, username: str, updates: Dict[str, Any]) -> bool:
        valid_keys = {"password_hash", "sessions", "files", "tasks", "notifications", "preferences", "clipboard", "devices"}
        set_clauses = []
        params = []
        for key, value in updates.items():
            if key in valid_keys:
                set_clauses.append(f"{key} = ?")
                if isinstance(value, (list, dict)):
                    params.append(json.dumps(value, ensure_ascii=False))
                else:
                    params.append(value)
        if not set_clauses:
            return False
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.append(username)
        query = f"UPDATE users SET {', '.join(set_clauses)} WHERE username = ?"
        with self.transaction() as conn:
            cur = conn.execute(query, params)
            return cur.rowcount > 0

    def get_all_users(self) -> Dict[str, Dict[str, Any]]:
        rows = self.fetchall("SELECT * FROM users")
        result = {}
        for row in rows:
            data = dict(row)
            for key in ["sessions", "files", "tasks", "notifications", "preferences", "devices"]:
                try:
                    data[key] = json.loads(data[key]) if data[key] else ([] if key != "preferences" else {})
                except Exception:
                    data[key] = [] if key != "preferences" else {}
            result[data["username"]] = data
        return result

    # ============================================================
    # CONVERSATIONS
    # ============================================================
    def create_conversation(self, conversation_id: str, username: str, title: str = "Nouvelle conversation") -> bool:
        try:
            with self.transaction() as conn:
                conn.execute(
                    "INSERT INTO conversations (id, username, title) VALUES (?, ?, ?)",
                    (conversation_id, username, title)
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        return dict(row) if row else None

    def get_user_conversations(self, username: str, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM conversations WHERE username = ? ORDER BY updated_at DESC LIMIT ?",
            (username, limit)
        )
        return [dict(row) for row in rows]

    def update_conversation(self, conversation_id: str, title: Optional[str] = None, messages: Optional[List[Dict]] = None):
        updates = []
        params = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(conversation_id)
        query = f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?"
        with self.transaction() as conn:
            conn.execute(query, params)
            if messages is not None:
                conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
                conn.execute("DELETE FROM messages_fts WHERE conversation_id = ?", (conversation_id,))
                for msg in messages:
                    conn.execute(
                        "INSERT INTO messages (conversation_id, role, content, timestamp, metadata) VALUES (?, ?, ?, ?, ?)",
                        (conversation_id, msg.get("role", "user"), msg.get("content", ""), msg.get("timestamp", datetime.now().isoformat()), json.dumps(msg.get("metadata", {}), ensure_ascii=False))
                    )

    def delete_conversation(self, conversation_id: str) -> bool:
        with self.transaction() as conn:
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            return cur.rowcount > 0

    # ============================================================
    # MESSAGES
    # ============================================================
    def add_message(self, conversation_id: str, role: str, content: str, metadata: Optional[Dict] = None, buffer: bool = True):
        query = "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, ?, ?, ?)"
        params = (conversation_id, role, content, json.dumps(metadata or {}, ensure_ascii=False))
        if buffer:
            self._buffer_write(query, params)
        else:
            with self.transaction() as conn:
                conn.execute(query, params)

    def get_messages(self, conversation_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC LIMIT ?",
            (conversation_id, limit)
        )
        result = []
        for row in rows:
            data = dict(row)
            try:
                data["metadata"] = json.loads(data["metadata"]) if data["metadata"] else {}
            except Exception:
                data["metadata"] = {}
            result.append(data)
        return result

    def search_messages(self, username: str, query: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Recherche paginée, limitée à l'utilisateur, via FTS5."""
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        rows = self.fetchall(
            """SELECT m.id, m.conversation_id, m.role, m.content, m.timestamp
               FROM messages_fts f
               JOIN messages m ON m.id = f.rowid
               JOIN conversations c ON c.id = m.conversation_id
               WHERE f.messages_fts MATCH ? AND c.username = ?
               ORDER BY m.timestamp DESC LIMIT ? OFFSET ?""",
            (query, username, limit, offset),
        )
        return [dict(row) for row in rows]

    # ============================================================
    # LTM (Long Term Memory) with FTS5
    # ============================================================
    def add_ltm(self, username: str, user_msg: str, assistant_msg: str, language: str = "fr"):
        query = "INSERT INTO ltm (username, user_msg, assistant_msg, language) VALUES (?, ?, ?, ?)"
        params = (username, user_msg, assistant_msg, language)
        self._buffer_write(query, params)

    def search_ltm_fts(self, username: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            """SELECT l.id, l.username, l.user_msg, l.assistant_msg, l.language, l.timestamp,
                      bm25(ltm_fts) as rank
               FROM ltm_fts
               JOIN ltm l ON l.id = ltm_fts.rowid
               WHERE ltm_fts MATCH ? AND l.username = ?
               ORDER BY rank
               LIMIT ?""",
            (query, username, limit)
        )
        return [dict(row) for row in rows]

    def get_recent_ltm(self, username: str, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM ltm WHERE username = ? ORDER BY timestamp DESC LIMIT ?",
            (username, limit)
        )
        return [dict(row) for row in rows]

    def prune_ltm(self, username: str, max_entries: int = 1000):
        with self.transaction() as conn:
            conn.execute(
                """DELETE FROM ltm WHERE id IN (
                    SELECT id FROM ltm WHERE username = ? ORDER BY timestamp DESC LIMIT -1 OFFSET ?
                )""",
                (username, max_entries)
            )

    # ============================================================
    # FACTS
    # ============================================================
    def add_fact(self, username: str, fact: str) -> bool:
        try:
            with self.transaction() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO facts (username, fact) VALUES (?, ?)",
                    (username.lower(), fact)
                )
            return True
        except Exception:
            return False

    def get_facts(self, username: str) -> List[str]:
        rows = self.fetchall("SELECT fact FROM facts WHERE username = ? ORDER BY id", (username.lower(),))
        return [row["fact"] for row in rows]

    def remove_fact(self, username: str, pattern: str) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM facts WHERE username = ? AND fact LIKE ?",
                (username.lower(), f"%{pattern}%")
            )
            return cur.rowcount

    def clear_facts(self, username: str):
        with self.transaction() as conn:
            conn.execute("DELETE FROM facts WHERE username = ?", (username.lower(),))

    # ============================================================
    # STM (Short Term Memory)
    # ============================================================
    def add_stm(self, username: str, conversation_id: str, role: str, content: str):
        query = "INSERT INTO stm (username, conversation_id, role, content) VALUES (?, ?, ?, ?)"
        params = (username, conversation_id, role, content)
        self._buffer_write(query, params)

    def get_stm(self, username: str, conversation_id: str, max_messages: int = 24) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM stm WHERE username = ? AND conversation_id = ? ORDER BY timestamp ASC LIMIT ?",
            (username, conversation_id, max_messages)
        )
        return [dict(row) for row in rows]

    def clear_stm(self, username: str, conversation_id: str):
        with self.transaction() as conn:
            conn.execute("DELETE FROM stm WHERE username = ? AND conversation_id = ?", (username, conversation_id))

    # ============================================================
    # SETTINGS
    # ============================================================
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
        return default

    def set_setting(self, key: str, value: Any):
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=False))
            )

    # ============================================================
    # MIGRATION FROM JSON
    # ============================================================
    def migrate_from_json(self, base_dir: str):
        """Migre les données depuis les anciens fichiers JSON vers SQLite."""
        print("[Storage] Début de la migration JSON -> SQLite...")
        base = Path(base_dir)

        # users.json
        users_file = base / "users" / "users.json"
        if users_file.exists():
            try:
                with open(users_file, "r", encoding="utf-8") as f:
                    users = json.load(f)
                for username, data in users.items():
                    if not self.get_user(username):
                        sessions = json.dumps(data.get("sessions", []))
                        files = json.dumps(data.get("files", []))
                        tasks = json.dumps(data.get("tasks", []))
                        notifications = json.dumps(data.get("notifications", []))
                        preferences = json.dumps(data.get("preferences", {}))
                        clipboard = data.get("clipboard", "")
                        devices = json.dumps(data.get("devices", []))
                        with self.transaction() as conn:
                            conn.execute(
                                """INSERT INTO users (username, password_hash, sessions, files, tasks, notifications, preferences, clipboard, devices)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (username, data.get("password", ""), sessions, files, tasks, notifications, preferences, clipboard, devices)
                            )
                print(f"[Storage] Migré {len(users)} utilisateurs")
            except Exception as e:
                print(f"[Storage] Erreur migration users: {e}")

        # ltm.json
        ltm_file = base / "ltm.json"
        if ltm_file.exists():
            try:
                with open(ltm_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for conv in data.get("conversations", []):
                    self.add_ltm(
                        conv.get("username", ""),
                        conv.get("user", ""),
                        conv.get("assistant", ""),
                        conv.get("language", "fr")
                    )
                print(f"[Storage] Migré {len(data.get('conversations', []))} entrées LTM")
            except Exception as e:
                print(f"[Storage] Erreur migration LTM: {e}")

        # history/*.json
        history_dir = base / "history"
        if history_dir.exists():
            for hist_file in history_dir.glob("*.json"):
                try:
                    with open(hist_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    username = hist_file.stem
                    for conv in data.get("conversations", []):
                        conv_id = conv.get("id") or f"conv_{int(time.time()*1000)}"
                        self.create_conversation(conv_id, username, conv.get("title", "Nouvelle conversation"))
                        for msg in conv.get("messages", []):
                            self.add_message(conv_id, msg.get("role", "user"), msg.get("content", ""), buffer=False)
                except Exception as e:
                    print(f"[Storage] Erreur migration history {hist_file}: {e}")

        # facts.json
        facts_file = base / "memory" / "facts.json"
        if facts_file.exists():
            try:
                with open(facts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for username, facts in data.get("users", {}).items():
                    for fact in facts:
                        self.add_fact(username, fact)
                print(f"[Storage] Migré facts pour {len(data.get('users', {}))} utilisateurs")
            except Exception as e:
                print(f"[Storage] Erreur migration facts: {e}")

        print("[Storage] Migration terminée.")

    def close(self):
        self._stop_flush.set()
        if self._flush_thread:
            self._flush_thread.join(timeout=5)
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# Singleton instance
_storage: Optional[OnyxStorage] = None


def get_storage(db_path: str = "onyx.db") -> OnyxStorage:
    global _storage
    if _storage is None:
        _storage = OnyxStorage(db_path)
    return _storage
