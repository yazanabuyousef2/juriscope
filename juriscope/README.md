# Juriscope – مساعد قانوني ذكي

> افهم موقفك القانوني بوضوح — مدعوم بالذكاء الاصطناعي

---

## 📋 متطلبات التشغيل

- Python 3.9 أو أحدث
- اتصال بالإنترنت (لتحميل Tailwind CSS و Google Fonts)

---

## 🚀 تشغيل المشروع محلياً

### Windows

```powershell
# 1. إنشاء البيئة الافتراضية
python -m venv venv

# 2. تفعيل البيئة الافتراضية
.\venv\Scripts\Activate.ps1

# إذا ظهر خطأ في التفعيل، شغّل هذا الأمر أولاً:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 3. تثبيت المكتبات
pip install -r requirements.txt

# 4. تشغيل المشروع
python main.py
```

### Mac / Linux

```bash
# 1. إنشاء البيئة الافتراضية
python3 -m venv venv

# 2. تفعيل البيئة الافتراضية
source venv/bin/activate

# 3. تثبيت المكتبات
pip install -r requirements.txt

# 4. تشغيل المشروع
python main.py
```

---

## 🌐 فتح الموقع

بعد التشغيل، افتح المتصفح واذهب إلى:

```
http://127.0.0.1:8000
```

---

## 📁 هيكل المشروع

```
juriscope/
├── main.py                         # نقطة الدخول الرئيسية
├── requirements.txt                # مكتبات Python
├── README.md
│
└── app/
    ├── routes/
    │   ├── pages.py                # مسارات الصفحات (HTML)
    │   └── api.py                  # مسارات API
    │
    ├── services/
    │   └── ai_service.py           # منطق الذكاء الاصطناعي (ديمو)
    │
    ├── schemas/
    │   └── legal.py                # نماذج Pydantic
    │
    ├── templates/
    │   ├── base.html               # القالب الأساسي (RTL)
    │   ├── index.html              # الصفحة الرئيسية
    │   ├── assistant.html          # صفحة المساعد القانوني
    │   ├── features.html           # صفحة المميزات
    │   └── use_cases.html          # صفحة حالات الاستخدام
    │
    └── static/
        ├── css/style.css           # أنماط CSS
        └── js/assistant.js         # JavaScript للمساعد
```

---

## 🔌 ربط الذكاء الاصطناعي الحقيقي لاحقاً

افتح الملف `app/services/ai_service.py` واستبدل محتوى الدالة:

```python
async def analyze_legal_question(question: str) -> AnalyzeResponse:
```

بكود OpenAI أو RAG حسب حاجتك. التعليمات موجودة داخل الملف.

---

## 🌍 نشر مجاني (Render.com)

1. ارفع المشروع على GitHub
2. اذهب إلى [render.com](https://render.com) وأنشئ حساباً مجانياً
3. اختر "New Web Service" وربطه بـ GitHub repo
4. اضبط:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
5. انتظر حتى يكتمل النشر

---

## ⚠️ تنبيه قانوني

يوفر Juriscope معلومات وتحليلات قانونية مساعدة لأغراض معرفية وتنظيمية فقط،
ولا يُعد استشارة قانونية نهائية ولا ينشئ علاقة محامٍ وموكل.
يجب دائمًا مراجعة محامٍ مرخص قبل اتخاذ أي إجراء قانوني.
