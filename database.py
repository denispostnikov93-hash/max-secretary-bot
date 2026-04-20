"""
База данных для заявок
"""
import aiosqlite
from datetime import datetime
from config import DATABASE_PATH
from typing import Optional, Dict, Any, List

class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    async def init(self):
        """Создать таблицы"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    client_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    source TEXT NOT NULL,
                    consent_pd BOOLEAN NOT NULL,
                    consent_policy BOOLEAN NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.commit()

    async def save_application(self, name: str, phone: str, client_type: str,
                               category: str, description: Optional[str],
                               source: str, consent_pd: bool,
                               consent_policy: bool) -> int:
        """Сохранить заявку"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                '''INSERT INTO applications
                   (name, phone, client_type, category, description, source, consent_pd, consent_policy)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (name, phone, client_type, category, description, source, consent_pd, consent_policy)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_all_applications(self) -> List[Dict[str, Any]]:
        """Получить все заявки"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM applications ORDER BY created_at DESC')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_application(self, app_id: int) -> Optional[Dict[str, Any]]:
        """Получить одну заявку"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM applications WHERE id = ?', (app_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

db = Database()
