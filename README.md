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
   bo'ladi. `railpack.json` fayli tufayli Railway avtomatik `ffmpeg`
   va shriftlarni ham o'rnatadi (video montaj funksiyasi uchun) —
   bu bosqich birinchi deploy'da 1-2 daqiqa qo'shimcha vaqt olishi
   mumkin, alohida sozlash shart emas.
   (Eslatma: agar loyihada eski `nixpacks.toml` fayli qolgan bo'lsa,
   uni o'chirib tashlashingiz mumkin — Railway hozir shu maqsad uchun
   `railpack.json`dan foydalanadi.)

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
  ber" desangiz — u videoni yuklaydi, so'ng **video mazmuniga qarab
  mustaqil ravishda**: eng mos formatni (9:16 Reels/TikTok, 1:1
  kvadrat post, 16:9 YouTube/landshaft, 4:5 Instagram post), eng mos
  uslubni (energetik raqamli-belgili, toza-minimalist, yoki
  kinematik-letterbox), nechta lahza kerakligini (2-6 ta) va har
  bir lahza uchun ranglarni **o'zi tanlaydi** — bu qattiq bitta
  shablon emas, har safar boshqacha natija bo'lishi mumkin. Aniq
  format/uslub xohlasangiz ("kvadrat qilib", "16:9 qilib", "energetik
  uslubda"), shuni so'rovingizda ayting — tizim shunga amal qiladi.
  Video faylni to'g'ridan-to'g'ri yuborib ham xuddi shu so'rovni
  berish mumkin. Bu jarayon 1-3 daqiqa vaqt oladi.
  **MUHIM**: bu terminal/shell orqali emas, faqat qattiq belgilangan
  xavfsiz funksiyalar orqali ishlaydi — AI erkin buyruq yoza olmaydi,
  faqat format/uslub/rang kabi PARAMETRLARNI tanlaydi.
  YouTube'ning "bot-himoyasi" (Sign in to confirm...)ni yengish uchun
  tizim avtomatik ravishda maxsus yordamchi server (PoToken provider)
  ishga tushiradi — bu birinchi marta ishga tushganda 30-60 soniya
  qo'shimcha vaqt olishi mumkin, keyingi yuklashlar tezroq bo'ladi.
  Agar hali ham "sign in" xatosi chiqsa, `YOUTUBE_COOKIES`
  o'zgaruvchisini sozlash tavsiya etiladi (yuqoridagi bo'limga qarang).
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

## YouTube "tizimga kirish" xatosini tuzatish (ixtiyoriy)

Ba'zi YouTube videolarini yuklashda `Please sign in` xatosi chiqishi
mumkin — bu YouTube'ning bulut-serverlardan (Railway kabi) kelgan
so'rovlarni "shubhali" deb hisoblab qo'yadigan bot-himoyasi, xatolik
emas. Buni tuzatish uchun haqiqiy YouTube hisobingizning cookies
faylini berish kerak:

1. Kompyuteringizda Chrome brauzerida youtube.com'ga kiring (hisobingiz
   bilan).
2. Chrome Web Store'dan **"Get cookies.txt LOCALLY"** kengaytmasini
   o'rnating.
3. youtube.com sahifasida turib, kengaytma belgisini bosing va
   "Export" / "Download" tugmasini bosing — `cookies.txt` fayli
   yuklanadi.
4. Shu faylni matn muharriri (TextEdit/Notepad) bilan oching, **butun
   matnini** nusxalab oling.
5. Railway'da Variables bo'limiga o'ting, yangi o'zgaruvchi qo'shing:
   `YOUTUBE_COOKIES` — qiymat qismiga nusxalangan matnni to'liq
   joylashtiring.
6. Saqlang — Railway avtomatik qayta deploy qiladi. Shundan keyin
   "tizimga kirish" talab qiladigan videolar ham yuklanishi kerak.

**Eslatma**: cookies faylida sizning YouTube sessiyangiz haqida
ma'lumot bor — uni hech kim bilan bulashmang, faqat Railway
Variables'ning o'ziga joylashtiring.

## YouTube bot-himoyasini kuchliroq yengish: PoToken xizmati (ixtiyoriy, ilg'or)

Agar cookie qo'shgandan keyin ham ba'zi videolar "sign in"/"format
not available" xatosini bersa, buning sababi YouTube'ning yanada
kuchli himoyasi ("PoToken" talabi) bo'lishi mumkin. Buni **alohida,
mustaqil Railway xizmati** sifatida qo'shish orqali yengish mumkin
(bu asosiy bot xizmatingizga HECH QANDAY ta'sir qilmaydi — butunlay
boshqa konteynerda ishlaydi):

1. Railway loyihangizda (xuddi shu project ichida, yangi/alohida
   emas) **"+ New"** → **"Empty Service"** ni tanlang.
2. Xizmatga nom bering: aynan **`bgutil-provider`** deb yozing (nom
   muhim — keyingi qadamda shu nom ishlatiladi).
3. Shu xizmatning Settings → Source bo'limida **"Docker Image"**ni
   tanlang, manzil sifatida yozing: `brainicism/bgutil-ytdlp-pot-provider`
4. Networking bo'limida ichki portni **4416** deb belgilang (faqat
   ichki/private tarmoq uchun, tashqi domenga chiqarish shart emas).
5. Deploy bo'lishini kuting (bu — tayyor Docker rasm, qurish shart
   emas, tez ishga tushadi).
6. Asosiy bot xizmatingizga (worker) qayting, Variables bo'limiga
   yangi o'zgaruvchi qo'shing:
   `POT_PROVIDER_URL` = `http://bgutil-provider.railway.internal:4416`
7. Saqlang — Railway asosiy xizmatni qayta deploy qiladi. Shundan
   keyin video yuklash avtomatik ravishda shu yordamchi xizmatdan
   foydalanadi.

**Eslatma**: agar 2-qadamda xizmatga boshqa nom bergan bo'lsangiz,
6-qadamdagi manzilda ham aynan o'sha nomni ishlating (masalan nom
"pot-server" bo'lsa, manzil `http://pot-server.railway.internal:4416`
bo'ladi).

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
