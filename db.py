# -*- coding: utf-8 -*-
"""
MongoDB Atlas (bepul tarif) bilan ishlash.
Ikki asosiy to'plam (collection):
  - conversations: har bir agent + foydalanuvchi uchun suhbat tarixi (xotira)
  - tasks: Direktor tomonidan boshqa bo'limlarga berilgan topshiriqlar
"""

import os
import datetime
from pymongo import MongoClient

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        uri = os.getenv("MONGODB_URI")
        _client = MongoClient(uri)
        _db = _client[os.getenv("MONGODB_DB_NAME", "ai_jamoa")]
    return _db


# ---------- Suhbat xotirasi ----------

def get_history(agent_key: str, chat_id: int, limit: int = 12) -> list[dict]:
    db = get_db()
    docs = (
        db.conversations.find({"agent": agent_key, "chat_id": chat_id})
        .sort("_id", -1)
        .limit(limit)
    )
    docs = list(docs)[::-1]
    return [{"role": d["role"], "content": d["content"]} for d in docs]


def save_message(agent_key: str, chat_id: int, role: str, content: str):
    db = get_db()
    db.conversations.insert_one(
        {
            "agent": agent_key,
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "ts": datetime.datetime.utcnow(),
        }
    )


# ---------- Vazifalar (topshiriqlar) ----------

def create_task(from_agent: str, to_agent: str, task_text: str, origin_chat_id: int):
    db = get_db()
    db.tasks.insert_one(
        {
            "from_agent": from_agent,
            "to_agent": to_agent,
            "task_text": task_text,
            "origin_chat_id": origin_chat_id,
            "status": "pending",
            "created_at": datetime.datetime.utcnow(),
        }
    )


def get_pending_tasks(to_agent: str):
    db = get_db()
    return list(db.tasks.find({"to_agent": to_agent, "status": "pending"}))


def mark_task_done(task_id, result_text: str):
    db = get_db()
    db.tasks.update_one(
        {"_id": task_id},
        {"$set": {"status": "done", "result": result_text,
                   "done_at": datetime.datetime.utcnow()}},
    )
