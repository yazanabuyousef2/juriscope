استبدل الملف التالي فقط:
app/routes/internal_legal.py

ثم ثبّت pdfplumber إذا لم يكن مثبتًا:
pip install pdfplumber

وأضف إلى requirements.txt:
pdfplumber

بعدها شغّل:
python main.py

ثم احذف رفع قانون البنك المركزي السابق وأعد رفعه من جديد.
هذا التعديل يعالج مشكلة ترتيب النص العربي في PDF ديوان التشريع والرأي، مثل عكس 1 و31 في المادة 59.
