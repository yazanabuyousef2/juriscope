const $ = (id) => document.getElementById(id);
const WORKSPACE_ROOT = () => document.getElementById("workspace-page");

function getStorageKey() {
  const root = WORKSPACE_ROOT();
  const caseId = root?.dataset.caseId || "standalone";
  return `mizan_workspace_state_v3_${caseId}`;
}

function getPageDefaults() {
  const root = WORKSPACE_ROOT();
  return {
    caseId: root?.dataset.caseId || "",
    title: root?.dataset.caseTitle || "",
    country: root?.dataset.caseCountry || "الأردن",
    caseType: root?.dataset.caseType || "غير محدد",
    audience: root?.dataset.userRole || "individual",
    client: root?.dataset.caseClient || "",
    opponent: root?.dataset.caseOpponent || "",
  };
}

const DEFAULT_TOOLS = {
  individual: [
    { key: "plain_summary", label: "تبسيط الجواب وخطوات عملية", description: "تحويل التحليل إلى خطوات واضحة لشخص غير متخصص." },
    { key: "lawyer_brief", label: "ملخص جاهز للمحامي", description: "ملخص قصير يمكن إرساله لمحامٍ." },
    { key: "legal_notice", label: "إنذار عدلي / خطاب مطالبة", description: "مسودة مطالبة أو إنذار أولي." },
    { key: "evidence_list", label: "قائمة بينات ومستندات", description: "ما يلزم جمعه قبل الإجراء." },
    { key: "case_timeline", label: "Timeline للقضية", description: "ترتيب الوقائع والمواعيد." },
  ],
  lawyer: [
    { key: "defense_memo", label: "مذكرة دفاع", description: "مسودة دفاع ودفوع ومخاطر." },
    { key: "claim_statement", label: "لائحة دعوى", description: "مسودة لائحة دعوى." },
    { key: "reply_statement", label: "لائحة جوابية", description: "رد منظم على ادعاءات الخصم." },
    { key: "case_timeline", label: "Timeline للقضية", description: "خط زمني للوقائع والإجراءات." },
    { key: "evidence_list", label: "قائمة بينات ومستندات", description: "الأدلة المطلوبة ونواقصها." },
    { key: "litigation_strategy", label: "استراتيجية تفاوض أو تقاضي", description: "خطة خيارات ومخاطر." },
  ],
  company: [
    { key: "contract_review", label: "تحليل عقد", description: "التزامات ومخاطر وبنود ناقصة." },
    { key: "risk_score", label: "Risk Score / مصفوفة مخاطر", description: "تقييم أولي للمخاطر." },
    { key: "legal_notice", label: "إنذار عدلي / خطاب مطالبة", description: "مطالبة رسمية أولية." },
    { key: "evidence_list", label: "قائمة بينات ومستندات", description: "مستندات داعمة للموقف." },
  ],
  law_student: [
    { key: "study_notes", label: "شرح مادة / ملخص تعليمي", description: "شرح تعليمي وأمثلة." },
    { key: "flashcards", label: "Flashcards / بطاقات مراجعة", description: "أسئلة وبطاقات مراجعة." },
    { key: "plain_summary", label: "تبسيط الجواب وخطوات عملية", description: "فهم مبسط للفكرة." },
  ],
  legal_researcher: [
    { key: "lawyer_brief", label: "ملخص بحثي منظم", description: "ملخص بحث ومصادر وحدود." },
    { key: "case_timeline", label: "Timeline للقضية", description: "ترتيب الوقائع زمنياً." },
    { key: "risk_score", label: "مصفوفة مخاطر", description: "خريطة مخاطر وثغرات." },
  ],
  judge: [
    { key: "case_timeline", label: "Timeline للقضية", description: "عرض محايد للوقائع." },
    { key: "evidence_list", label: "قائمة بينات ومستندات", description: "الثابت والناقص." },
    { key: "lawyer_brief", label: "ملخص بحثي محايد", description: "تلخيص نقاط النزاع." },
  ],
  government_employee: [
    { key: "official_letter", label: "صياغة كتاب رسمي", description: "مسودة كتاب أو مخاطبة رسمية." },
    { key: "case_timeline", label: "Timeline للإجراء", description: "ترتيب الإجراءات والمواعيد." },
    { key: "evidence_list", label: "قائمة مستندات وموافقات", description: "ما يلزم قبل القرار." },
  ],
};

let state = createEmptyWorkspace();
let availableTools = [];
let activeTab = "overview";

function createEmptyWorkspace() {
  const defaults = getPageDefaults();
  return {
    id: `ws_${Date.now()}`,
    title: defaults.title || "",
    country: defaults.country || "الأردن",
    audience: defaults.audience || "individual",
    caseType: defaults.caseType || "غير محدد",
    caseId: defaults.caseId || "",
    client: defaults.client || "",
    opponent: defaults.opponent || "",
    priority: "normal",
    status: "draft",
    question: "",
    analysis: {},
    usedTools: [],
    outputs: [],
    documents: [],
    tasks: [],
    timeline: [],
    notes: "",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function textWithBreaks(value) {
  return escapeHtml(value).replace(/\n/g, "<br>");
}

function nowId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function getAudience() {
  return $("workspace-audience")?.value || state.audience || "individual";
}

function fallbackTools() {
  return DEFAULT_TOOLS[getAudience()] || DEFAULT_TOOLS.individual;
}

function setStatus(message, type = "normal") {
  const el = $("workspace-status");
  if (el) {
    el.textContent = message;
    el.className = `text-xs ${type === "error" ? "text-red-300" : type === "success" ? "text-green-300" : "text-slate-500"}`;
  }

  const saved = $("workspace-save-indicator");
  if (saved) {
    saved.textContent = type === "error" ? "يحتاج انتباه" : "محفوظ محليًا";
    saved.className = `text-[11px] ${type === "error" ? "text-red-300" : "text-slate-500"}`;
  }
}

function saveState() {
  syncStateFromInputs();
  state.updatedAt = new Date().toISOString();
  localStorage.setItem(getStorageKey(), JSON.stringify(state));
  renderStats();
  renderNextActions();
}

function loadState() {
  const raw = localStorage.getItem(getStorageKey());
  if (!raw) {
    state = createEmptyWorkspace();
    return;
  }

  try {
    state = { ...createEmptyWorkspace(), ...JSON.parse(raw) };
    const defaults = getPageDefaults();
    if (defaults.caseId) {
      state.caseId = defaults.caseId;
      state.title = state.title || defaults.title;
      state.country = state.country || defaults.country;
      state.caseType = state.caseType || defaults.caseType;
      state.client = state.client || defaults.client;
      state.opponent = state.opponent || defaults.opponent;
    }
  } catch (_) {
    state = createEmptyWorkspace();
  }
}

function syncInputsFromState() {
  if ($("workspace-title")) $("workspace-title").value = state.title || "";
  if ($("workspace-country")) $("workspace-country").value = state.country || "الأردن";
  if ($("workspace-audience")) $("workspace-audience").value = state.audience || "individual";
  if ($("workspace-case-type")) $("workspace-case-type").value = state.caseType || "غير محدد";
  if ($("workspace-case-id")) $("workspace-case-id").value = state.caseId || "";
  if ($("workspace-client")) $("workspace-client").value = state.client || "";
  if ($("workspace-opponent")) $("workspace-opponent").value = state.opponent || "";
  if ($("workspace-priority")) $("workspace-priority").value = state.priority || "normal";
  if ($("workspace-status-select")) $("workspace-status-select").value = state.status || "draft";
  if ($("workspace-question")) $("workspace-question").value = state.question || "";
  if ($("workspace-analysis-json")) $("workspace-analysis-json").value = Object.keys(state.analysis || {}).length ? JSON.stringify(state.analysis, null, 2) : "";
  if ($("workspace-notes")) $("workspace-notes").value = state.notes || "";
}

function syncStateFromInputs() {
  state.title = $("workspace-title")?.value?.trim() || state.title || "";
  state.country = $("workspace-country")?.value?.trim() || "الأردن";
  state.audience = $("workspace-audience")?.value || "individual";
  state.caseType = $("workspace-case-type")?.value || "غير محدد";
  state.caseId = $("workspace-case-id")?.value || "";
  state.client = $("workspace-client")?.value?.trim() || "";
  state.opponent = $("workspace-opponent")?.value?.trim() || "";
  state.priority = $("workspace-priority")?.value || "normal";
  state.status = $("workspace-status-select")?.value || "draft";
  state.question = $("workspace-question")?.value?.trim() || "";
  state.notes = $("workspace-notes")?.value || "";

  const rawAnalysis = $("workspace-analysis-json")?.value?.trim();
  if (rawAnalysis) {
    try {
      state.analysis = JSON.parse(rawAnalysis);
    } catch (_) {
      // Keep previous valid analysis.
    }
  }
}

function renderStats() {
  const remaining = getRemainingTools();
  const stats = {
    outputs: state.outputs.length,
    openTasks: state.tasks.filter((task) => !task.done).length,
    documents: state.documents.length,
    remainingTools: remaining.length,
  };
  Object.entries(stats).forEach(([key, value]) => {
    const el = document.querySelector(`[data-stat="${key}"]`);
    if (el) el.textContent = value;
  });
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".workspace-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.panel !== tab);
  });
  document.querySelectorAll(".workspace-tab-btn").forEach((btn) => {
    const isActive = btn.dataset.tab === tab;
    btn.className = `workspace-tab-btn w-full text-right px-4 py-3 rounded-xl text-sm transition-all ${isActive ? "bg-gold-400 text-navy-950 font-bold" : "text-slate-300 hover:bg-white/5"}`;
  });
}

async function loadTools() {
  availableTools = fallbackTools();
  renderTools();
  renderStats();

  try {
    const response = await fetch(`/api/workspace-tools?audience_mode=${encodeURIComponent(getAudience())}`);
    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data.tools) && data.tools.length) {
        availableTools = data.tools;
        renderTools();
        renderStats();
      }
    }
  } catch (_) {
    // Keep fallback tools; page remains usable.
  }
}

function normalizeToolLabel(label) {
  return String(label || "").trim();
}

function getRemainingTools() {
  const used = new Set((state.usedTools || []).map(normalizeToolLabel));
  return availableTools.filter((tool) => !used.has(normalizeToolLabel(tool.label)));
}

function renderTools() {
  const box = $("workspace-tools-list");
  if (!box) return;
  const remaining = getRemainingTools();

  if (!remaining.length) {
    box.innerHTML = `
      <div class="md:col-span-2 xl:col-span-3 rounded-xl border border-green-500/20 bg-green-500/5 p-5 text-sm text-green-200">
        ✅ تم استخدام كل الأدوات المقترحة لهذه المرحلة. تستطيع إعادة الأدوات أو بدء ملف عمل جديد.
      </div>
    `;
    renderStats();
    return;
  }

  box.innerHTML = remaining.map((tool) => `
    <button class="workspace-tool-btn text-right rounded-2xl border border-white/10 bg-navy-950/40 hover:bg-white/10 hover:border-gold-400/30 p-4 transition-all" data-tool-key="${escapeHtml(tool.key)}" data-tool-label="${escapeHtml(tool.label)}">
      <div class="flex items-start justify-between gap-2 mb-2">
        <div class="text-sm font-bold text-white">${escapeHtml(tool.label)}</div>
        <span class="text-[10px] rounded-full bg-gold-400/10 text-gold-300 px-2 py-1">تشغيل</span>
      </div>
      <div class="text-xs text-slate-400 leading-relaxed">${escapeHtml(tool.description || "توليد مخرج عملي من ملف العمل الحالي")}</div>
    </button>
  `).join("");

  document.querySelectorAll(".workspace-tool-btn").forEach((btn) => {
    btn.addEventListener("click", () => runTool(btn.dataset.toolKey, btn.dataset.toolLabel));
  });
  renderStats();
}

function readAnalysisJson() {
  syncStateFromInputs();
  return state.analysis || {};
}

function markdownToText(markdown) {
  return String(markdown || "").replace(/\n{3,}/g, "\n\n").trim();
}

function addOutput(data) {
  const output = {
    id: nowId("out"),
    tool_key: data.tool_key || "",
    tool_label: data.tool_label || "أداة Workspace",
    title: data.title || data.tool_label || "مخرج قانوني",
    document_type: data.document_type || "workspace_output",
    content_markdown: markdownToText(data.content_markdown || ""),
    missing_information: Array.isArray(data.missing_information) ? data.missing_information : [],
    next_actions: Array.isArray(data.next_actions) ? data.next_actions : [],
    quality_warning: data.quality_warning || "هذا مخرج أولي يحتاج مراجعة مختص قبل الاستخدام الرسمي.",
    created_at: data.created_at || new Date().toISOString(),
  };
  state.outputs.unshift(output);
  if (output.tool_label && !state.usedTools.includes(output.tool_label)) state.usedTools.push(output.tool_label);
  createFollowupItemsFromOutput(output);
  saveState();
  renderOutputs();
  renderTools();
  switchTab("outputs");
}

function createFollowupItemsFromOutput(output) {
  for (const info of output.missing_information || []) {
    state.tasks.push({ id: nowId("task"), title: `استكمال معلومة ناقصة: ${info}`, due: "", priority: "high", done: false, source: output.title });
  }
  for (const action of output.next_actions || []) {
    state.tasks.push({ id: nowId("task"), title: String(action), due: "", priority: "normal", done: false, source: output.title });
  }
}

function renderOutputs() {
  const output = $("workspace-output");
  if (!output) return;

  if (!state.outputs.length) {
    output.innerHTML = `
      <div class="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-slate-400">
        لا توجد مخرجات بعد. افتح تبويب الأدوات وشغّل أداة مثل مذكرة دفاع، لائحة دعوى، إنذار، أو مصفوفة مخاطر.
      </div>
    `;
    return;
  }

  output.innerHTML = state.outputs.map((item) => {
    const missing = item.missing_information?.length ? `
      <div class="mt-4 rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4">
        <div class="text-xs font-semibold text-yellow-300 mb-2">معلومات ناقصة</div>
        <ul class="list-disc pr-5 text-sm text-slate-300 space-y-1">${item.missing_information.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
      </div>` : "";
    const next = item.next_actions?.length ? `
      <div class="mt-4 rounded-xl border border-green-500/20 bg-green-500/5 p-4">
        <div class="text-xs font-semibold text-green-300 mb-2">الخطوات التالية</div>
        <ul class="list-decimal pr-5 text-sm text-slate-300 space-y-1">${item.next_actions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
      </div>` : "";

    return `
      <article class="rounded-2xl border border-gold-400/20 bg-gold-400/5 p-5" data-output-id="${escapeHtml(item.id)}">
        <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
          <div>
            <div class="text-xs text-gold-300 mb-1">${escapeHtml(item.tool_label)}</div>
            <h3 class="text-xl font-bold text-white">${escapeHtml(item.title)}</h3>
            <div class="text-[11px] text-slate-500 mt-1">${new Date(item.created_at).toLocaleString("ar")}</div>
          </div>
          <div class="flex gap-2">
            <button class="copy-output text-xs px-3 py-2 rounded-xl border border-white/10 text-slate-300 hover:text-white" data-id="${escapeHtml(item.id)}">نسخ</button>
            <button class="delete-output text-xs px-3 py-2 rounded-xl border border-red-400/20 text-red-200 hover:bg-red-500/10" data-id="${escapeHtml(item.id)}">حذف</button>
          </div>
        </div>
        <div class="workspace-output-content text-sm text-slate-200 leading-loose whitespace-pre-wrap bg-navy-950/50 border border-white/10 rounded-xl p-4">${textWithBreaks(item.content_markdown)}</div>
        ${missing}
        ${next}
        <div class="mt-4 text-xs text-slate-400 border-t border-white/10 pt-3">${escapeHtml(item.quality_warning)}</div>
      </article>
    `;
  }).join("");

  document.querySelectorAll(".copy-output").forEach((btn) => btn.addEventListener("click", async () => {
    const item = state.outputs.find((x) => x.id === btn.dataset.id);
    if (!item) return;
    await navigator.clipboard.writeText(item.content_markdown || "");
    btn.textContent = "تم النسخ";
    setTimeout(() => (btn.textContent = "نسخ"), 1500);
  }));

  document.querySelectorAll(".delete-output").forEach((btn) => btn.addEventListener("click", () => {
    state.outputs = state.outputs.filter((x) => x.id !== btn.dataset.id);
    saveState();
    renderOutputs();
  }));
}

async function runTool(toolKey, toolLabel) {
  syncStateFromInputs();
  if (!state.question && !Object.keys(state.analysis || {}).length) {
    setStatus("اكتب الوقائع أو استورد آخر تحليل أولًا.", "error");
    switchTab("overview");
    return;
  }

  setStatus(`جاري توليد: ${toolLabel}...`);
  document.querySelectorAll(".workspace-tool-btn").forEach((btn) => (btn.disabled = true));

  try {
    const payload = {
      tool_key: toolKey,
      tool_label: toolLabel,
      question: state.question || "استخدم التحليل السابق لبناء المخرج المطلوب.",
      country: state.country || "الأردن",
      case_type: state.caseType || "غير محدد",
      selected_case_type: state.caseType || "غير محدد",
      audience_mode: state.audience || getAudience(),
      assistant_mode: "workspace_tool",
      case_id: state.caseId ? parseInt(state.caseId, 10) : (getPageDefaults().caseId ? parseInt(getPageDefaults().caseId, 10) : null),
      analysis: readAnalysisJson(),
      used_tools: state.usedTools,
      available_tools: availableTools.map((tool) => tool.label),
    };

    const response = await fetch("/api/workspace-tool", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || "تعذر تشغيل الأداة.");

    addOutput(data);
    setStatus("تم إنشاء المخرج داخل Workspace.", "success");
  } catch (error) {
    setStatus(error.message || "حدث خطأ أثناء تشغيل الأداة.", "error");
    renderTools();
  }
}

function buildWorkspacePlan() {
  syncStateFromInputs();
  if (!state.question) {
    setStatus("اكتب الوقائع أولًا حتى أبني لك خطة عمل.", "error");
    return;
  }

  const remaining = getRemainingTools().slice(0, 5);
  state.tasks.push({ id: nowId("task"), title: "تحديد الهدف القانوني النهائي من الملف", due: "", priority: "high", done: false, source: "خطة العمل" });
  state.tasks.push({ id: nowId("task"), title: "جمع المستندات الأساسية وربطها بالوقائع", due: "", priority: "high", done: false, source: "خطة العمل" });
  if (remaining[0]) state.tasks.push({ id: nowId("task"), title: `تشغيل أداة: ${remaining[0].label}`, due: "", priority: "normal", done: false, source: "خطة العمل" });
  if (remaining[1]) state.tasks.push({ id: nowId("task"), title: `تشغيل أداة: ${remaining[1].label}`, due: "", priority: "normal", done: false, source: "خطة العمل" });
  state.timeline.push({ id: nowId("time"), date: new Date().toISOString().slice(0, 10), title: "فتح ملف العمل وبناء الخطة الأولية", type: "إجراء", note: "تم إنشاء خطة Workspace أولية." });
  saveState();
  renderTasks();
  renderTimeline();
  renderNextActions();
  setStatus("تم بناء خطة عمل أولية.", "success");
}

function renderNextActions() {
  const box = $("workspace-next-actions");
  if (!box) return;
  const tasks = state.tasks.filter((task) => !task.done).slice(0, 4);
  if (!tasks.length) {
    box.innerHTML = `<div class="text-slate-500 text-sm">لا توجد مهام بعد. اضغط “بناء خطة عمل” أو شغّل أداة من تبويب الأدوات.</div>`;
    return;
  }
  box.innerHTML = tasks.map((task) => `<div class="rounded-xl border border-white/10 bg-white/5 p-3">${escapeHtml(task.title)}</div>`).join("");
}

function addDocument() {
  const name = $("doc-name")?.value?.trim();
  if (!name) return;
  state.documents.push({
    id: nowId("doc"),
    name,
    type: $("doc-type")?.value || "أخرى",
    status: $("doc-status")?.value || "available",
    createdAt: new Date().toISOString(),
  });
  $("doc-name").value = "";
  saveState();
  renderDocuments();
}

function renderDocuments() {
  const box = $("documents-list");
  if (!box) return;
  if (!state.documents.length) {
    box.innerHTML = `<div class="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">لا توجد مستندات بعد.</div>`;
    return;
  }
  box.innerHTML = state.documents.map((doc) => `
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/5 p-3">
      <div>
        <div class="font-semibold text-white text-sm">${escapeHtml(doc.name)}</div>
        <div class="text-xs text-slate-500 mt-1">${escapeHtml(doc.type)} — ${escapeHtml(labelStatus(doc.status))}</div>
      </div>
      <button class="delete-doc text-xs text-red-200 border border-red-400/20 rounded-lg px-3 py-1" data-id="${escapeHtml(doc.id)}">حذف</button>
    </div>
  `).join("");
  document.querySelectorAll(".delete-doc").forEach((btn) => btn.addEventListener("click", () => {
    state.documents = state.documents.filter((doc) => doc.id !== btn.dataset.id);
    saveState();
    renderDocuments();
  }));
}

function labelStatus(value) {
  if (value === "available") return "متوفر";
  if (value === "needed") return "مطلوب";
  if (value === "review") return "بحاجة مراجعة";
  return value || "غير محدد";
}

function addTask() {
  const title = $("task-title")?.value?.trim();
  if (!title) return;
  state.tasks.push({
    id: nowId("task"),
    title,
    due: $("task-due")?.value || "",
    priority: $("task-priority")?.value || "normal",
    done: false,
    source: "يدوي",
  });
  $("task-title").value = "";
  saveState();
  renderTasks();
}

function renderTasks() {
  const box = $("tasks-list");
  if (!box) return;
  if (!state.tasks.length) {
    box.innerHTML = `<div class="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">لا توجد مهام بعد.</div>`;
    return;
  }
  box.innerHTML = state.tasks.map((task) => `
    <div class="flex items-start gap-3 rounded-xl border border-white/10 bg-white/5 p-3 ${task.done ? "opacity-60" : ""}">
      <input type="checkbox" class="task-check mt-1" data-id="${escapeHtml(task.id)}" ${task.done ? "checked" : ""}>
      <div class="flex-1">
        <div class="font-semibold text-sm ${task.done ? "line-through text-slate-500" : "text-white"}">${escapeHtml(task.title)}</div>
        <div class="text-xs text-slate-500 mt-1">${task.due ? `الاستحقاق: ${escapeHtml(task.due)} — ` : ""}${escapeHtml(priorityLabel(task.priority))}${task.source ? ` — ${escapeHtml(task.source)}` : ""}</div>
      </div>
      <button class="delete-task text-xs text-red-200 border border-red-400/20 rounded-lg px-3 py-1" data-id="${escapeHtml(task.id)}">حذف</button>
    </div>
  `).join("");
  document.querySelectorAll(".task-check").forEach((chk) => chk.addEventListener("change", () => {
    const task = state.tasks.find((x) => x.id === chk.dataset.id);
    if (task) task.done = chk.checked;
    saveState();
    renderTasks();
  }));
  document.querySelectorAll(".delete-task").forEach((btn) => btn.addEventListener("click", () => {
    state.tasks = state.tasks.filter((task) => task.id !== btn.dataset.id);
    saveState();
    renderTasks();
  }));
}

function priorityLabel(value) {
  if (value === "urgent") return "عاجل";
  if (value === "high") return "مهم";
  return "عادي";
}

function addTimeline() {
  const title = $("timeline-title")?.value?.trim();
  if (!title) return;
  state.timeline.push({
    id: nowId("time"),
    date: $("timeline-date")?.value || "",
    title,
    type: $("timeline-type")?.value || "واقعة",
    note: "",
  });
  $("timeline-title").value = "";
  saveState();
  renderTimeline();
}

function renderTimeline() {
  const box = $("timeline-list");
  if (!box) return;
  if (!state.timeline.length) {
    box.innerHTML = `<div class="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">لا يوجد خط زمني بعد.</div>`;
    return;
  }
  const sorted = [...state.timeline].sort((a, b) => String(a.date || "9999").localeCompare(String(b.date || "9999")));
  box.innerHTML = sorted.map((event) => `
    <div class="flex gap-3 rounded-xl border border-white/10 bg-white/5 p-3">
      <div class="min-w-[110px] text-xs text-gold-300">${escapeHtml(event.date || "بدون تاريخ")}</div>
      <div class="flex-1">
        <div class="text-sm font-semibold text-white">${escapeHtml(event.title)}</div>
        <div class="text-xs text-slate-500 mt-1">${escapeHtml(event.type)}</div>
      </div>
      <button class="delete-time text-xs text-red-200 border border-red-400/20 rounded-lg px-3 py-1" data-id="${escapeHtml(event.id)}">حذف</button>
    </div>
  `).join("");
  document.querySelectorAll(".delete-time").forEach((btn) => btn.addEventListener("click", () => {
    state.timeline = state.timeline.filter((event) => event.id !== btn.dataset.id);
    saveState();
    renderTimeline();
  }));
}

function loadLastAnalysis() {
  const raw = localStorage.getItem("mizan_last_analysis");
  if (!raw) {
    setStatus("لا يوجد تحليل محفوظ محليًا. نفّذ تحليلًا من صفحة المساعد أولًا.", "error");
    return;
  }

  try {
    const analysis = JSON.parse(raw);
    state.analysis = analysis;
    const summary = analysis.professional_summary || analysis.short_answer || analysis.lawyer_summary || analysis.final_recommendation || "";
    if (summary) state.question = summary;
    const risks = analysis.key_risks || analysis.business_risks || analysis.risk_matrix;
    if (Array.isArray(risks)) {
      risks.slice(0, 3).forEach((risk) => state.tasks.push({ id: nowId("task"), title: `مراجعة خطر: ${String(risk)}`, due: "", priority: "high", done: false, source: "آخر تحليل" }));
    }
    const docs = analysis.relevant_documents || analysis.proof_points;
    if (Array.isArray(docs)) {
      docs.slice(0, 5).forEach((doc) => state.documents.push({ id: nowId("doc"), name: String(doc), type: "مستند داعم", status: "needed", createdAt: new Date().toISOString() }));
    }
    syncInputsFromState();
    saveState();
    renderAll();
    setStatus("تم استيراد آخر تحليل وتحويله إلى ملف عمل.", "success");
  } catch (_) {
    setStatus("تعذر قراءة آخر تحليل محفوظ.", "error");
  }
}

function exportWorkspace() {
  syncStateFromInputs();
  const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${state.title || "mizan-workspace"}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function newWorkspace() {
  if (!confirm("سيتم إعادة ضبط بيانات Workspace المحلية لهذه القضية فقط. المخرجات المحفوظة في القضية لن تُحذف. هل تريد المتابعة؟")) return;
  localStorage.removeItem(getStorageKey());
  state = createEmptyWorkspace();
  state.country = $("workspace-country")?.value || getPageDefaults().country || "الأردن";
  state.audience = $("workspace-audience")?.value || getPageDefaults().audience || "individual";
  state.caseId = $("workspace-case-id")?.value || getPageDefaults().caseId || "";
  state.title = $("workspace-title")?.value || getPageDefaults().title || "";
  state.caseType = $("workspace-case-type")?.value || getPageDefaults().caseType || "غير محدد";
  syncInputsFromState();
  loadTools();
  renderAll();
  setStatus("تم فتح ملف عمل جديد.", "success");
}

function renderAll() {
  renderStats();
  renderTools();
  renderOutputs();
  renderDocuments();
  renderTasks();
  renderTimeline();
  renderNextActions();
}

function bindInputs() {
  [
    "workspace-title", "workspace-country", "workspace-audience", "workspace-case-type", "workspace-case-id",
    "workspace-client", "workspace-opponent", "workspace-priority", "workspace-status-select",
    "workspace-question", "workspace-analysis-json", "workspace-notes"
  ].forEach((id) => {
    const el = $(id);
    if (!el) return;
    const eventName = el.tagName === "SELECT" ? "change" : "input";
    el.addEventListener(eventName, () => {
      saveState();
      if (id === "workspace-audience") {
        state.usedTools = [];
        loadTools();
      }
    });
  });
}


function buildAnalysisDisplay(data) {
  if (!data || typeof data !== "object") return "";
  const parts = [];
  const preferred = [
    ["الملخص", data.professional_summary || data.short_answer || data.lawyer_summary],
    ["التحليل", data.legal_analysis || data.detailed_analysis || data.answer],
    ["التوصية", data.final_recommendation || data.recommendation],
    ["المخاطر", Array.isArray(data.key_risks) ? data.key_risks.join("\n- ") : data.risk_level],
  ];
  preferred.forEach(([label, value]) => {
    if (!value) return;
    parts.push(`## ${label}\n${Array.isArray(value) ? value.join("\n") : String(value)}`);
  });
  if (!parts.length) {
    parts.push(JSON.stringify(data, null, 2));
  }
  return parts.join("\n\n");
}

async function sendCaseAssistant(source = "overview") {
  syncStateFromInputs();
  const fromTab = source === "tab";
  const questionEl = fromTab ? $("case-assistant-question-tab") : $("case-assistant-question");
  const resultEl = fromTab ? $("case-assistant-result-tab") : $("case-assistant-result");
  const statusEl = $("case-assistant-status");

  let question = questionEl?.value?.trim() || "";
  if (!question) {
    question = state.question || "";
  }
  if (!question) {
    if (statusEl) statusEl.textContent = "اكتب سؤالًا أو املأ ملف العمل أولًا.";
    if (resultEl) {
      resultEl.classList.remove("hidden");
      resultEl.textContent = "اكتب سؤالًا أو املأ ملف العمل أولًا.";
    }
    return;
  }

  const contextPrefix = state.question && question !== state.question
    ? `سياق ملف القضية:\n${state.question}\n\nسؤال المستخدم داخل القضية:\n${question}`
    : question;

  if (statusEl) statusEl.textContent = "جاري التحليل داخل القضية...";
  if (resultEl) {
    resultEl.classList.remove("hidden");
    resultEl.textContent = "جاري التحليل...";
  }

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: contextPrefix,
        country: state.country || getPageDefaults().country || "الأردن",
        case_type: state.caseType || getPageDefaults().caseType || "غير محدد",
        selected_case_type: state.caseType || getPageDefaults().caseType || "غير محدد",
        audience_mode: state.audience || getPageDefaults().audience || "individual",
        assistant_mode: "case_workspace_assistant",
        case_id: state.caseId ? parseInt(state.caseId, 10) : (getPageDefaults().caseId ? parseInt(getPageDefaults().caseId, 10) : null),
      }),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || "تعذر تشغيل مساعد القضية.");

    const display = buildAnalysisDisplay(data);
    if (resultEl) resultEl.textContent = display;

    state.analysis = data;
    state.outputs.unshift({
      id: nowId("out"),
      title: "تحليل من مساعد القضية",
      tool_label: "مساعد القضية",
      document_type: "case_workspace_assistant",
      content_markdown: display,
      created_at: new Date().toISOString(),
    });
    saveState();
    renderOutputs();
    if (statusEl) statusEl.textContent = "تم حفظ التحليل داخل القضية.";
  } catch (error) {
    if (resultEl) resultEl.textContent = error.message || "حدث خطأ أثناء التحليل.";
    if (statusEl) statusEl.textContent = "حدث خطأ.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadState();
  syncInputsFromState();
  bindInputs();
  loadTools();
  renderAll();
  switchTab("overview");

  document.querySelectorAll(".workspace-tab-btn").forEach((btn) => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));
  $("workspace-new")?.addEventListener("click", newWorkspace);
  $("workspace-load-last")?.addEventListener("click", loadLastAnalysis);
  $("workspace-export")?.addEventListener("click", exportWorkspace);
  $("workspace-build-plan")?.addEventListener("click", buildWorkspacePlan);
  $("workspace-reset-tools")?.addEventListener("click", () => { state.usedTools = []; saveState(); renderTools(); setStatus("تمت إعادة ضبط الأدوات.", "success"); });
  $("workspace-toggle-json")?.addEventListener("click", () => $("workspace-analysis-json")?.classList.toggle("hidden"));
  $("workspace-clear-outputs")?.addEventListener("click", () => { if (confirm("مسح كل المخرجات؟")) { state.outputs = []; saveState(); renderOutputs(); }});
  $("add-document")?.addEventListener("click", addDocument);
  $("add-task")?.addEventListener("click", addTask);
  $("add-timeline")?.addEventListener("click", addTimeline);
  $("case-assistant-send")?.addEventListener("click", () => sendCaseAssistant("overview"));
  $("case-assistant-send-tab")?.addEventListener("click", () => sendCaseAssistant("tab"));
  $("case-assistant-use-workspace")?.addEventListener("click", () => { if ($("case-assistant-question")) $("case-assistant-question").value = $("workspace-question")?.value || ""; });
  $("case-assistant-use-workspace-tab")?.addEventListener("click", () => { if ($("case-assistant-question-tab")) $("case-assistant-question-tab").value = $("workspace-question")?.value || ""; });
});
