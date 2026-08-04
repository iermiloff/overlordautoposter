import sqlite3
import json
import os

DB_PATH = "data/autoposter.db"

def init_db():
    """Инициализация базы данных при старте бота"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Таблица постов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_type TEXT,
                media_id TEXT,
                text TEXT,
                buttons TEXT,
                interval_min INTEGER,
                is_active INTEGER DEFAULT 1,
                last_posted TEXT DEFAULT NULL,
                target_channels TEXT DEFAULT '[]'
            )
        ''')
        # Таблица каналов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                title TEXT
            )
        ''')
        conn.commit()

def add_post(media_type, media_id, text, buttons, interval, target_channels=None):
    """Добавление нового поста в базу данных"""
    if target_channels is None:
        target_channels = []
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO posts (media_type, media_id, text, buttons, interval_min, target_channels) VALUES (?, ?, ?, ?, ?, ?)",
            (media_type, media_id, text, json.dumps(buttons), interval, json.dumps(target_channels))
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
        cursor.execute(
            "SELECT * FROM posts ORDER BY id DESC LIMIT ? OFFSET ?", 
            (limit, offset)
        )
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
