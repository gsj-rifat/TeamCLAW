import aiosqlite
import json
import time
from typing import List, Optional
from src.core.interfaces.db import DatabasePort
from src.core.models.insights import InsightRecord
from src.core.models.sop import Sop
from src.infrastructure.config import settings

class SqliteAdapter(DatabasePort):
    def __init__(self, db_path: str = settings.insights_db_path):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    channel_id TEXT,
                    user_id TEXT,
                    decisions TEXT,
                    todos TEXT,
                    facts TEXT,
                    message_text TEXT
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    channel_id TEXT,
                    created_by TEXT,
                    status TEXT DEFAULT 'active',
                    tags TEXT,
                    created_at INTEGER NOT NULL,
                    version TEXT DEFAULT 'v1'
                );
            """)
            await db.commit()

    async def save_insight(self, insight: InsightRecord) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO insights (
                    created_at, date, channel_id, user_id,
                    decisions, todos, facts, message_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                insight.created_at, insight.date, insight.channel_id, insight.user_id,
                json.dumps(insight.decisions), json.dumps(insight.todos), json.dumps(insight.facts),
                insight.message_text
            ))
            await db.commit()
            return cursor.lastrowid

    async def fetch_insights(self, start_ts: int, end_ts: int, channel_id: Optional[str] = None) -> List[InsightRecord]:
        query = "SELECT * FROM insights WHERE created_at >= ? AND created_at < ?"
        params = [start_ts, end_ts]
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    results.append(InsightRecord(
                        id=row['id'],
                        created_at=row['created_at'],
                        date=row['date'],
                        channel_id=row['channel_id'],
                        user_id=row['user_id'],
                        decisions=json.loads(row['decisions'] or "[]"),
                        todos=json.loads(row['todos'] or "[]"),
                        facts=json.loads(row['facts'] or "[]"),
                        message_text=row['message_text']
                    ))
                return results

    async def save_sop(self, sop: Sop) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO sops (
                    title, topic, content, channel_id, created_by, status, tags, created_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sop.title, sop.topic, sop.content, sop.channel_id, sop.created_by,
                sop.status, json.dumps(sop.tags) if sop.tags else None,
                sop.created_at, sop.version
            ))
            await db.commit()
            return cursor.lastrowid

    async def fetch_sops(self, limit: int = 100, status: Optional[str] = None) -> List[Sop]:
        query = "SELECT * FROM sops"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    results.append(Sop(
                        id=row['id'],
                        title=row['title'],
                        topic=row['topic'],
                        content=row['content'],
                        channel_id=row['channel_id'],
                        created_by=row['created_by'],
                        status=row['status'],
                        tags=json.loads(row['tags']) if row['tags'] else None,
                        created_at=row['created_at'],
                        version=row['version'] or "v1"
                    ))
                return results
