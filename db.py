# -*- coding: utf-8 -*-
"""
MongoDB Atlas (bepul tarif) bilan ishlash.
Uch asosiy to'plam (collection):
  - conversations: har bir agent + foydalanuvchi uchun suhbat tarixi (xotira)
  - tasks: Direktor tomonidan boshqa AI bo'limlarga berilgan topshiriqlar
  - human_tasks: Direktor tomonidan haqiqiy xodimga yuborilgan xabarlar
    va ularning javobi kutilayotgan holati
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


# ---------- AI bo'limlarga vazifalar ----------

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


# ---------- Haqiqiy xodimga yuborilgan xabarlar ----------

def create_human_task(employee_key: str, employee_chat_id: int,
                       message_text: str, origin_chat_id: int,
                       origin_agent: str):
    """Direktor xodimga xabar yuborganda chaqiriladi."""
    db = get_db()
    db.human_tasks.insert_one(
        {
            "employee_key": employee_key,
            "employee_chat_id": employee_chat_id,
            "message_text": message_text,
            "origin_chat_id": origin_chat_id,
            "origin_agent": origin_agent,
            "status": "waiting_reply",
            "created_at": datetime.datetime.utcnow(),
        }
    )


def get_waiting_human_task(employee_chat_id: int):
    """Shu xodimdan javob kutilayotgan eng so'nggi vazifani topadi."""
    db = get_db()
    return db.human_tasks.find_one(
        {"employee_chat_id": employee_chat_id, "status": "waiting_reply"},
        sort=[("created_at", -1)],
    )


def mark_human_task_replied(task_id, reply_text: str):
    db = get_db()
    db.human_tasks.update_one(
        {"_id": task_id},
        {"$set": {"status": "replied", "reply_text": reply_text,
                   "replied_at": datetime.datetime.utcnow()}},
    )
