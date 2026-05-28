"use strict";

const LOADING_MESSAGES = [
  "جاري تحليل حالتك القانونية...",
  "جاري تحديد أثر الدولة المختارة...",
  "جاري مراجعة نوع القضية والباقة...",
  "جاري البحث عن حالات مشابهة...",
  "جاري تجهيز ملخص مناسب للمحامي...",
];

const DOCUMENT_LOADING_MESSAGES = [
  "جاري رفع المستند وقراءته...",
  "جاري تحليل الصفحات الممسوحة...",
  "جاري استخراج البنود والالتزامات...",
  "جاري البحث عن الثغرات القانونية...",
  "جاري تجهيز ملخص مناسب للمحامي...",
];

const questionInput = document.getElementById("question-input");
const charCount = document.getElementById("char-count");
const analyzeBtn = document.getElementById("analyze-btn");
const emptyState = document.getElementById("empty-state");
const loadingState = document.getElementById("loading-state");
const resultState = document.getElementById("result-state");
const documentResultState = document.getElementById("document-result-state");
const loadingMessage = document.getElementById("loading-message");
const newAnalysisBtn = document.getElementById("new-analysis-btn");
const copySummaryBtn = document.getElementById("copy-summary-btn");

const countrySelect = document.getElementById("country-select");
const caseTypeSelect = document.getElementById("case-type-select");
const caseIdSelect = document.getElementById("case-id-select");
const criminalPanel = document.getElementById("criminal-details-panel");

const documentTypeSelect = document.getElementById("document-type-select");
const documentFileInput = document.getElementById("document-file-input");
const documentQuestionInput = document.getElementById("document-question-input");
const analyzeDocumentBtn = document.getElementById("analyze-document-btn");

const criminalFields = {
  alleged_crime: document.getElementById("alleged-crime-input"),
  has_prior_record: document.getElementById("has-prior-record-select"),
  prior_count: document.getElementById("prior-count-input"),
  confession: document.getElementById("confession-select"),
  witnesses: document.getElementById("witnesses-select"),
  harm: document.getElementById("harm-select"),
  mitigating_factors: document.getElementById("mitigating-factors-input"),
  aggravating_factors: document.getElementById("aggravating-factors-input"),
};

function escapeHTML(str) {
  if (typeof str !== "string") return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function valueOf(el, fallback = "") {
  return el && el.value ? el.value : fallback;
}

function selectedCaseId() {
  const val = valueOf(caseIdSelect, "");
  return val ? Number(val) : null;
}

function updateCriminalPanel() {
  if (!criminalPanel || !caseTypeSelect) return;
  if (caseTypeSelect.value === "جنائي") criminalPanel.classList.remove("hidden");
  else criminalPanel.classList.add("hidden");
}

caseTypeSelect?.addEventListener("change", updateCriminalPanel);
updateCriminalPanel();

questionInput?.addEventListener("input", () => {
  charCount.textContent = `${questionInput.value.length} حرف`;
});

function showState(state) {
  emptyState?.classList.add("hidden");
  loadingState?.classList.add("hidden");
  resultState?.classList.add("hidden");
  documentResultState?.classList.add("hidden");

  if (state === "empty") emptyState?.classList.remove("hidden");
  if (state === "loading") loadingState?.classList.remove("hidden");
  if (state === "result") resultState?.classList.remove("hidden");
  if (state === "document") documentResultState?.classList.remove("hidden");
}

function cycleMessages(messages) {
  let i = 0;
  if (loadingMessage) loadingMessage.textContent = messages[0];
  return setInterval(() => {
    i = (i + 1) % messages.length;
    if (loadingMessage) loadingMessage.textContent = messages[i];
  }, 1600);
}

function listItems(items) {
  if (!Array.isArray(items) || !items.length) return "<li>غير محدد.</li>";
  return items.map((item) => `<li class="flex gap-2"><span class="text-gold-400">•</span><span>${escapeHTML(String(item))}</span></li>`).join("");
}

function renderResults(data) {
  document.getElementById("res-short-answer").textContent = data.short_answer || "";
  document.getElementById("res-country-context").textContent = data.country_context || "";
  document.getElementById("res-classification").textContent = data.legal_classification || "";
  document.getElementById("res-understanding").textContent = data.case_understanding || "";
  document.getElementById("res-risks").innerHTML = listItems(data.key_risks);
  document.getElementById("res-documents").innerHTML = listItems(data.relevant_documents);
  document.getElementById("res-next-steps").innerHTML = Array.isArray(data.next_steps)
    ? data.next_steps.map((s, i) => `<li class="flex gap-3"><span class="text-gold-400 font-semibold">${i + 1}</span><span>${escapeHTML(String(s))}</span></li>`).join("")
    : "";
  document.getElementById("res-lawyer-summary").textContent = data.lawyer_summary || "";
  document.getElementById("res-disclaimer").textContent = data.disclaimer || "";

  const casesWrap = document.getElementById("res-similar-cases");
  casesWrap.innerHTML = "";
  (data.similar_cases || []).forEach((c) => {
    const div = document.createElement("div");
    div.className = "rounded-xl border border-white/10 bg-white/5 p-4";
    div.innerHTML = `
      <div class="flex items-start justify-between gap-3 mb-2">
        <div class="font-semibold text-white">${escapeHTML(c.title || "حالة مشابهة")}</div>
        <div class="text-xs text-gold-400">${escapeHTML(c.similarity || "")}</div>
      </div>
      <div class="text-sm text-gold-300 mb-2">${escapeHTML(c.principle || "")}</div>
      <div class="text-sm text-slate-400 leading-relaxed">${escapeHTML(c.why_relevant || "")}</div>
    `;
    casesWrap.appendChild(div);
  });

  const penalty = data.criminal_penalty_estimate || {};
  const penaltyCard = document.getElementById("criminal-result-card");
  const penaltyWrap = document.getElementById("res-criminal-penalty");
  if (penalty.show) {
    penaltyCard.classList.remove("hidden");
    penaltyWrap.innerHTML = `
      <div><span class="text-slate-400">الفعل المنسوب:</span> ${escapeHTML(penalty.alleged_crime || "")}</div>
      <div><span class="text-slate-400">النطاق العقابي المحتمل:</span> ${escapeHTML(penalty.possible_penalty_range || "")}</div>
      <div><span class="text-slate-400">عوامل قد تشدد العقوبة:</span><ul class="mt-2 space-y-1">${listItems(penalty.factors_that_may_increase_penalty)}</ul></div>
      <div><span class="text-slate-400">عوامل قد تخفف العقوبة:</span><ul class="mt-2 space-y-1">${listItems(penalty.factors_that_may_reduce_penalty)}</ul></div>
      <div class="rounded-lg border border-red-500/20 bg-red-500/10 p-3">${escapeHTML(penalty.important_warning || "")}</div>
    `;
  } else {
    penaltyCard.classList.add("hidden");
    penaltyWrap.innerHTML = "";
  }

  showState("result");
}

async function analyzeQuestion() {
  const question = valueOf(questionInput, "").trim();
  if (question.length < 10) {
    alert("يرجى كتابة سؤال أكثر تفصيلًا، لا يقل عن 10 أحرف.");
    return;
  }

  const payload = {
    question,
    country: valueOf(countrySelect, "الأردن"),
    case_type: valueOf(caseTypeSelect, "أخرى"),
    case_id: selectedCaseId(),
    criminal_details: {
      alleged_crime: valueOf(criminalFields.alleged_crime, ""),
      has_prior_record: valueOf(criminalFields.has_prior_record, "غير معروف"),
      prior_count: valueOf(criminalFields.prior_count, ""),
      confession: valueOf(criminalFields.confession, "غير معروف"),
      witnesses: valueOf(criminalFields.witnesses, "غير معروف"),
      harm: valueOf(criminalFields.harm, "غير معروف"),
      mitigating_factors: valueOf(criminalFields.mitigating_factors, ""),
      aggravating_factors: valueOf(criminalFields.aggravating_factors, ""),
    },
  };

  showState("loading");
  analyzeBtn.disabled = true;
  const interval = cycleMessages(LOADING_MESSAGES);

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "حدث خطأ أثناء التحليل.");
    renderResults(data);
  } catch (err) {
    alert(err.message || "حدث خطأ أثناء التحليل. يرجى المحاولة مرة أخرى.");
    showState("empty");
  } finally {
    clearInterval(interval);
    analyzeBtn.disabled = false;
  }
}

function renderDocumentResult(data) {
  document.getElementById("doc-summary").textContent = data.summary || "";
  document.getElementById("doc-parties").innerHTML = listItems(data.parties);
  document.getElementById("doc-obligations").innerHTML = listItems(data.main_obligations);
  document.getElementById("doc-risky").innerHTML = listItems(data.risky_clauses);
  document.getElementById("doc-gaps").innerHTML = listItems(data.legal_gaps);
  document.getElementById("doc-missing").innerHTML = listItems(data.missing_clauses);
  document.getElementById("doc-edits").innerHTML = listItems(data.suggested_edits);
  document.getElementById("doc-risk-level").textContent = data.risk_level || "غير محدد";
  document.getElementById("doc-lawyer-summary").textContent = data.lawyer_summary || "";
  showState("document");
}

async function analyzeDocument() {
  const file = documentFileInput?.files?.[0];
  if (!file) {
    alert("يرجى اختيار ملف PDF أو صورة لتحليلها.");
    return;
  }

  const form = new FormData();
  form.append("file", file);
  form.append("country", valueOf(countrySelect, "الأردن"));
  form.append("document_type", valueOf(documentTypeSelect, "مستند قانوني"));
  form.append("question", valueOf(documentQuestionInput, ""));
  const caseId = selectedCaseId();
  if (caseId) form.append("case_id", String(caseId));

  showState("loading");
  analyzeDocumentBtn.disabled = true;
  const interval = cycleMessages(DOCUMENT_LOADING_MESSAGES);

  try {
    const res = await fetch("/api/analyze-document", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "حدث خطأ أثناء تحليل المستند.");
    renderDocumentResult(data);
  } catch (err) {
    alert(err.message || "حدث خطأ أثناء تحليل المستند. يرجى المحاولة مرة أخرى.");
    showState("empty");
  } finally {
    clearInterval(interval);
    analyzeDocumentBtn.disabled = false;
  }
}

analyzeBtn?.addEventListener("click", analyzeQuestion);
analyzeDocumentBtn?.addEventListener("click", analyzeDocument);

questionInput?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) analyzeQuestion();
});

newAnalysisBtn?.addEventListener("click", () => {
  questionInput.value = "";
  charCount.textContent = "0 حرف";
  showState("empty");
});

copySummaryBtn?.addEventListener("click", async () => {
  const text = document.getElementById("res-lawyer-summary").textContent;
  try {
    await navigator.clipboard.writeText(text);
    copySummaryBtn.textContent = "تم النسخ!";
    setTimeout(() => (copySummaryBtn.textContent = "نسخ"), 1600);
  } catch {
    alert("لم يتم النسخ تلقائيًا.");
  }
});
