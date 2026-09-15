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
   bo'ladi. `nixpacks.toml` fayli tufayli Railway avtomatik `ffmpeg`
   va shriftlarni ham o'rnatadi (video montaj funksiyasi uchun) —
   bu bosqich birinchi deploy'da 1-2 daqiqa qo'shimcha vaqt olishi
   mumkin, alohida sozlash shart emas.

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
- **Rasm va video**: istalgan botga rasm yoki video yuborib, "buni "
  tahlil qil" yoki "shunga qarab post/ssenariy yoz" deb so'rasangiz,
  bot AI vision orqali tasvirni "ko'rib", shunga qarab javob beradi.
  (Video uchun hozircha faqat asosiy kadr tahlil qilinadi, to'liq
  video emas.)
- **Fayl yaratish**: "buni PDF/Word qilib ber" desangiz, bot haqiqiy
  `.pdf` yoki `.docx` fayl generatsiya qilib, to'g'ridan-to'g'ri
  Telegram orqali yuboradi. "Buni operatorga PDF qilib yubor"
  desangiz esa, fayl guruhda o'sha xodimga @mention qilib yuboriladi.
- **Rasm yaratish**: Dizaynerga (yoki istalgan botga) "rasm chizib
  ber", "banner tayyorla" desangiz, AI orqali haqiqiy rasm generatsiya
  qilinib yuboriladi. Xodimga yuborish ham xuddi fayl kabi ishlaydi
  ("bu rasmni operatorga yubor").
- **Havolalar (linklar)**: xabaringizda oddiy veb-sahifa havolasi
  (blog, yangilik, kompaniya sayti va h.k.) bo'lsa, bot uni ochib,
  sarlavha va matnini o'qib, shunga qarab javob beradi. Instagram,
  Facebook, TikTok, YouTube, Twitter/X kabi saytlar bundan mustasno —
  ular login/JavaScript talab qilgani uchun ochilmaydi; bunday
  holatlarda faylni/rasmni/videoni to'g'ridan-to'g'ri yuklab yuboring.
- **YouTube'dan qiziqarli-kadrlar videosi (faqat Mobilograf)**:
  Mobilografga YouTube havolasini yuborib "buni yuklab, reel qilib "
  ber" desangiz — u videoni yuklaydi, AI vision orqali eng qiziqarli
  3 ta kadrni tanlaydi, professional dizaynli (raqamli belgi +
  sarlavha) 9:16 formatdagi qisqa videoni yig'ib, to'g'ridan-to'g'ri
  yuboradi. Video faylni to'g'ridan-to'g'ri yuborib ham xuddi shu
  so'rovni berish mumkin. Bu jarayon 1-3 daqiqa vaqt oladi.
  **MUHIM**: bu terminal/shell orqali emas, faqat ikkita qattiq
  belgilangan xavfsiz funksiya orqali ishlaydi — AI erkin buyruq
  yoza olmaydi.
- **Ovozli xabarlar**: botlarga ovozli xabar yuborsangiz, ular uni
  avtomatik matnga o'girib (Whisper orqali), tushunib, matn holida
  javob qaytaradi.
- **Xodimga xabar**: Direktorga (yoki istalgan bo'limga) "operatorga
  ayt..." desangiz, bot guruhda xodimni @username orqali mention
  qilib xabar yozadi va javobini kutib, kelgach sizga darhol yetkazadi
  (batafsili pastda).
- **Topic'lar (mavzular)**: agar guruhingizda Telegram Topics
  (Forum) yoqilgan bo'lsa va videodagidek har bir bo'lim uchun
  alohida topic ochgan bo'lsangiz, `topics_config.py` orqali har
  bir topicni tegishli botga bog'lab qo'yish mumkin — shunda o'sha
  topicda yozilgan har qanday xabarga (@mention shart emas) faqat
  o'sha bo'lim boti avtomatik javob beradi.

## Xodim qo'shish (fayl tahrirlash shart emas!)

Endi xodim qo'shish uchun GitHub'ga kirish kerak emas — to'g'ridan-to'g'ri
Direktorga (yoki istalgan boshqa botga) yozing, masalan:

> "Yangi xodim qo'sh: Akobir Tursunov, telefon +998901234567, sohasi —
> videograf, Telegram username'i @akobir_video"

Bot buni tushunib, avtomatik MongoDB'ga saqlaydi. Shundan keyin istalgan
bo'lim botiga "Akobirga ayt, ertaga soat 10da syomka bormi" desangiz —
bot **guruhda, @akobir_video'ni mention qilib** xabar yozadi (agar
o'sha botning o'z topici bo'lsa — shu topicda, aks holda umumiy
guruhda). Akobir o'sha yerda javob yozishi bilan, javob avtomatik
so'ragan odamga forward qilinadi.

**Muhim shart**: xodim mention orqali xabar ololishi uchun, u albatta
"Virtual Ofis" guruhingizning a'zosi bo'lishi kerak (guruhga oddiy
a'zo sifatida qo'shilgan bo'lishi kifoya, admin bo'lishi shart emas).

## Topic'larni botlarga bog'lash (ixtiyoriy, lekin tavsiya etiladi)

1. Guruh nomi ustiga bosib, sozlamalarga kiring, "Topics" (Mavzular)
   funksiyasini yoqing.
2. Har bir bo'lim uchun alohida topic yarating (masalan "Marketolog",
   "SMM", "Moliya" va h.k.).
3. Har bir topic ichida shunday yozing: `/topicid`
   Bot darhol o'sha joyning ID raqamini javob qilib beradi (barcha 6 ta
   bot ko'rishi mumkin bo'lgani uchun bir nechta bir xil javob kelishi
   mumkin — bu normal, faqat raqamga qarang).
4. GitHub'da `topics_config.py` faylini oching, `TOPIC_MAP` ichiga
   qo'shing:
   ```python
   TOPIC_MAP = {
       12: "marketolog",
       15: "smm",
       18: "moliya",
       21: "mobilograf",
       24: "dizayner",
       27: "direktor",
   }
   ```
   (Raqamlar — sizning topic ID'laringiz, o'ng tomondagi nom esa
   `agents_config.py`dagi agent kaliti bilan bir xil bo'lishi kerak.)
5. Commit qiling — Railway avtomatik qayta deploy qiladi.

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
