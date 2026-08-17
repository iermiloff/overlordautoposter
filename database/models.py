import sqlite3
import json
import os

DB_PATH = "data/autoposter.db"

def init_db():
    """Инициализация базы данных при старте бота и миграция старых таблиц"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Таблица настроек
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        ''')
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('timezone', 'UTC')")
        
        # Базовое создание таблицы постов (для новых деплоев)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_type TEXT,
            media_id TEXT,
            text TEXT,
            buttons TEXT,
            interval_min INTEGER DEFAULT NULL,
            publish_at TEXT DEFAULT NULL,
            is_delayed INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            last_posted TEXT DEFAULT NULL,
            target_channels TEXT DEFAULT '[]'
        )
        ''')
        
        # --- МИГРАЦИЯ ДЛЯ СУЩЕСТВУЮЩИХ БАЗ ДАННЫХ ---
        # Проверяем существующие колонки в posts, чтобы не упасть при их отсутствии
        cursor.execute("PRAGMA table_info(posts)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "interval_min" not in columns:
            try: cursor.execute("ALTER TABLE posts ADD COLUMN interval_min INTEGER DEFAULT NULL")
            except: pass
        if "publish_at" not in columns:
            try: cursor.execute("ALTER TABLE posts ADD COLUMN publish_at TEXT DEFAULT NULL")
            except: pass
        if "is_delayed" not in columns:
            try: cursor.execute("ALTER TABLE posts ADD COLUMN is_delayed INTEGER DEFAULT 0")
            except: pass
            
        # Таблица каналов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            channel_id INTEGER PRIMARY KEY,
            title TEXT
        )
        ''')
        conn.commit()

def get_timezone() -> str:
    """Получить текущий часовой пояс администратора"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'timezone'")
        res = cursor.fetchone()
        return res[0] if res else "UTC"

def set_timezone(tz_name: str):
    """Обновить часовой пояс администратора"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'timezone'", (tz_name,))
        conn.commit()

def add_post(media_type, media_id, text, buttons, interval=None, publish_at=None, is_delayed=0, target_channels=None):
    """Добавление нового поста в базу данных (интервального или отложенного)"""
    if target_channels is None:
        target_channels = []
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO posts (media_type, media_id, text, buttons, interval_min, publish_at, is_delayed, target_channels) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (media_type, media_id, text, json.dumps(buttons), interval, publish_at, is_delayed, json.dumps(target_channels))
        )
        conn.commit()

def get_all_posts():
    """Получение абсолютно всех постов для фонового планировщика"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts")
        return cursor.fetchall()

def get_posts_page(limit: int, offset: int):
    """Получение постов порциями для пагинации админки"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
        return cursor.fetchall()

def get_posts_count() -> int:
    """Общее количество постов в базе"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM posts")
        res = cursor.fetchone()
        return res[0] if res else 0

def get_post_by_id(post_id: int):
    """Получение одного конкретного поста для детального просмотра"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        return cursor.fetchone()

def update_post_status(post_id: int, is_active: int):
    """Включение / Выключение автопостинга для поста"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET is_active = ? WHERE id = ?", (is_active, post_id))
        conn.commit()

def delete_post(post_id: int):
    """Полное удаление поста"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()

def update_last_posted(post_id: int, timestamp: str):
    """Обновление метки времени при публикации"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET last_posted = ? WHERE id = ?", (timestamp, post_id))
        conn.commit()

def add_channel(channel_id: int, title: str):
    """Сохранить канал при добавлении бота в админы"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO channels (channel_id, title) VALUES (?, ?)", (channel_id, title))
        conn.commit()

def remove_channel(channel_id: int):
    """Удалить канал, если бота убрали из админов"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        conn.commit()

def get_all_channels_detailed():
    """Получить список каналов со всеми полями (ID и Название)"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM channels ORDER BY title ASC")
        return cursor.fetchall()

def update_post_channels(post_id: int, channels_list: list):
    """Обновить список целевых каналов для конкретного поста"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET target_channels = ? WHERE id = ?", (json.dumps(channels_list), post_id))
        conn.commit()

def update_post_field(post_id: int, field_name: str, value):
    """Универсальное обновление любого текстового/числового поля поста"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE posts SET {field_name} = ? WHERE id = ?", (value, post_id))
        conn.commit()

def update_post_media(post_id: int, media_type: str, media_id: str):
    """Обновление медиафайла поста"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET media_type = ?, media_id = ? WHERE id = ?", (media_type, media_id, post_id))
        conn.commit()

