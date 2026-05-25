# Mizan — مساعد قانوني ذكي

نسخة مطورة تشمل:

- إنشاء حساب وتسجيل دخول وتسجيل خروج.
- حماية المساعد القانوني وتحليل المستندات؛ لا يمكن الاستخدام قبل تسجيل الدخول.
- باقات داخلية مع حدود استخدام شهرية.
- صفحة ملف شخصي تعرض الباقة والاستخدام.
- نظام قضايا: إنشاء قضية، حفظ الأسئلة، حفظ المستندات، ملاحظات خاصة، ومستجدات جلسات.
- تحليل الأسئلة القانونية حسب الدولة ونوع القضية.
- تحليل مستندات قانونية، بما فيها PDF الممسوح Scanner PDF، باستخدام Gemini.
- واجهة عربية RTL.

## التشغيل محليًا على Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

إذا منع PowerShell تفعيل البيئة:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

افتح:

```text
http://127.0.0.1:8000
```

## ملف البيئة .env

أنشئ ملف `.env` بجانب `main.py`:

```env
GEMINI_API_KEY=ضع_مفتاح_Gemini_هنا
GEMINI_MODEL=gemini-2.5-flash
```

لا ترفع `.env` إلى GitHub.

## النشر على Render

إذا كانت ملفات المشروع داخل مجلد داخلي اسمه `juriscope` داخل المستودع:

**Build Command**

```bash
cd juriscope && pip install -r requirements.txt
```

**Start Command**

```bash
cd juriscope && uvicorn main:app --host 0.0.0.0 --port $PORT
```

أضف Environment Variables في Render:

```env
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
```

## ملاحظة مهمة

قاعدة البيانات الافتراضية SQLite مناسبة للتجربة. للإطلاق الحقيقي وحفظ بيانات العملاء والقضايا بشكل موثوق، استخدم PostgreSQL أو Supabase.
