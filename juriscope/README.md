# Mizan – مساعد قانوني ذكي

> افهم موقفك القانوني بوضوح — مدعوم بالذكاء الاصطناعي

Mizan هو تطبيق FastAPI عربي RTL يساعد المستخدم على كتابة سؤاله القانوني، اختيار الدولة، نوع القضية، والباقة، ثم الحصول على تحليل قانوني منظم باستخدام Gemini API.

---

## المميزات الحالية

- اختيار الدولة: الأردن، السعودية، الإمارات، مصر، العراق، قطر، الكويت، البحرين، عُمان.
- اختيار نوع القضية: مدني، تجاري، عقود، شركات، عمالي، إيجارات، أحوال شخصية، جنائي، شيكات ومطالبات مالية، ملكية فكرية، إداري، أخرى.
- اختيار الباقة: المجانية، الأفراد، الأعمال، المحامون.
- دعم القضايا الجنائية بحذر من خلال "تقدير النطاق العقابي المحتمل في حال ثبوت الفعل".
- ملخص جاهز للمحامي.
- واجهة عربية RTL.
- جاهز للنشر على Render.

---

## متطلبات التشغيل

- Python 3.9 أو أحدث
- Gemini API Key من Google AI Studio
- اتصال بالإنترنت

---

## ملف البيئة `.env`

أنشئ ملفًا باسم `.env` بجانب `main.py` واكتب:

```env
GEMINI_API_KEY=ضع_مفتاح_Gemini_هنا
GEMINI_MODEL=gemini-2.5-flash
```

لا ترفع ملف `.env` إلى GitHub.

---

## تشغيل المشروع محليًا

### Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

إذا ظهر خطأ في تفعيل البيئة الافتراضية:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### Mac / Linux

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## فتح الموقع

بعد التشغيل افتح:

```text
http://127.0.0.1:8000
```

صفحة المساعد:

```text
http://127.0.0.1:8000/assistant
```

---

## هيكل المشروع

```text
Mizan/
├── main.py
├── requirements.txt
├── README.md
├── app/
│   ├── routes/
│   │   ├── pages.py
│   │   └── api.py
│   ├── schemas/
│   │   └── legal.py
│   ├── services/
│   │   └── ai_service.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── assistant.html
│   │   ├── features.html
│   │   └── use_cases.html
│   └── static/
│       ├── css/style.css
│       └── js/assistant.js
```

---

## النشر على Render

إذا كان المشروع داخل مجلد داخلي اسمه `Mizan` داخل GitHub:

### الخيار الأول

اترك Root Directory فاضيًا، واستخدم:

```bash
cd Mizan && pip install -r requirements.txt
```

Start Command:

```bash
cd Mizan && uvicorn main:app --host 0.0.0.0 --port $PORT
```

### الخيار الثاني

ضع Root Directory:

```text
Mizan
```

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Environment Variables في Render

أضف:

```env
GEMINI_API_KEY=مفتاح_Gemini_الحقيقي
GEMINI_MODEL=gemini-2.5-flash
```

---

## تنبيه قانوني

يوفر Mizan معلومات وتحليلات قانونية مساعدة لأغراض معرفية وتنظيمية فقط، ولا يُعد استشارة قانونية نهائية ولا ينشئ علاقة محامٍ وموكل. يجب دائمًا مراجعة محامٍ مرخص قبل اتخاذ أي إجراء قانوني.

## تحليل المستندات القانونية

تمت إضافة endpoint جديد:

```text
POST /api/analyze-document
```

يدعم رفع الملفات التالية:

- PDF، بما في ذلك PDF الممسوح Scanner PDF عبر Gemini document understanding
- JPG / JPEG
- PNG
- WEBP

الحد الحالي للملف: 10MB.

يعتمد التحليل على Gemini، لذلك يجب إضافة المتغيرات التالية محليًا في `.env` أو في Render Environment Variables:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```
