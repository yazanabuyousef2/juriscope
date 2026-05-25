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
const loadingMessage = document.getElementById("loading-message");
const newAnalysisBtn = document.getElementById("new-analysis-btn");
const copySummaryBtn = document.getElementById("copy-summary-btn");
const exampleBtns = document.querySelectorAll(".example-btn");

const countrySelect = document.getElementById("country-select");
const caseTypeSelect = document.getElementById("case-type-select");
const planSelect = document.getElementById("plan-select");
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

function selectValue(el, fallback = "") {
  if (!el) return fallback;
  const value = el.value || "";
  if (value.includes("؟")) return fallback;
  return value;
}

function updateCriminalPanel() {
  if (!criminalPanel || !caseTypeSelect) return;
  if (caseTypeSelect.value === "جنائي") {
    criminalPanel.classList.remove("hidden");
  } else {
    criminalPanel.classList.add("hidden");
  }
}

caseTypeSelect?.addEventListener("change", updateCriminalPanel);
updateCriminalPanel();

questionInput?.addEventListener("input", () => {
  charCount.textContent = `${questionInput.value.length} حرف`;
});

const urlQ = new URLSearchParams(window.location.search).get("q");
if (urlQ && questionInput) {
  questionInput.value = urlQ;
  charCount.textContent = `${urlQ.length} حرف`;
}

exampleBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const text = btn.textContent.trim();
    questionInput.value = text;
    charCount.textContent = `${text.length} حرف`;
    questionInput.focus();

    if (text.includes("جريمة") || text.includes("اتهامي")) {
      caseTypeSelect.value = "جنائي";
      updateCriminalPanel();
    }
  });
});

function showState(state) {
  emptyState?.classList.add("hidden");
  loadingState?.classList.add("hidden");
  resultState?.classList.add("hidden");

  if (state === "empty") emptyState?.classList.remove("hidden");
  if (state === "loading") loadingState?.classList.remove("hidden");
  if (state === "result") resultState?.classList.remove("hidden");
}

let loadingInterval = null;

function startLoadingMessages(messages = LOADING_MESSAGES) {
  let i = 0;
  loadingMessage.textContent = messages[0];
  loadingInterval = setInterval(() => {
    i = (i + 1) % messages.length;
    loadingMessage.textContent = messages[i];
  }, 1500);
}

function stopLoadingMessages() {
  if (loadingInterval) {
    clearInterval(loadingInterval);
    loadingInterval = null;
  }
}

function renderList(elId, items, colorClass = "bg-slate-500") {
  const el = document.getElementById(elId);
  if (!el) return;
  el.innerHTML = "";

  if (!Array.isArray(items) || items.length === 0) {
    const li = document.createElement("li");
    li.className = "text-xs text-slate-500";
    li.textContent = "لا توجد نقاط مذكورة.";
    el.appendChild(li);
    return;
  }

  items.forEach((item) => {
    const li = document.createElement("li");
    li.className = "flex items-start gap-2 text-xs text-slate-300 leading-relaxed";
    li.innerHTML = `<div class="w-1.5 h-1.5 rounded-full ${colorClass} mt-1.5 shrink-0"></div><span>${escapeHTML(String(item))}</span>`;
    el.appendChild(li);
  });
}

function renderOrderedList(elId, items) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.innerHTML = "";

  if (!Array.isArray(items) || items.length === 0) {
    const li = document.createElement("li");
    li.className = "text-xs text-slate-500";
    li.textContent = "لا توجد خطوات مذكورة.";
    el.appendChild(li);
    return;
  }

  items.forEach((item, idx) => {
    const li = document.createElement("li");
    li.className = "flex items-start gap-3 text-xs text-slate-300 leading-relaxed";
    li.innerHTML = `
      <span class="shrink-0 w-5 h-5 rounded-full bg-green-500/20 text-green-400 text-xs flex items-center justify-center font-bold">${idx + 1}</span>
      <span>${escapeHTML(String(item))}</span>`;
    el.appendChild(li);
  });
}

function renderSimilarCases(cases) {
  const el = document.getElementById("res-similar-cases");
  if (!el) return;
  el.innerHTML = "";

  if (!Array.isArray(cases) || cases.length === 0) {
    el.innerHTML = `<p class="text-xs text-slate-500">لا توجد حالات مشابهة مذكورة.</p>`;
    return;
  }

  cases.forEach((c) => {
    const div = document.createElement("div");
    div.className = "bg-white/5 rounded-xl p-4 border border-white/5";
    div.innerHTML = `
      <div class="flex items-center justify-between gap-3 mb-2">
        <span class="text-xs font-semibold text-white">${escapeHTML(c.title || "")}</span>
        <span class="px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 text-xs border border-green-500/20">${escapeHTML(c.similarity || "")}</span>
      </div>
      <div class="text-xs text-slate-400 mb-1"><span class="text-slate-500">المبدأ:</span> ${escapeHTML(c.principle || "")}</div>
      <div class="text-xs text-slate-400"><span class="text-slate-500">سبب الصلة:</span> ${escapeHTML(c.why_relevant || "")}</div>
    `;
    el.appendChild(div);
  });
}

function renderPenaltyEstimate(estimate) {
  const card = document.getElementById("criminal-penalty-card");
  if (!card) return;

  if (!estimate || estimate.show !== true) {
    card.classList.add("hidden");
    return;
  }

  card.classList.remove("hidden");
  document.getElementById("res-alleged-crime").textContent = estimate.alleged_crime || "غير محدد";
  document.getElementById("res-penalty-range").textContent = estimate.possible_penalty_range || "غير محدد بدقة دون مراجعة النص القانوني الرسمي.";
  document.getElementById("res-penalty-warning").textContent = estimate.important_warning || "هذا تقدير عام وليس حكمًا نهائيًا.";

  renderList("res-penalty-increase", estimate.factors_that_may_increase_penalty, "bg-red-400");
  renderList("res-penalty-reduce", estimate.factors_that_may_reduce_penalty, "bg-green-400");
}

function hideDocumentResult() {
  const card = document.getElementById("document-result-card");
  card?.classList.add("hidden");
}

function renderDocumentResult(data) {
  const card = document.getElementById("document-result-card");
  if (card) card.classList.remove("hidden");

  document.getElementById("doc-res-type").textContent = data.document_type || "مستند قانوني";
  document.getElementById("doc-res-risk-level").textContent = data.risk_level || "غير محدد";
  document.getElementById("doc-res-summary").textContent = data.summary || "";

  renderList("doc-res-parties", data.parties, "bg-slate-400");
  renderList("doc-res-obligations", data.main_obligations, "bg-blue-400");
  renderList("doc-res-risky", data.risky_clauses, "bg-red-400");
  renderList("doc-res-gaps", data.legal_gaps, "bg-yellow-400");
  renderList("doc-res-missing", data.missing_clauses, "bg-purple-400");
  renderList("doc-res-edits", data.suggested_edits, "bg-green-400");

  document.getElementById("res-short-answer").textContent = data.summary || "تم تحليل المستند.";
  document.getElementById("res-country-context").textContent = data.country_context || "";
  document.getElementById("res-case-understanding").textContent = (data.parties || []).join("، ") || "تمت قراءة المستند المرفق.";
  document.getElementById("res-legal-classification").textContent = data.document_type || "تحليل مستند قانوني";
  document.getElementById("res-lawyer-summary").textContent = data.lawyer_summary || "";
  document.getElementById("res-disclaimer").textContent = data.disclaimer || "";

  renderPenaltyEstimate(null);
  renderList("res-key-risks", data.risky_clauses, "bg-red-400");
  renderList("res-relevant-documents", data.missing_clauses, "bg-blue-400");
  renderOrderedList("res-next-steps", data.suggested_edits);
  renderSimilarCases([]);

  showState("result");
  resultState.classList.add("fade-in");
}

function renderResult(data) {
  hideDocumentResult();
  document.getElementById("res-short-answer").textContent = data.short_answer || "";
  document.getElementById("res-country-context").textContent = data.country_context || "";
  document.getElementById("res-case-understanding").textContent = data.case_understanding || "";
  document.getElementById("res-legal-classification").textContent = data.legal_classification || "";
  document.getElementById("res-lawyer-summary").textContent = data.lawyer_summary || "";
  document.getElementById("res-disclaimer").textContent = data.disclaimer || "";

  renderPenaltyEstimate(data.criminal_penalty_estimate);
  renderList("res-key-risks", data.key_risks, "bg-red-400");
  renderList("res-relevant-documents", data.relevant_documents, "bg-blue-400");
  renderOrderedList("res-next-steps", data.next_steps);
  renderSimilarCases(data.similar_cases);

  showState("result");
  resultState.classList.add("fade-in");
}

function getCriminalDetails() {
  return {
    alleged_crime: criminalFields.alleged_crime?.value.trim() || "",
    has_prior_record: selectValue(criminalFields.has_prior_record, "غير معروف"),
    prior_count: criminalFields.prior_count?.value.trim() || "",
    confession: selectValue(criminalFields.confession, "غير معروف"),
    witnesses: selectValue(criminalFields.witnesses, "غير معروف"),
    harm: selectValue(criminalFields.harm, "غير معروف"),
    mitigating_factors: criminalFields.mitigating_factors?.value.trim() || "",
    aggravating_factors: criminalFields.aggravating_factors?.value.trim() || "",
  };
}

async function analyzeQuestion() {
  const question = questionInput.value.trim();

  if (question.length < 10) {
    alert("يرجى كتابة سؤال أكثر تفصيلًا، لا يقل عن 10 أحرف.");
    questionInput.focus();
    return;
  }

  const caseType = caseTypeSelect.value;
  const payload = {
    question,
    country: countrySelect.value,
    case_type: caseType,
    plan: planSelect.value,
    criminal_details: caseType === "جنائي" ? getCriminalDetails() : null,
  };

  analyzeBtn.disabled = true;
  showState("loading");
  startLoadingMessages(LOADING_MESSAGES);

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const err = await response.json();
        if (err.detail) message = err.detail;
      } catch (_) {}
      throw new Error(message);
    }

    const data = await response.json();
    stopLoadingMessages();
    renderResult(data);
  } catch (err) {
    stopLoadingMessages();
    showState("empty");

    if (err instanceof TypeError) {
      alert("حدث خطأ في الاتصال. يرجى التأكد من اتصالك بالإنترنت والمحاولة مرة أخرى.");
    } else {
      alert(`حدث خطأ أثناء التحليل. ${err.message || "يرجى المحاولة مرة أخرى."}`);
    }
  } finally {
    analyzeBtn.disabled = false;
  }
}

async function analyzeDocument() {
  const file = documentFileInput?.files?.[0];
  if (!file) {
    alert("يرجى اختيار ملف PDF أو صورة لتحليلها.");
    return;
  }

  if (file.size > 10 * 1024 * 1024) {
    alert("الملف كبير جدًا. الحد الحالي 10MB. يرجى رفع ملف أصغر أو نسخة مختصرة.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("country", countrySelect.value);
  formData.append("document_type", documentTypeSelect.value);
  formData.append("plan", planSelect.value);
  formData.append("question", documentQuestionInput?.value.trim() || "");

  analyzeDocumentBtn.disabled = true;
  showState("loading");
  startLoadingMessages(DOCUMENT_LOADING_MESSAGES);

  try {
    const response = await fetch("/api/analyze-document", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const err = await response.json();
        if (err.detail) message = err.detail;
      } catch (_) {}
      throw new Error(message);
    }

    const data = await response.json();
    stopLoadingMessages();
    renderDocumentResult(data);
  } catch (err) {
    stopLoadingMessages();
    showState("empty");

    if (err instanceof TypeError) {
      alert("حدث خطأ في الاتصال أثناء رفع المستند. يرجى المحاولة مرة أخرى.");
    } else {
      alert(`حدث خطأ أثناء تحليل المستند. ${err.message || "يرجى المحاولة مرة أخرى."}`);
    }
  } finally {
    analyzeDocumentBtn.disabled = false;
  }
}

analyzeBtn?.addEventListener("click", analyzeQuestion);
analyzeDocumentBtn?.addEventListener("click", analyzeDocument);

questionInput?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    analyzeQuestion();
  }
});

newAnalysisBtn?.addEventListener("click", () => {
  questionInput.value = "";
  charCount.textContent = "0 حرف";
  hideDocumentResult();
  showState("empty");
  questionInput.focus();
  resultState.classList.remove("fade-in");
});

copySummaryBtn?.addEventListener("click", async () => {
  const text = document.getElementById("res-lawyer-summary").textContent;
  try {
    await navigator.clipboard.writeText(text);
    copySummaryBtn.innerHTML = `
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
      </svg>
      تم النسخ!`;
    setTimeout(() => {
      copySummaryBtn.innerHTML = `
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
        </svg>
        نسخ`;
    }, 2000);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
});

const revealEls = document.querySelectorAll(".reveal");
if (revealEls.length) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) e.target.classList.add("visible");
    });
  }, { threshold: 0.1 });
  revealEls.forEach((el) => observer.observe(el));
}
