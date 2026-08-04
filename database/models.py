import sqlite3
import json
import os

DB_PATH = "data/autoposter.db"

def init_db():
    """Инициализация базы данных при старте бота"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_type TEXT,      -- photo, video, animation, text
                media_id TEXT,        -- file_id или ссылка
                text TEXT,
                buttons TEXT,         -- JSON-строка со списком кнопок
                interval_min INTEGER, -- интервал в минутах
                is_active INTEGER DEFAULT 1,
                last_posted TEXT DEFAULT NULL
            )
        ''')
        conn.commit()

def get_posts_page(limit: int, offset: int):
    """Получение постов порциями для пагинации"""
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
        return cursor.fetchone()[0]

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
