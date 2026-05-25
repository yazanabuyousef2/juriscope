'use strict';

// ── Loading messages ──────────────────────────────────────────────────────────
const LOADING_MESSAGES = [
  'جاري تحليل حالتك القانونية...',
  'جاري تحديد المبادئ القانونية ذات العلاقة...',
  'جاري البحث عن حالات مشابهة...',
  'جاري ترتيب التحليل...',
  'جاري تجهيز ملخص مناسب للمحامي...',
];

// ── DOM refs ──────────────────────────────────────────────────────────────────
const questionInput   = document.getElementById('question-input');
const charCount       = document.getElementById('char-count');
const analyzeBtn      = document.getElementById('analyze-btn');
const emptyState      = document.getElementById('empty-state');
const loadingState    = document.getElementById('loading-state');
const resultState     = document.getElementById('result-state');
const loadingMessage  = document.getElementById('loading-message');
const newAnalysisBtn  = document.getElementById('new-analysis-btn');
const copySummaryBtn  = document.getElementById('copy-summary-btn');
const exampleBtns     = document.querySelectorAll('.example-btn');

// ── Character counter ─────────────────────────────────────────────────────────
questionInput.addEventListener('input', () => {
  const len = questionInput.value.length;
  charCount.textContent = `${len} حرف`;
});

// ── Pre-fill from URL query (?q=...) ─────────────────────────────────────────
const urlQ = new URLSearchParams(window.location.search).get('q');
if (urlQ) {
  questionInput.value = urlQ;
  charCount.textContent = `${urlQ.length} حرف`;
}

// ── Example button click ──────────────────────────────────────────────────────
exampleBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const text = btn.textContent.trim();
    questionInput.value = text;
    charCount.textContent = `${text.length} حرف`;
    questionInput.focus();
  });
});

// ── Utility: escape HTML to prevent XSS ───────────────────────────────────────
function escapeHTML(str) {
  if (typeof str !== 'string') return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ── Show / hide states ────────────────────────────────────────────────────────
function showState(state) {
  emptyState.classList.add('hidden');
  loadingState.classList.add('hidden');
  resultState.classList.add('hidden');

  if (state === 'empty')   emptyState.classList.remove('hidden');
  if (state === 'loading') loadingState.classList.remove('hidden');
  if (state === 'result')  resultState.classList.remove('hidden');
}

// ── Loading message rotation ──────────────────────────────────────────────────
let loadingInterval = null;

function startLoadingMessages() {
  let i = 0;
  loadingMessage.textContent = LOADING_MESSAGES[0];
  loadingInterval = setInterval(() => {
    i = (i + 1) % LOADING_MESSAGES.length;
    loadingMessage.textContent = LOADING_MESSAGES[i];
  }, 1500);
}

function stopLoadingMessages() {
  if (loadingInterval) {
    clearInterval(loadingInterval);
    loadingInterval = null;
  }
}

// ── Render helpers ────────────────────────────────────────────────────────────
function renderList(elId, items, colorClass = 'bg-slate-500') {
  const el = document.getElementById(elId);
  el.innerHTML = '';
  if (!Array.isArray(items)) return;
  items.forEach(item => {
    const li = document.createElement('li');
    li.className = 'flex items-start gap-2 text-xs text-slate-300';
    li.innerHTML = `<div class="w-1.5 h-1.5 rounded-full ${colorClass} mt-1.5 shrink-0"></div><span>${escapeHTML(item)}</span>`;
    el.appendChild(li);
  });
}

function renderOrderedList(elId, items) {
  const el = document.getElementById(elId);
  el.innerHTML = '';
  if (!Array.isArray(items)) return;
  items.forEach((item, idx) => {
    const li = document.createElement('li');
    li.className = 'flex items-start gap-3 text-xs text-slate-300';
    li.innerHTML = `
      <span class="shrink-0 w-5 h-5 rounded-full bg-green-500/20 text-green-400 text-xs flex items-center justify-center font-bold">${idx + 1}</span>
      <span>${escapeHTML(item)}</span>`;
    el.appendChild(li);
  });
}

function renderSimilarCases(cases) {
  const el = document.getElementById('res-similar-cases');
  el.innerHTML = '';
  if (!Array.isArray(cases)) return;
  cases.forEach(c => {
    const div = document.createElement('div');
    div.className = 'bg-white/5 rounded-xl p-4 border border-white/5';
    div.innerHTML = `
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-semibold text-white">${escapeHTML(c.title || '')}</span>
        <span class="px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 text-xs border border-green-500/20">${escapeHTML(c.similarity || '')}</span>
      </div>
      <div class="text-xs text-slate-400 mb-1"><span class="text-slate-500">المبدأ:</span> ${escapeHTML(c.principle || '')}</div>
      <div class="text-xs text-slate-400"><span class="text-slate-500">سبب الصلة:</span> ${escapeHTML(c.why_relevant || '')}</div>
    `;
    el.appendChild(div);
  });
}

// ── Render full response ──────────────────────────────────────────────────────
function renderResult(data) {
  document.getElementById('res-short-answer').textContent         = data.short_answer || '';
  document.getElementById('res-case-understanding').textContent   = data.case_understanding || '';
  document.getElementById('res-legal-classification').textContent = data.legal_classification || '';
  document.getElementById('res-lawyer-summary').textContent       = data.lawyer_summary || '';
  document.getElementById('res-disclaimer').textContent           = data.disclaimer || '';

  renderList('res-key-risks',          data.key_risks,          'bg-red-400');
  renderList('res-relevant-documents', data.relevant_documents, 'bg-blue-400');
  renderOrderedList('res-next-steps',  data.next_steps);
  renderSimilarCases(data.similar_cases);

  showState('result');
  resultState.classList.add('fade-in');
}

// ── Main analyze function ─────────────────────────────────────────────────────
async function analyzeQuestion() {
  const question = questionInput.value.trim();

  if (question.length < 10) {
    alert('يرجى كتابة سؤال أكثر تفصيلًا، لا يقل عن 10 أحرف.');
    questionInput.focus();
    return;
  }

  analyzeBtn.disabled = true;
  showState('loading');
  startLoadingMessages();

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    stopLoadingMessages();
    renderResult(data);

  } catch (err) {
    stopLoadingMessages();
    showState('empty');

    if (err instanceof TypeError) {
      // Network error (fetch failed)
      alert('حدث خطأ في الاتصال. يرجى التأكد من اتصالك بالإنترنت والمحاولة مرة أخرى.');
    } else {
      alert('حدث خطأ أثناء التحليل. يرجى المحاولة مرة أخرى.');
    }
  } finally {
    analyzeBtn.disabled = false;
  }
}

// ── Events ────────────────────────────────────────────────────────────────────
analyzeBtn.addEventListener('click', analyzeQuestion);

questionInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    analyzeQuestion();
  }
});

newAnalysisBtn.addEventListener('click', () => {
  questionInput.value = '';
  charCount.textContent = '0 حرف';
  showState('empty');
  questionInput.focus();
  // Remove animation class so it can re-trigger
  resultState.classList.remove('fade-in');
});

copySummaryBtn.addEventListener('click', async () => {
  const text = document.getElementById('res-lawyer-summary').textContent;
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
    // Fallback for older browsers
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
});

// ── Scroll reveal (for other pages if reused) ─────────────────────────────────
const revealEls = document.querySelectorAll('.reveal');
if (revealEls.length) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); });
  }, { threshold: 0.1 });
  revealEls.forEach(el => observer.observe(el));
}
