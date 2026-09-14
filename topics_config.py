# -*- coding: utf-8 -*-
"""
Guruhdagi har bir "Topic" (mavzu)ni tegishli agentga bog'lash.
Shu orqali har bir bot FAQAT o'ziga tegishli topic'da avtomatik javob
beradi (chaqirish - @mention shart emas), boshqa topic'larda esa
avvalgidek faqat chaqirilganda javob beradi.

QANDAY TOPIC ID TOPISH KERAK:
1. Guruhingizda "Topics" (Forum) funksiyasi yoqilgan bo'lishi kerak
   (guruh sozlamalarida "Topics" -> yoqing).
2. Har bir topic ichida (masalan "Marketolog" topicida) istalgan
   xabar yozing.
3. Brauzerda oching (istalgan bitta bot tokeni bilan):
   https://api.telegram.org/bot<TOKEN>/getUpdates
4. JSON javobida shu xabar uchun "message_thread_id": <raqam> ni
   topasiz - shu raqam o'sha topicning ID'si.
5. Pastdagi jadvalga kiriting.

Eslatma: "General" (asosiy) topicda thread_id bo'lmaydi - u har doim
oddiy guruh xabari sifatida ishlaydi (faqat @mention orqali chaqiriladi).
"""

TOPIC_MAP = {
   -1003942111149: "mobilograf",
   -1003942111149: "dizayner",
   -1003942111149: "marketolog",
   -1003942111149: "moliya",
   -1003942111149: "smm",
   -1003942111149: "direktor"
}
