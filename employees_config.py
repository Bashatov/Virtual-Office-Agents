# -*- coding: utf-8 -*-
"""
Haqiqiy (AI bo'lmagan) xodimlar ro'yxati.
Bular - siz bilan ishlaydigan real odamlar (videograf, haydovchi,
menejer va h.k.), ularga Direktor orqali to'g'ridan-to'g'ri Telegram
xabar yuborish va javobini kutish mumkin.

QANDAY QO'SHISH KERAK:
1. Xodimning o'zi Direktor botga Telegramda /start bosishi kerak
   (yoki botga bitta xabar yozishi kerak) - bottan xabar olish uchun bu shart.
2. Shundan so'ng https://api.telegram.org/bot<DIREKTOR_TOKEN>/getUpdates
   manzilini oching - u yerda xodimning "chat":{"id": ...} raqamini
   topasiz (xuddi GROUP_CHAT_ID'ni topgandek).
3. Shu raqamni pastdagi jadvalga kiriting.
"""

EMPLOYEES = {
    # Namuna - o'zingiznikini shunga o'xshab qo'shing:
    # "akobir": {
    #     "display_name": "Akobir (Videograf)",
    #     "chat_id": -1001234567890,
    # },
}
