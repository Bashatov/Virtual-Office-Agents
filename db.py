# -*- coding: utf-8 -*-
"""
MongoDB Atlas bilan ishlash. To'plamlar (collection):
  - conversations: har bir agent + foydalanuvchi suhbat tarixi (xotira)
  - tasks: Direktordan boshqa AI bo'limlarga berilgan vazifalar
  - employees: xodimlar ro'yxati (Direktorga yozib qo'shiladi, fayl
    tahrirlash shart emas)
  - human_tasks: xodimga guruhda @mention orqali yuborilgan xabarlar va
    ularning javobi kutilayotgan holati
"""

import os
import datetime
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        uri = os.getenv("MONGODB_URI")
        _client = MongoClient(uri)
        _db = _client[os.getenv("MONGODB_DB_NAME", "ai_jamoa")]
        # Takroriy Telegram update'larni aniqlash uchun unikal indeks
        # (masalan server qayta ishga tushganda bitta xabar ikki marta
        # qayta ishlanib ketmasligi uchun).
        _db.processed_updates.create_index(
            [("agent", 1), ("update_id", 1)], unique=True
        )
    return _db


# ---------- Takroriy xabarlarni aniqlash ----------

def claim_update(agent_key: str, update_id: int) -> bool:
    """
    True qaytaradi - agar bu update shu agent uchun BIRINCHI marta
    ko'rilayotgan bo'lsa (demak qayta ishlash mumkin).
    False qaytaradi - agar bu update ALLAQACHON qayta ishlangan bo'lsa
    (masalan server qayta ishga tushishi natijasida takrorlangan) -
    bunda handler hech narsa qilmasdan chiqib ketishi kerak.
    """
    db = get_db()
    try:
        db.processed_updates.insert_one({
            "agent": agent_key, "update_id": update_id,
            "ts": datetime.datetime.utcnow(),
        })
        return True
    except DuplicateKeyError:
        return False


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


# ---------- Xodimlar (Direktorga yozib qo'shiladi/tahrirlanadi, DB'da saqlanadi) ----------

def upsert_employee(key: str, fields: dict):
    """
    fields - faqat YANGILANISHI kerak bo'lgan maydonlar (name/phone/
    sohasi/username). Berilmagan maydonlarga tegilmaydi - shu orqali
    ham yangi xodim qo'shish, ham mavjudini QISMAN tahrirlash mumkin
    (masalan faqat telefon raqamini yangilash).
    """
    db = get_db()
    update = {}
    for k, v in fields.items():
        if not v or v == "-":
            continue
        if k == "username":
            v = v.lstrip("@")
        update[k] = v
    update["key"] = key
    update["updated_at"] = datetime.datetime.utcnow()
    db.employees.update_one({"key": key}, {"$set": update}, upsert=True)


def delete_employee(key: str) -> bool:
    db = get_db()
    result = db.employees.delete_one({"key": key})
    return result.deleted_count > 0


def get_employee(key: str):
    db = get_db()
    return db.employees.find_one({"key": key})


def list_employees():
    db = get_db()
    return list(db.employees.find({}))


# ---------- Xodimga guruhda @mention orqali yuborilgan xabarlar ----------

def create_human_task(employee_key: str, employee_username: str,
                       group_chat_id: int, thread_id, message_text: str,
                       origin_chat_id: int, origin_agent: str):
    db = get_db()
    db.human_tasks.insert_one(
        {
            "employee_key": employee_key,
            "employee_username": employee_username,
            "group_chat_id": group_chat_id,
            "thread_id": thread_id,
            "message_text": message_text,
            "origin_chat_id": origin_chat_id,
            "origin_agent": origin_agent,
            "status": "waiting_reply",
            "created_at": datetime.datetime.utcnow(),
        }
    )


def claim_human_task_by_username(group_chat_id: int, username: str, reply_text: str):
    """
    Guruhda kimdir yozganda chaqiriladi: agar shu username'dan javob
    kutilayotgan vazifa bo'lsa, uni ATOMAR ravishda "band qiladi" -
    shu bilan 6 ta bot bir xabarni 6 marta forward qilib yubormaydi
    (faqat birinchi ulgurgan bot vazifani "yutib oladi").
    """
    db = get_db()
    return db.human_tasks.find_one_and_update(
        {
            "group_chat_id": group_chat_id,
            "employee_username": username,
            "status": "waiting_reply",
        },
        {"$set": {
            "status": "replied",
            "reply_text": reply_text,
            "replied_at": datetime.datetime.utcnow(),
        }},
        sort=[("created_at", -1)],
        return_document=ReturnDocument.AFTER,
    )
