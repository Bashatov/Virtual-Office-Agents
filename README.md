# AI Jamoa — Telegram Multi-Agent Tizimi

6 ta AI agent: Bosh Direktor, Marketolog, SMM, Dizayner, Mobilograf, Moliyachi.
Direktor Claude'da, ijodiy bo'limlar (Marketolog/SMM/Dizayner) GPT-4o'da,
Mobilograf va Moliyachi Claude'da ishlaydi — `agents_config.py` faylida
istalgan vaqt o'zgartirish mumkin.

## 1-qadam: Telegram botlarini yaratish

1. Telegram'da **@BotFather**ga yozing.
2. Har bir agent uchun `/newbot` buyrug'ini yuboring (jami 6 marta):
   - Bosh Direktor
   - Marketolog
   - SMM
   - Dizayner
   - Mobilograf
   - Moliyachi
3. Har birida BotFather sizga **token** beradi (masalan
   `123456:ABC-DEF...`). Hammasini saqlab qo'ying.
4. Har bir bot uchun BotFather'da **Group Privacy'ni o'chiring**:
   `/mybots` → botni tanlang → `Bot Settings` → `Group Privacy` → `Turn off`.
   (Bu — bot guruhdagi barcha xabarlarni ko'rishi uchun kerak.)

## 2-qadam: "Virtual Ofis" guruhini yaratish

1. Telegram'da yangi guruh oching, nomini masalan **"Virtual Ofis"** qo'ying.
2. Barcha 6 ta botni shu guruhga qo'shing va **admin** qiling.
3. Guruh chat ID'sini bilish uchun: guruhga istalgan xabar yozing, so'ng
   brauzerda quyidagi manzilni oching (BOT_TOKEN o'rniga istalgan bitta
   bot tokenini qo'ying):
   `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
   Javobda `"chat":{"id":-1001234567890,...}` kabi raqamni topasiz —
   shu raqam sizning `GROUP_CHAT_ID`.

## 3-qadam: AI API kalitlarini olish

- **Claude**: console.anthropic.com → API Keys → yangi kalit yarating.
- **GPT-4o**: platform.openai.com → API Keys → yangi kalit yarating.
- Ikkalasida ham hisobingizga pul (billing) qo'shishingiz kerak bo'ladi
  (postpaid/prepaid — foydalanilgan hajmga qarab to'lanadi).

## 4-qadam: MongoDB Atlas (bepul ma'lumotlar bazasi)

1. mongodb.com/cloud/atlas saytida ro'yxatdan o'ting.
2. **Free tier (M0)** cluster yarating.
3. `Database Access`'da foydalanuvchi/parol yarating.
4. `Network Access`'da `Allow access from anywhere` (0.0.0.0/0) qo'shing
   (Railway'ning IP manzili o'zgarib turadi, shuning uchun shart).
5. `Connect` → `Drivers` bo'limidan ulanish satrini (connection string)
   nusxa oling — bu sizning `MONGODB_URI`.

## 5-qadam: Railway'da joylashtirish (deploy)

1. railway.app'da akkaunt oching, GitHub akkauntingizga ulang.
2. Bu loyihani (shu papkani) o'zingizning GitHub repo'ingizga yuklang.
3. Railway'da **New Project → Deploy from GitHub repo** tanlang, shu
   repo'ni tanlang.
4. Railway loyihangizning **Variables** bo'limiga o'ting va `.env.example`
   dagi barcha nomlarni haqiqiy qiymatlar bilan kiriting (tokenlar,
   API kalitlar, MONGODB_URI, GROUP_CHAT_ID).
5. Railway avtomatik `Procfile`ni o'qib, `python main.py` orqali botni
   ishga tushiradi. Bir necha daqiqadan so'ng barcha 6 ta bot onlayn
   bo'ladi.

## Qanday ishlaydi

- Direktor bilan shaxsiy chatda yozsangiz, u so'rovingizni tahlil qiladi
  va agar kerak bo'lsa mos bo'limga (masalan SMM'ga) avtomatik topshiriq
  beradi — bu topshiriq MongoDB'da saqlanadi.
- Har bir bo'lim-bot 20 soniyada bir marta o'ziga berilgan yangi
  topshiriqlarni tekshiradi, bajaradi va natijani **Virtual Ofis**
  guruhiga yozadi — xuddi videodagidek.
- Har bir agent bilan alohida (shaxsiy) suhbat ham qilishingiz mumkin —
  ular bir-biridan mustaqil ishlaydi.
- **Guruhda tartib**: xodimlar o'zaro yozishganda botlar aralashmaydi.
  Botni chaqirish uchun: `@BotUsername` yozing, botning oldingi
  xabariga "Reply" qiling, yoki xabarni bot nomi bilan boshlang
  (masalan "Marketolog, Instagram uchun post yoz").
- **Fayllar**: botlarga `.txt`, `.docx`, `.pdf` fayl yuborsangiz, ular
  fayl ichidagi matnni o'qib, shunga qarab javob beradi.
- **Ovozli xabarlar**: botlarga ovozli xabar yuborsangiz, ular uni
  avtomatik matnga o'girib (Whisper orqali), tushunib, matn holida
  javob qaytaradi.
- **Haqiqiy xodimga xabar**: Direktorga "operatorga ayt..." desangiz,
  u ro'yxatdagi xodimga to'g'ridan-to'g'ri Telegram xabar yuboradi va
  javobini kutib, kelgach sizga darhol yetkazadi.

## Keyingi kuchaytirishlar (ixtiyoriy)

- **Rasm generatsiya**: Dizayner-agent javobini DALL-E yoki Stability AI
  API'ga uzatib, tayyor rasm generatsiya qilish qo'shish mumkin.
- **Avtomatik post qilish**: SMM tayyorlagan matnni Telegram/Instagram'ga
  avtopost qilish uchun Instagram Graph API integratsiyasi.
- **Haftalik hisobot**: `db.py`dagi `conversations`/`tasks` to'plamlaridan
  haftalik statistikani Direktorga avtomatik yuborish (cron job sifatida
  `main.py`ga qo'shiladi).

## Xarajat taxmini (oyiga)

- Railway: ~$5 (worker doim ishlab turishi uchun)
- MongoDB Atlas: $0 (bepul tarif yetarli)
- Claude + GPT-4o API: foydalanishga qarab, odatda oyiga $10-30
  (kam trafik uchun)
