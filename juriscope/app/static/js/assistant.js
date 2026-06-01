console.log("✅ Mizan assistant.js multi-document analysis v20260529-1");

let conversationHistory = [];

function $(id) {
  return document.getElementById(id);
}

function valueOf(id, fallback = "") {
  const element = $(id);
  if (!element) return fallback;
  return element.value || fallback;
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function textWithBreaks(value) {
  return escapeHtml(value || "").replaceAll("\n", "<br>");
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (value === null || value === undefined || value === "") return [];
  return [value];
}

function itemText(item) {
  if (typeof item === "string") return item;

  if (item && typeof item === "object") {
    if (item.title || item.summary || item.text || item.article_number || item.article_text) {
      return [
        item.title,
        item.article_number ? `المادة ${item.article_number}` : "",
        item.summary,
        item.text,
        item.article_text,
      ].filter(Boolean).join(" — ");
    }

    return Object.values(item).filter(Boolean).join(" — ") || JSON.stringify(item);
  }

  return String(item ?? "");
}

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value || "";
}

function getAssistantPageConfig() {
  const page = $("assistant-page");

  return {
    userRole: page?.dataset?.userRole || "individual",
    staffMode: page?.dataset?.staffMode === "true",
    showCaseType: page?.dataset?.showCaseType === "true",
  };
}

function getSelectedCaseType() {
  const config = getAssistantPageConfig();

  if (!config.showCaseType) {
    return "غير محدد";
  }

  const value = valueOf("case-type-select", "غير محدد").trim();
  return value || "غير محدد";
}

function showOnly(stateId) {
  ["empty-state", "loading-state", "result-state", "document-result-state"].forEach((id) => {
    const element = $(id);
    if (!element) return;

    if (id === stateId) {
      element.classList.remove("hidden");
    } else {
      element.classList.add("hidden");
    }
  });
}

function setButtonLoading(buttonId, loading, normalText, loadingText) {
  const button = $(buttonId);
  if (!button) return;

  button.disabled = loading;
  button.textContent = loading ? loadingText : normalText;
  button.classList.toggle("opacity-60", loading);
  button.classList.toggle("cursor-not-allowed", loading);
}

function setLoading(show, message = "جاري التحليل...") {
  if (show) {
    setText("loading-message", message);
    showOnly("loading-state");
  }

  setButtonLoading("analyze-btn", show, "إرسال للمساعد", "جاري الإرسال...");
  setButtonLoading("analyze-document-btn", show, "تحليل المستندات", "جاري تحليل المستندات...");
}

async function parseApiResponse(response) {
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    return await response.json();
  }

  const text = await response.text();

  return {
    detail: text || "حدث خطأ غير متوقع.",
  };
}

function listToHtml(items, ordered = false) {
  const list = asArray(items);

  if (!list.length) {
    return '<p class="text-sm text-slate-500">لا يوجد.</p>';
  }

  const tag = ordered ? "ol" : "ul";
  const className = ordered ? "list-decimal pr-5" : "list-disc pr-5";

  return `
    <${tag} class="${className} space-y-2 text-sm text-slate-300 leading-relaxed">
      ${list.map((x) => `<li>${escapeHtml(itemText(x))}</li>`).join("")}
    </${tag}>
  `;
}

function hasText(value) {
  return Boolean(value && String(value).trim());
}

function hasList(value) {
  return asArray(value).length > 0;
}

function cardHtml(title, bodyHtml, options = {}) {
  const border = options.border || "border-white/10";
  const bg = options.bg || "";
  const titleColor = options.titleColor || "text-gold-400";

  return `
    <div class="glass-card rounded-2xl border ${border} ${bg} p-5">
      <div class="text-xs font-semibold ${titleColor} mb-3">${escapeHtml(title)}</div>
      <div class="text-sm text-slate-300 leading-relaxed">${bodyHtml}</div>
    </div>
  `;
}

function badge(text, className = "bg-white/5 border-white/10 text-slate-300") {
  return `
    <span class="inline-flex rounded-full border px-3 py-1 text-xs ${className}">
      ${escapeHtml(text)}
    </span>
  `;
}

function getRequestTypeLabel(type) {
  const labels = {
    general_question: "سؤال قانوني مهني",
    case_analysis: "تحليل قضية",
    legal_research: "بحث قانوني",
    contract_review: "مراجعة عقد",
    legal_drafting: "صياغة قانونية",
    litigation_strategy: "استراتيجية دعوى",
    corporate_advisory: "استشارة شركات",
    legal_article_request: "طلب مادة قانونية",
    legislation_request: "طلب تشريع",
    procedure_guidance: "إرشاد إجرائي",
    lawyer_brief: "ملخص للمحامي",
    document_analysis: "تحليل مستند",
  };

  return labels[type] || "رد قانوني";
}

function getAudienceLabel(mode) {
  const labels = {
    legal_professional: "مهني قانوني",
    individual: "شخص عادي",
    lawyer: "محامي",
    company: "شركة / رجل أعمال",
    judge: "قاضٍ",
    law_student: "طالب قانون",
    legal_researcher: "باحث قانوني",
    government_employee: "موظف حكومي",
  };

  return labels[mode] || mode || "مستخدم";
}

function getStrictCardsForRequest(data) {
  const requestType = data.request_type || data.assistant_mode || "case_analysis";

  const professionalBase = [
    "case_type_correction",
    "professional_summary",
    "facts_assumptions",
    "legal_issues",
    "governing_law",
    "verified_legal_materials",
    "source_based_analysis",
    "application_to_facts",
    "strengths",
    "weaknesses",
    "opposing_arguments",
    "strategic_recommendations",
    "missing_information",
    "final_recommendation",
    "professional_tools",
    "action_checklist",
    "confidence",
    "legal_sources",
    "disclaimer",
  ];

  const byType = {
    legal_research: [
      "case_type_correction", "professional_summary", "legal_issues", "governing_law",
      "verified_legal_materials", "source_based_analysis", "source_limitations",
      "confidence", "legal_sources", "disclaimer",
    ],
    contract_review: [
      "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
      "governing_law", "source_based_analysis", "key_risks", "business_risks",
      "weaknesses", "strategic_recommendations", "drafting_notes", "missing_information",
      "confidence", "legal_sources", "disclaimer",
    ],
    legal_drafting: [
      "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
      "governing_law", "drafting_notes", "source_based_analysis", "missing_information",
      "final_recommendation", "confidence", "legal_sources", "disclaimer",
    ],
    litigation_strategy: [
      "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
      "governing_law", "application_to_facts", "strengths", "weaknesses",
      "opposing_arguments", "proof_points", "strategic_recommendations", "relevant_documents",
      "missing_information", "confidence", "legal_sources", "disclaimer",
    ],
    document_analysis: [
      "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
      "governing_law", "source_based_analysis", "application_to_facts", "key_risks",
      "relevant_documents", "missing_information", "strategic_recommendations",
      "confidence", "legal_sources", "disclaimer",
    ],
    lawyer_brief: [
      "case_type_correction", "professional_summary", "case_understanding", "legal_classification",
      "governing_law", "source_based_analysis", "proof_points", "defenses_or_arguments",
      "key_risks", "lawyer_summary", "confidence", "legal_sources", "disclaimer",
    ],
  };

  return byType[requestType] || byType[data.assistant_mode] || professionalBase;
}

function getCardsToShow(data) {
  const fromBackend = asArray(data.cards_to_show).filter(Boolean);
  if (fromBackend.length) {
    return fromBackend;
  }
  return getStrictCardsForRequest(data);
}

function renderSimilarCasesHtml(cases) {
  const list = asArray(cases);

  if (!list.length) {
    return '<p class="text-sm text-slate-500">لا يوجد.</p>';
  }

  return `
    <div class="space-y-3">
      ${list.map((item) => {
        if (typeof item === "string") {
          return `
            <div class="rounded-xl bg-white/5 border border-white/10 p-3 text-sm text-slate-300">
              ${escapeHtml(item)}
            </div>
          `;
        }

        return `
          <div class="rounded-xl bg-white/5 border border-white/10 p-3 text-sm text-slate-300">
            <div class="font-semibold text-white mb-1">${escapeHtml(item.title || "حالة مشابهة عامة")}</div>
            ${item.similarity ? `<div class="text-slate-300">${escapeHtml(item.similarity)}</div>` : ""}
            ${item.principle ? `<div class="text-slate-400 mt-1">${escapeHtml(item.principle)}</div>` : ""}
            ${item.why_relevant ? `<div class="text-slate-500 mt-1">${escapeHtml(item.why_relevant)}</div>` : ""}
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderCriminalPenaltyHtml(penalty) {
  if (!penalty || !penalty.show) return "";

  return `
    <div class="space-y-3">
      ${penalty.alleged_crime ? `<p><strong>الفعل المنسوب:</strong> ${escapeHtml(penalty.alleged_crime)}</p>` : ""}
      ${penalty.possible_penalty_range ? `<p><strong>النطاق المحتمل:</strong> ${escapeHtml(penalty.possible_penalty_range)}</p>` : ""}

      <div>
        <strong>عوامل قد تشدد الموقف:</strong>
        ${listToHtml(penalty.factors_that_may_increase_penalty)}
      </div>

      <div>
        <strong>عوامل قد تخفف الموقف:</strong>
        ${listToHtml(penalty.factors_that_may_reduce_penalty)}
      </div>

      ${penalty.important_warning ? `<p class="text-yellow-300">${escapeHtml(penalty.important_warning)}</p>` : ""}
    </div>
  `;
}

function renderLegalSourcesHtml(sources) {
  const list = asArray(sources);

  if (!list.length) {
    return '<p class="text-sm text-slate-500">لم يتم العثور على مصادر قانونية معتمدة مناسبة من قاعدة بيانات Mizan لهذا السؤال.</p>';
  }

  return `
    <div class="space-y-3">
      ${list.map((source, index) => {
        const matchedTerms = asArray(source.matched_terms).map(escapeHtml).join(", ") || "—";

        return `
          <details class="rounded-xl bg-black/20 border border-white/10 p-4">
            <summary class="cursor-pointer text-gold-300 font-semibold">
              مصدر ${index + 1}: ${escapeHtml(source.document_title || "تشريع")} ${source.article_number ? `— المادة ${escapeHtml(source.article_number)}` : ""}
            </summary>

            <div class="mt-4 space-y-3">
              <div class="flex flex-wrap gap-2 text-xs">
                ${badge(source.country_name || "غير محدد", "bg-blue-500/10 border-blue-400/30 text-blue-200")}
                ${badge("Score: " + (source.score || ""), "bg-yellow-500/10 border-yellow-400/30 text-yellow-200")}
                ${badge(source.article_review_status || "approved", "bg-green-500/10 border-green-400/30 text-green-200")}
                ${source.source_confidence ? badge(source.source_confidence, "bg-white/5 border-white/10 text-slate-300") : ""}
              </div>

              <div class="text-xs text-slate-400">
                <strong class="text-slate-200">التشريع:</strong>
                ${escapeHtml(source.document_title || "")}
              </div>

              ${source.article_number ? `
                <div class="text-xs text-slate-400">
                  <strong class="text-slate-200">رقم المادة:</strong>
                  ${escapeHtml(source.article_number)}
                </div>
              ` : ""}

              ${source.article_title ? `
                <div class="text-xs text-slate-400">
                  <strong class="text-slate-200">عنوان المادة:</strong>
                  ${escapeHtml(source.article_title)}
                </div>
              ` : ""}

              ${source.article_text ? `
                <div class="rounded-xl bg-white/5 border border-white/10 p-4 text-xs text-slate-300 leading-relaxed whitespace-pre-line">
                  ${escapeHtml(source.article_text)}
                </div>
              ` : ""}

              <div class="text-xs text-slate-500">
                الكلمات المطابقة: ${matchedTerms}
              </div>
            </div>
          </details>
        `;
      }).join("")}
    </div>
  `;
}

function shouldShowCaseTypeCorrection(data) {
  if (!data) return false;

  if (data.case_type_correction_note) return true;

  if (data.selected_case_type && data.detected_case_type) {
    if (data.selected_case_type !== "غير محدد" && data.selected_case_type !== data.detected_case_type) {
      return true;
    }
  }

  return false;
}

function renderCaseTypeCorrectionHtml(data) {
  if (!shouldShowCaseTypeCorrection(data)) return "";

  const selected = data.selected_case_type || "غير محدد";
  const detected = data.detected_case_type || "غير محدد";
  const note = data.case_type_correction_note || "";

  return cardHtml(
    "تنبيه بخصوص نوع القضية",
    `
      <div class="space-y-3">
        <div class="flex flex-wrap gap-2">
          ${badge(`اختيار المستخدم: ${selected}`, "bg-white/5 border-white/10 text-slate-300")}
          ${badge(`التصنيف الأقرب: ${detected}`, "bg-yellow-500/10 border-yellow-400/30 text-yellow-200")}
        </div>
        ${note ? `<p>${textWithBreaks(note)}</p>` : ""}
      </div>
    `,
    {
      border: "border-yellow-500/20",
      bg: "bg-yellow-500/5",
      titleColor: "text-yellow-300",
    }
  );
}


function normalizeToolItem(tool) {
  if (tool && typeof tool === "object") {
    return {
      key: tool.key || "",
      label: tool.label || tool.title || itemText(tool),
      description: tool.description || "توليد مخرج عملي من التحليل الحالي",
    };
  }
  return {
    key: "",
    label: itemText(tool),
    description: "اضغط لتوليد هذا المخرج داخل مساحة عمل Mizan",
  };
}

function renderProfessionalToolsCard(data) {
  const tools = asArray(data.professional_tools).map(normalizeToolItem).filter((tool) => tool.label);
  if (!tools.length) return "";

  const buttons = tools.map((tool) => `
    <button
      class="workspace-tool-btn text-right rounded-xl border border-gold-400/15 bg-gold-400/5 hover:bg-gold-400/10 hover:border-gold-400/35 p-4 transition-all"
      data-tool-key="${escapeHtml(tool.key)}"
      data-tool-label="${escapeHtml(tool.label)}"
    >
      <div class="text-sm font-semibold text-white mb-1">${escapeHtml(tool.label)}</div>
      <div class="text-xs text-slate-400 leading-relaxed">${escapeHtml(tool.description)}</div>
    </button>
  `).join("");

  return `
    <div id="professional-tools-card" class="glass-card rounded-2xl border border-gold-400/20 bg-gold-400/5 p-5">
      <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <div class="text-xs font-semibold text-gold-300 mb-1">أدوات مقترحة داخل Mizan</div>
          <p class="text-xs text-slate-400 leading-relaxed">اضغط على أي أداة ليقوم Mizan بإنشائها، ثم ستظهر لك الأدوات المتبقية فقط.</p>
        </div>
        <a href="/cases" class="text-xs px-3 py-2 rounded-xl border border-white/10 text-slate-300 hover:text-white hover:border-white/20 transition-all">فتح ملف قضية</a>
      </div>
      <div class="grid sm:grid-cols-2 gap-3">${buttons}</div>
    </div>
  `;
}

function renderWorkspaceToolOutput(data) {
  const missing = hasList(data.missing_information)
    ? `<div class="mt-4 rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4"><div class="text-xs font-semibold text-yellow-300 mb-2">معلومات ناقصة</div>${listToHtml(data.missing_information)}</div>`
    : "";

  const nextActions = hasList(data.next_actions)
    ? `<div class="mt-4 rounded-xl border border-green-500/20 bg-green-500/5 p-4"><div class="text-xs font-semibold text-green-300 mb-2">الخطوات التالية</div>${listToHtml(data.next_actions, true)}</div>`
    : "";

  return `
    <div class="glass-card rounded-2xl border border-gold-400/20 bg-gold-400/5 p-5">
      <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <div class="text-xs font-semibold text-gold-300 mb-1">مخرج أداة Workspace</div>
          <h3 class="text-lg font-bold text-white">${escapeHtml(data.title || data.tool_label || "مخرج قانوني")}</h3>
        </div>
        <button class="copy-generated-tool-btn text-xs px-3 py-2 rounded-xl border border-white/10 text-slate-300 hover:text-white hover:border-white/20 transition-all">نسخ</button>
      </div>
      <div class="generated-tool-content text-sm text-slate-200 leading-loose whitespace-pre-wrap bg-navy-950/50 border border-white/10 rounded-xl p-4">${textWithBreaks(data.content_markdown || "")}</div>
      ${missing}
      ${nextActions}
      <div class="mt-4 text-xs text-slate-400 border-t border-white/10 pt-3">${escapeHtml(data.quality_warning || "هذا مخرج أولي يحتاج مراجعة مختص قبل الاستخدام الرسمي.")}</div>
    </div>
  `;
}

function renderCardByName(cardName, data) {
  switch (cardName) {
    case "case_type_correction":
      return renderCaseTypeCorrectionHtml(data);

    case "short_answer":
      if (!hasText(data.short_answer)) return "";
      return cardHtml(
        "الإجابة المختصرة",
        `<p class="text-slate-200">${textWithBreaks(data.short_answer)}</p>`,
        { border: "border-gold-400/20", bg: "bg-gold-400/5" }
      );

    case "plain_explanation":
      if (!hasText(data.plain_explanation)) return "";
      return cardHtml("شرح مبسط", `<p>${textWithBreaks(data.plain_explanation)}</p>`);

    case "practical_meaning":
      if (!hasText(data.practical_meaning)) return "";
      return cardHtml("ماذا يعني هذا عمليًا؟", `<p>${textWithBreaks(data.practical_meaning)}</p>`);

    case "country_context":
      if (!hasText(data.country_context)) return "";
      return cardHtml("سياق الدولة", `<p>${textWithBreaks(data.country_context)}</p>`);

    case "case_understanding":
      if (!hasText(data.case_understanding)) return "";
      return cardHtml("فهم الحالة", `<p>${textWithBreaks(data.case_understanding)}</p>`);

    case "legal_classification":
      if (!hasText(data.legal_classification)) return "";
      return cardHtml("التكييف القانوني المحتمل", `<p>${textWithBreaks(data.legal_classification)}</p>`);

    case "legal_basis":
      if (!hasText(data.legal_basis)) return "";
      return cardHtml(
        "الأساس القانوني",
        `<p>${textWithBreaks(data.legal_basis)}</p>`,
        { border: "border-blue-500/20", bg: "bg-blue-500/5", titleColor: "text-blue-300" }
      );

    case "articles_requested":
      if (!hasList(data.articles_requested)) return "";
      return cardHtml(
        "المواد القانونية المطلوبة",
        listToHtml(data.articles_requested),
        { border: "border-blue-500/20", bg: "bg-blue-500/5", titleColor: "text-blue-300" }
      );

    case "legislation_summary":
      if (!hasText(data.legislation_summary)) return "";
      return cardHtml(
        "ملخص التشريع",
        `<p>${textWithBreaks(data.legislation_summary)}</p>`,
        { border: "border-blue-500/20", bg: "bg-blue-500/5", titleColor: "text-blue-300" }
      );

    case "mizan_sources_summary":
      if (!hasText(data.mizan_sources_summary) && !hasText(data.source_dependency_level)) return "";
      return cardHtml(
        "اعتماد الجواب على مصادر Mizan",
        `
          <div class="space-y-3">
            ${data.source_dependency_level ? `
              <div>
                <span class="text-slate-400">مستوى الاعتماد:</span>
                <span class="text-gold-300 font-semibold">${escapeHtml(data.source_dependency_level)}</span>
              </div>
            ` : ""}
            ${data.mizan_sources_summary ? `<p>${textWithBreaks(data.mizan_sources_summary)}</p>` : ""}
          </div>
        `,
        { border: "border-gold-400/20", bg: "bg-gold-400/5" }
      );

    case "analysis_based_on_sources":
      if (!hasText(data.analysis_based_on_sources)) return "";
      return cardHtml(
        "التحليل المبني على التشريعات والمواد المعتمدة",
        `<p>${textWithBreaks(data.analysis_based_on_sources)}</p>`,
        { border: "border-green-500/20", bg: "bg-green-500/5", titleColor: "text-green-300" }
      );

    case "general_legal_reasoning":
      if (!hasText(data.general_legal_reasoning)) return "";
      return cardHtml("التحليل القانوني العام المساعد", `<p>${textWithBreaks(data.general_legal_reasoning)}</p>`);

    case "verified_legal_materials":
      if (!hasList(data.verified_legal_materials)) return "";
      return cardHtml(
        "مواد أو نصوص مؤكدة",
        listToHtml(data.verified_legal_materials),
        { border: "border-green-500/20", bg: "bg-green-500/5", titleColor: "text-green-300" }
      );

    case "unverified_legal_points":
      if (!hasList(data.unverified_legal_points)) return "";
      return cardHtml(
        "نقاط تحتاج تحقق",
        listToHtml(data.unverified_legal_points),
        { border: "border-yellow-500/20", bg: "bg-yellow-500/5", titleColor: "text-yellow-300" }
      );

    case "key_risks":
      if (!hasList(data.key_risks)) return "";
      return cardHtml(
        "المخاطر الرئيسية",
        listToHtml(data.key_risks),
        { border: "border-red-500/20", bg: "bg-red-500/5", titleColor: "text-red-300" }
      );

    case "business_risks":
      if (!hasList(data.business_risks)) return "";
      return cardHtml(
        "مخاطر على العمل أو الشركة",
        listToHtml(data.business_risks),
        { border: "border-orange-500/20", bg: "bg-orange-500/5", titleColor: "text-orange-300" }
      );

    case "relevant_documents":
      if (!hasList(data.relevant_documents)) return "";
      return cardHtml("المستندات ذات العلاقة", listToHtml(data.relevant_documents), { titleColor: "text-blue-300" });

    case "proof_points":
      if (!hasList(data.proof_points)) return "";
      return cardHtml("نقاط الإثبات", listToHtml(data.proof_points), { titleColor: "text-purple-300" });

    case "defenses_or_arguments":
      if (!hasList(data.defenses_or_arguments)) return "";
      return cardHtml("الدفوع أو الحجج المحتملة", listToHtml(data.defenses_or_arguments), { titleColor: "text-purple-300" });

    case "similar_cases":
      if (!hasList(data.similar_cases)) return "";
      return cardHtml("حالات مشابهة عامة", renderSimilarCasesHtml(data.similar_cases), { titleColor: "text-purple-300" });

    case "criminal_penalty_estimate":
      if (!data.criminal_penalty_estimate || !data.criminal_penalty_estimate.show) return "";
      return cardHtml(
        "تقدير جنائي أولي",
        renderCriminalPenaltyHtml(data.criminal_penalty_estimate),
        { border: "border-red-500/20", bg: "bg-red-500/5", titleColor: "text-red-300" }
      );

    case "next_steps":
      if (!hasList(data.next_steps)) return "";
      return cardHtml(
        "الخطوات التالية",
        listToHtml(data.next_steps, true),
        { border: "border-green-500/20", bg: "bg-green-500/5", titleColor: "text-green-300" }
      );

    case "procedure_steps":
      if (!hasList(data.procedure_steps)) return "";
      return cardHtml(
        "الخطوات الإجرائية",
        listToHtml(data.procedure_steps, true),
        { border: "border-green-500/20", bg: "bg-green-500/5", titleColor: "text-green-300" }
      );

    case "when_to_consult_lawyer":
      if (!hasText(data.when_to_consult_lawyer)) return "";
      return cardHtml("متى تحتاج مراجعة محام؟", `<p>${textWithBreaks(data.when_to_consult_lawyer)}</p>`);

    case "educational_notes":
      if (!hasText(data.educational_notes)) return "";
      return cardHtml(
        "ملاحظات تعليمية",
        `<p>${textWithBreaks(data.educational_notes)}</p>`,
        { border: "border-purple-500/20", bg: "bg-purple-500/5", titleColor: "text-purple-300" }
      );

    case "role_based_guidance":
      if (!hasText(data.role_based_guidance)) return "";
      return cardHtml("توجيه حسب نوع المستخدم", `<p>${textWithBreaks(data.role_based_guidance)}</p>`);

    case "professional_summary":
      if (!hasText(data.professional_summary)) return "";
      return cardHtml(
        "الخلاصة القانونية المهنية",
        `<p class="text-slate-200">${textWithBreaks(data.professional_summary)}</p>`,
        { border: "border-gold-400/20", bg: "bg-gold-400/5" }
      );

    case "facts_assumptions":
      if (!hasList(data.facts_assumptions)) return "";
      return cardHtml("الوقائع والافتراضات المعتمدة", listToHtml(data.facts_assumptions), { titleColor: "text-blue-300" });

    case "legal_issues":
      if (!hasList(data.legal_issues)) return "";
      return cardHtml("المسائل القانونية محل البحث", listToHtml(data.legal_issues), { titleColor: "text-purple-300" });

    case "governing_law":
      if (!hasList(data.governing_law)) return "";
      return cardHtml("النصوص والقواعد القانونية الحاكمة", listToHtml(data.governing_law), { border: "border-blue-500/20", bg: "bg-blue-500/5", titleColor: "text-blue-300" });

    case "source_based_analysis":
      if (!hasText(data.source_based_analysis)) return "";
      return cardHtml("التحليل القانوني المبني على المصادر", `<p>${textWithBreaks(data.source_based_analysis)}</p>`, { border: "border-green-500/20", bg: "bg-green-500/5", titleColor: "text-green-300" });

    case "application_to_facts":
      if (!hasText(data.application_to_facts)) return "";
      return cardHtml("تطبيق القانون على الوقائع", `<p>${textWithBreaks(data.application_to_facts)}</p>`, { titleColor: "text-green-300" });

    case "strengths":
      if (!hasList(data.strengths)) return "";
      return cardHtml("نقاط القوة", listToHtml(data.strengths), { border: "border-green-500/20", bg: "bg-green-500/5", titleColor: "text-green-300" });

    case "weaknesses":
      if (!hasList(data.weaknesses)) return "";
      return cardHtml("نقاط الضعف والمخاطر", listToHtml(data.weaknesses), { border: "border-red-500/20", bg: "bg-red-500/5", titleColor: "text-red-300" });

    case "opposing_arguments":
      if (!hasList(data.opposing_arguments)) return "";
      return cardHtml("ما قد يدفع به الخصم", listToHtml(data.opposing_arguments), { border: "border-orange-500/20", bg: "bg-orange-500/5", titleColor: "text-orange-300" });

    case "strategic_recommendations":
      if (!hasList(data.strategic_recommendations)) return "";
      return cardHtml("الاستراتيجية والتوصيات العملية", listToHtml(data.strategic_recommendations, true), { border: "border-gold-400/20", bg: "bg-gold-400/5" });

    case "drafting_notes":
      if (!hasList(data.drafting_notes)) return "";
      return cardHtml("ملاحظات الصياغة القانونية", listToHtml(data.drafting_notes), { titleColor: "text-purple-300" });

    case "missing_information":
      if (!hasList(data.missing_information)) return "";
      return cardHtml("معلومات أو مستندات ناقصة", listToHtml(data.missing_information), { border: "border-yellow-500/20", bg: "bg-yellow-500/5", titleColor: "text-yellow-300" });

    case "final_recommendation":
      if (!hasText(data.final_recommendation)) return "";
      return cardHtml("التوصية النهائية", `<p>${textWithBreaks(data.final_recommendation)}</p>`, { border: "border-gold-400/20", bg: "bg-gold-400/5" });

    case "source_limitations":
      if (!hasList(data.source_limitations)) return "";
      return cardHtml("حدود المصادر المتاحة", listToHtml(data.source_limitations), { border: "border-yellow-500/20", bg: "bg-yellow-500/5", titleColor: "text-yellow-300" });

    case "lawyer_summary":
      if (!hasText(data.lawyer_summary)) return "";
      return `
        <div class="glass-card rounded-2xl border border-gold-400/20 p-5">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs font-semibold text-gold-400">ملخص جاهز للمحامي</div>
            <button id="copy-summary-btn" class="text-xs text-slate-400 hover:text-white border border-white/10 hover:border-white/20 rounded-lg px-3 py-1 transition-all">نسخ</button>
          </div>
          <p id="res-lawyer-summary" class="text-sm text-slate-300 leading-relaxed bg-white/5 rounded-xl p-4">${textWithBreaks(data.lawyer_summary)}</p>
        </div>
      `;

    case "professional_tools":
      return renderProfessionalToolsCard(data);

    case "action_checklist":
      if (!hasList(data.action_checklist)) return "";
      return cardHtml(
        "قائمة تنفيذ عملية",
        listToHtml(data.action_checklist, true),
        { border: "border-green-500/20", bg: "bg-green-500/5", titleColor: "text-green-300" }
      );

    case "source_reasoning":
      if (!hasText(data.source_reasoning)) return "";
      return cardHtml(
        "لماذا اختار Mizan هذه المصادر؟",
        `<p>${textWithBreaks(data.source_reasoning)}</p>`,
        { border: "border-blue-500/20", bg: "bg-blue-500/5", titleColor: "text-blue-300" }
      );

    case "risk_matrix":
      if (!hasList(data.risk_matrix)) return "";
      return cardHtml(
        "مصفوفة المخاطر",
        listToHtml(data.risk_matrix),
        { border: "border-red-500/20", bg: "bg-red-500/5", titleColor: "text-red-300" }
      );

    case "litigation_timeline":
      if (!hasList(data.litigation_timeline)) return "";
      return cardHtml(
        "الخط الزمني الإجرائي",
        listToHtml(data.litigation_timeline, true),
        { border: "border-purple-500/20", bg: "bg-purple-500/5", titleColor: "text-purple-300" }
      );

    case "document_intelligence":
      if (!hasList(data.document_intelligence)) return "";
      return cardHtml(
        "ذكاء المستندات",
        listToHtml(data.document_intelligence),
        { border: "border-blue-500/20", bg: "bg-blue-500/5", titleColor: "text-blue-300" }
      );

    case "confidence": {
      if (!hasText(data.confidence_level) && !hasText(data.confidence_reason) && !hasText(data.legal_accuracy_note)) return "";
      const confLevel = (data.confidence_level || "").trim();
      const confColor = confLevel === "مرتفع" ? "green" : confLevel === "متوسط" ? "yellow" : "red";
      const confBorderBg = confLevel === "مرتفع"
        ? "border-green-500/20 bg-green-500/5"
        : confLevel === "متوسط"
        ? "border-yellow-500/20 bg-yellow-500/5"
        : "border-red-500/20 bg-red-500/5";
      const confTitleColor = confLevel === "مرتفع" ? "text-green-300" : confLevel === "متوسط" ? "text-yellow-300" : "text-red-300";
      const confIcon = confLevel === "مرتفع" ? "✅" : confLevel === "متوسط" ? "🔶" : "🔴";
      return cardHtml(
        `${confIcon} درجة الثقة بالتحليل`,
        `
          ${confLevel ? `<p><strong class="${confTitleColor}">مستوى الثقة: ${escapeHtml(confLevel)}</strong></p>` : ""}
          ${data.confidence_reason ? `<p class="mt-2 text-slate-300">${textWithBreaks(data.confidence_reason)}</p>` : ""}
          ${data.legal_accuracy_note && data.legal_accuracy_note !== data.confidence_reason ? `<p class="mt-2 text-xs text-slate-400">${textWithBreaks(data.legal_accuracy_note)}</p>` : ""}
        `,
        { border: confBorderBg.split(" ")[0], bg: confBorderBg.split(" ")[1], titleColor: confTitleColor }
      );
    }

    case "legal_sources":
      if (!hasList(data.legal_sources)) return "";
      return cardHtml(
        "المصادر القانونية المسترجعة من قاعدة بيانات Mizan",
        renderLegalSourcesHtml(data.legal_sources),
        { border: "border-blue-500/20", bg: "bg-blue-500/5", titleColor: "text-blue-300" }
      );

    case "disclaimer":
      if (!hasText(data.disclaimer)) return "";
      return `
        <div class="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4">
          <p class="text-xs text-slate-400 leading-relaxed">${textWithBreaks(data.disclaimer)}</p>
        </div>
      `;

    default:
      return "";
  }
}

function renderMetaHeader(data) {
  const detectedCaseType = data.detected_case_type || "غير محدد";
  const selectedCaseType = data.selected_case_type || "غير محدد";
  const assistantModeLabel = getRequestTypeLabel(data.assistant_mode || data.request_type || "");
  const audienceLabel = data.persona_label || getAudienceLabel(data.audience_mode || data.effective_user_role || "");
  const correctionNote = data.case_type_correction_note || "";

  return `
    <div class="glass-card rounded-2xl border border-white/10 p-4">
      <div class="flex flex-wrap gap-2 mb-2">
        ${assistantModeLabel ? badge(assistantModeLabel, "bg-gold-400/10 border-gold-400/30 text-gold-200") : ""}
        ${audienceLabel ? badge(`طريقة الرد: ${audienceLabel}`, "bg-blue-500/10 border-blue-400/30 text-blue-200") : ""}
        ${detectedCaseType && detectedCaseType !== "غير محدد" ? badge(`نوع القضية: ${detectedCaseType}`, "bg-purple-500/10 border-purple-400/30 text-purple-200") : ""}
      </div>
      ${correctionNote ? `<p class="text-xs text-amber-300 mt-2 leading-relaxed">${escapeHtml(correctionNote)}</p>` : ""}
    </div>
  `;
}

function summarizeAnswerForHistory(data) {
  const parts = [
    data.professional_summary,
    data.short_answer,
    data.legal_classification,
    data.final_recommendation,
    data.case_type_correction_note,
  ].filter(Boolean);

  return parts.join("\n").slice(0, 900);
}

function addConversationTurn(question, data) {
  conversationHistory.push({
    role: "user",
    content: question,
  });

  conversationHistory.push({
    role: "assistant",
    content: summarizeAnswerForHistory(data),
    request_type: data.request_type || "",
    detected_case_type: data.detected_case_type || "",
    selected_case_type: data.selected_case_type || "",
  });

  if (conversationHistory.length > 12) {
    conversationHistory = conversationHistory.slice(conversationHistory.length - 12);
  }

  renderConversationHistoryPanel();
}

function getConversationHistoryForApi() {
  return conversationHistory.slice(-8);
}

function clearConversationHistory() {
  conversationHistory = [];
  renderConversationHistoryPanel();
}

function renderConversationHistoryPanel() {
  const box = $("conversation-box");
  const panel = $("conversation-history-panel");

  if (!box || !panel) return;

  if (!conversationHistory.length) {
    box.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }

  box.classList.remove("hidden");

  panel.innerHTML = conversationHistory.slice(-8).map((item) => {
    const isUser = item.role === "user";

    return `
      <div class="rounded-xl ${isUser ? "bg-white/5 border-white/10" : "bg-gold-400/10 border-gold-400/20"} border p-3">
        <div class="text-[11px] ${isUser ? "text-slate-400" : "text-gold-300"} mb-1">
          ${isUser ? "أنت" : "Mizan"}
        </div>
        <div class="text-xs text-slate-200 leading-relaxed">
          ${textWithBreaks(String(item.content || "").slice(0, 350))}
        </div>
      </div>
    `;
  }).join("");
}

function renderSourceMissingAlert(data) {
  // Show alert if Mizan has no valid sources for the question
  const limitations = asArray(data.source_limitations);
  const confidence = (data.confidence_level || "").trim();
  const sourceSummary = data.mizan_sources_summary || "";
  const hasSources = hasList(data.legal_sources);

  if (confidence === "منخفض" && limitations.length > 0) {
    return `
      <div class="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5">
        <div class="flex items-start gap-3">
          <div class="text-amber-400 text-lg mt-0.5">⚠️</div>
          <div>
            <div class="text-sm font-semibold text-amber-300 mb-1">تنبيه: مصادر معتمدة محدودة</div>
            <p class="text-xs text-slate-300 leading-relaxed">
              ${escapeHtml(limitations[0] || "لا توجد مصادر قانونية معتمدة كافية داخل Mizan لهذا السؤال.")}
            </p>
            ${!hasSources ? `<p class="text-xs text-amber-200 mt-2 font-medium">لا توجد مصادر معتمدة كافية داخل Mizan للإجابة الجازمة على هذا السؤال.</p>` : ""}
          </div>
        </div>
      </div>
    `;
  }
  return "";
}

function renderLegalResult(data, questionText = "") {
  showOnly("result-state");

  const resultState = $("result-state");
  if (!resultState) return;

  const cardsToShow = getCardsToShow(data);
  const htmlParts = [];

  // Source missing alert — shown BEFORE cards
  const sourceMissingAlert = renderSourceMissingAlert(data);
  if (sourceMissingAlert) htmlParts.push(sourceMissingAlert);

  // Uploaded files display
  if (hasList(data.uploaded_documents)) {
    htmlParts.push(cardHtml(
      "الملفات المستخدمة في التحليل",
      listToHtml(data.uploaded_documents.map((doc) => {
        if (!doc || typeof doc !== "object") return doc;
        const sizeKb = doc.size_bytes ? Math.round(Number(doc.size_bytes) / 1024) : "";
        return `${doc.filename || "ملف"}${sizeKb ? ` — ${sizeKb}KB` : ""}`;
      })),
      { border: "border-blue-500/20", bg: "bg-blue-500/5", titleColor: "text-blue-300" }
    ));
  }

  cardsToShow.forEach((cardName) => {
    const html = renderCardByName(cardName, data);
    if (html) htmlParts.push(html);
  });

  htmlParts.push(`<div id="workspace-tool-results" class="space-y-4"></div>`);

  htmlParts.push(`
    <div class="glass-card rounded-2xl border border-white/10 p-4">
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex-1">
          <p class="text-xs text-slate-400 mb-2">هل كان التحليل مفيدًا؟</p>
          <div class="flex gap-2">
            <button id="feedback-positive-btn" class="flex items-center gap-1 text-xs px-3 py-2 rounded-xl bg-green-500/10 border border-green-500/20 text-green-300 hover:bg-green-500/20 transition-all" data-rating="1">
              👍 مفيد
            </button>
            <button id="feedback-negative-btn" class="flex items-center gap-1 text-xs px-3 py-2 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 hover:bg-red-500/20 transition-all" data-rating="-1">
              👎 غير مفيد
            </button>
            <span id="feedback-thanks" class="hidden text-xs text-green-300 self-center">✅ شكراً على تقييمك</span>
          </div>
        </div>
        <div class="flex gap-2">
          <button id="export-copy-btn" class="text-xs px-3 py-2 rounded-xl border border-white/10 text-slate-300 hover:text-white hover:border-white/20 transition-all">
            📋 نسخ الخلاصة
          </button>
          <a href="/analysis-history" class="text-xs px-3 py-2 rounded-xl border border-white/10 text-slate-300 hover:text-white hover:border-white/20 transition-all">
            📂 السجل
          </a>
          <button id="new-analysis-btn" class="text-xs px-3 py-2 rounded-xl bg-white/10 text-white hover:bg-white/15 transition-all">
            + جديد
          </button>
        </div>
      </div>
    </div>
  `);

  resultState.innerHTML = htmlParts.join("");
  window._lastAnalysisData = data || {};
  try {
    localStorage.setItem("mizan_last_analysis", JSON.stringify(data || {}));
  } catch (e) {
    console.warn("Could not save last analysis", e);
  }

  if (questionText) {
    addConversationTurn(questionText, data);
  }

  setupDynamicResultButtons();
}

function renderDocumentResult(data) {
  showOnly("document-result-state");

  const documentState = $("document-result-state");
  if (!documentState) return;

  const cards = [];

  // Operational/debug badges are intentionally hidden from document analysis output.
  if (hasList(data.uploaded_documents)) {
    cards.push(cardHtml(
      "الملفات التي تم تحليلها",
      listToHtml(data.uploaded_documents.map((doc) => {
        if (!doc || typeof doc !== "object") return doc;
        const sizeKb = doc.size_bytes ? Math.round(Number(doc.size_bytes) / 1024) : "";
        return `${doc.filename || "ملف"}${sizeKb ? ` — ${sizeKb}KB` : ""}`;
      })),
      { border: "border-blue-500/20", bg: "bg-blue-500/5", titleColor: "text-blue-300" }
    ));
  }

  if (hasText(data.summary)) {
    cards.push(cardHtml(
      "ملخص المستند",
      `<p>${textWithBreaks(data.summary)}</p>`,
      { border: "border-gold-400/20", bg: "bg-gold-400/5" }
    ));
  }

  if (hasList(data.parties)) {
    cards.push(cardHtml("الأطراف", listToHtml(data.parties)));
  }

  if (hasList(data.main_obligations)) {
    cards.push(cardHtml("الالتزامات الرئيسية", listToHtml(data.main_obligations)));
  }

  if (hasList(data.risky_clauses)) {
    cards.push(cardHtml(
      "البنود الخطرة",
      listToHtml(data.risky_clauses),
      { border: "border-red-500/20", bg: "bg-red-500/5", titleColor: "text-red-300" }
    ));
  }

  if (hasList(data.legal_gaps)) {
    cards.push(cardHtml(
      "الثغرات القانونية",
      listToHtml(data.legal_gaps),
      { border: "border-yellow-500/20", bg: "bg-yellow-500/5", titleColor: "text-yellow-300" }
    ));
  }

  if (hasList(data.missing_clauses)) {
    cards.push(cardHtml("البنود الناقصة", listToHtml(data.missing_clauses), { titleColor: "text-blue-300" }));
  }

  if (hasList(data.suggested_edits)) {
    cards.push(cardHtml(
      "تعديلات مقترحة",
      listToHtml(data.suggested_edits),
      { border: "border-green-500/20", bg: "bg-green-500/5", titleColor: "text-green-300" }
    ));
  }

  if (hasList(data.verified_legal_materials)) {
    cards.push(cardHtml(
      "مواد أو نصوص مؤكدة",
      listToHtml(data.verified_legal_materials),
      { border: "border-green-500/20", bg: "bg-green-500/5", titleColor: "text-green-300" }
    ));
  }

  if (hasList(data.unverified_legal_points)) {
    cards.push(cardHtml(
      "نقاط تحتاج تحقق",
      listToHtml(data.unverified_legal_points),
      { border: "border-yellow-500/20", bg: "bg-yellow-500/5", titleColor: "text-yellow-300" }
    ));
  }

  if (hasText(data.risk_level) || hasText(data.lawyer_summary)) {
    cards.push(cardHtml(
      "مستوى الخطورة وملخص للمحامي",
      `
        ${data.risk_level ? `<p><strong>مستوى الخطورة:</strong> ${escapeHtml(data.risk_level)}</p>` : ""}
        ${data.lawyer_summary ? `<p class="mt-3">${textWithBreaks(data.lawyer_summary)}</p>` : ""}
      `,
      { border: "border-gold-400/20", bg: "bg-gold-400/5" }
    ));
  }

  if (hasText(data.disclaimer)) {
    cards.push(`
      <div class="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4">
        <p class="text-xs text-slate-400 leading-relaxed">${textWithBreaks(data.disclaimer)}</p>
      </div>
    `);
  }

  documentState.innerHTML = cards.join("");
}

function renderError(message) {
  showOnly("result-state");

  const resultState = $("result-state");
  if (!resultState) return;

  resultState.innerHTML = `
    ${cardHtml(
      "حدث خطأ",
      `<p class="text-red-200">${escapeHtml(message || "حدث خطأ غير متوقع.")}</p>`,
      { border: "border-red-500/20", bg: "bg-red-500/5", titleColor: "text-red-300" }
    )}
    <button id="new-analysis-btn" class="w-full py-3 rounded-xl border border-white/15 text-sm text-slate-300 hover:text-white hover:border-white/30 hover:bg-white/5 transition-all">
      بدء تحليل جديد
    </button>
  `;

  setupDynamicResultButtons();
}

function resetCurrentQuestionInput() {
  const q = $("question-input");
  if (q) q.value = "";

  const c = $("char-count");
  if (c) c.textContent = "0 حرف";
}


async function runWorkspaceToolFromResult(button) {
  const currentAnalysisData = window._lastAnalysisData || {};
  const toolLabel = button.dataset.toolLabel || button.textContent.trim();
  const toolKey = button.dataset.toolKey || "";
  const questionText = conversationHistory.length ? conversationHistory[conversationHistory.length - 1]?.question || "" : valueOf("question-input", "");

  button.disabled = true;
  const originalHtml = button.innerHTML;
  button.innerHTML = `<div class="text-sm font-semibold text-white">جاري إنشاء ${escapeHtml(toolLabel)}...</div>`;

  try {
    const payload = {
      tool_key: toolKey,
      tool_label: toolLabel,
      question: questionText || currentAnalysisData.short_answer || currentAnalysisData.professional_summary || "استخدم التحليل السابق لبناء الأداة المطلوبة.",
      country: valueOf("country", "الأردن"),
      case_type: getSelectedCaseType(),
      selected_case_type: getSelectedCaseType(),
      assistant_mode: "workspace_tool",
      audience_mode: valueOf("audience-mode-select", getAssistantPageConfig().userRole || "individual"),
      case_id: valueOf("case-id-select", "") ? parseInt(valueOf("case-id-select", "")) : null,
      analysis: currentAnalysisData,
      used_tools: currentAnalysisData._used_workspace_tools || [],
      available_tools: asArray(currentAnalysisData.professional_tools).map((tool) => normalizeToolItem(tool).label),
    };

    const response = await fetch("/api/workspace-tool", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await parseApiResponse(response);
    if (!response.ok) throw new Error(data.detail || data.error || "تعذر تشغيل الأداة.");

    currentAnalysisData._used_workspace_tools = [...(currentAnalysisData._used_workspace_tools || []), data.tool_label || toolLabel];
    currentAnalysisData.workspace_tool_outputs = [...(currentAnalysisData.workspace_tool_outputs || []), data];
    if (hasList(data.remaining_tools)) {
      currentAnalysisData.professional_tools = data.remaining_tools;
      const toolsCard = $("professional-tools-card");
      if (toolsCard) {
        const replacement = renderProfessionalToolsCard(currentAnalysisData);
        if (replacement) toolsCard.outerHTML = replacement;
        else toolsCard.remove();
      }
    }

    const resultsBox = $("workspace-tool-results");
    if (resultsBox) {
      resultsBox.insertAdjacentHTML("afterbegin", renderWorkspaceToolOutput(data));
    }
    setupDynamicResultButtons();
  } catch (error) {
    console.error("Workspace tool error", error);
    button.disabled = false;
    button.innerHTML = originalHtml;
    const resultsBox = $("workspace-tool-results");
    if (resultsBox) {
      resultsBox.insertAdjacentHTML("afterbegin", cardHtml("تعذر تشغيل الأداة", `<p class="text-red-200">${escapeHtml(error.message || "حدث خطأ أثناء توليد الأداة.")}</p>`, { border: "border-red-500/20", bg: "bg-red-500/5", titleColor: "text-red-300" }));
    }
  }
}

function setupDynamicResultButtons() {
  const newButton = $("new-analysis-btn");
  if (newButton) {
    newButton.addEventListener("click", () => {
      showOnly("empty-state");
      resetCurrentQuestionInput();
      clearConversationHistory();
    });
  }

  const copyButton = $("copy-summary-btn");
  if (copyButton) {
    copyButton.addEventListener("click", async () => {
      const summary = $("res-lawyer-summary")?.textContent || "";
      if (!summary) return;
      await navigator.clipboard.writeText(summary);
      copyButton.textContent = "تم النسخ";
      setTimeout(() => { copyButton.textContent = "نسخ"; }, 1500);
    });
  }

  const exportCopyBtn = $("export-copy-btn");
  if (exportCopyBtn) {
    exportCopyBtn.addEventListener("click", async () => {
      const resultState = $("result-state");
      const summary = $("res-lawyer-summary")?.textContent?.trim()
        || resultState?.querySelector(".text-gold-400 + p")?.textContent?.trim()
        || "";
      const allText = resultState?.innerText?.trim() || "";
      const textToCopy = summary || allText.slice(0, 2000);
      if (!textToCopy) return;
      try {
        await navigator.clipboard.writeText(textToCopy);
        exportCopyBtn.textContent = "✅ تم النسخ";
        setTimeout(() => { exportCopyBtn.textContent = "📋 نسخ الخلاصة"; }, 1800);
      } catch {
        exportCopyBtn.textContent = "خطأ في النسخ";
      }
    });
  }

  const currentAnalysisData = window._lastAnalysisData || {};
  [
    { id: "feedback-positive-btn", rating: 1 },
    { id: "feedback-negative-btn", rating: -1 },
  ].forEach(({ id, rating }) => {
    const btn = $(id);
    if (!btn) return;
    btn.addEventListener("click", async () => {
      try {
        const body = {
          analysis_id: currentAnalysisData.id || currentAnalysisData.analysis_id || null,
          rating,
          comment: "",
          assistant_mode: currentAnalysisData.assistant_mode || "",
          confidence_level: currentAnalysisData.confidence_level || "",
        };
        await fetch("/api/analysis-feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const thanks = $("feedback-thanks");
        if (thanks) thanks.classList.remove("hidden");
        $("feedback-positive-btn")?.setAttribute("disabled", "true");
        $("feedback-negative-btn")?.setAttribute("disabled", "true");
      } catch (e) {
        console.error("Feedback error", e);
      }
    });
  });

  document.querySelectorAll(".workspace-tool-btn").forEach((btn) => {
    if (btn.dataset.bound === "true") return;
    btn.dataset.bound = "true";
    btn.addEventListener("click", () => runWorkspaceToolFromResult(btn));
  });

  document.querySelectorAll(".copy-generated-tool-btn").forEach((btn) => {
    if (btn.dataset.bound === "true") return;
    btn.dataset.bound = "true";
    btn.addEventListener("click", async () => {
      const content = btn.closest(".glass-card")?.querySelector(".generated-tool-content")?.textContent || "";
      if (!content) return;
      try {
        await navigator.clipboard.writeText(content);
        btn.textContent = "تم النسخ";
        setTimeout(() => { btn.textContent = "نسخ"; }, 1500);
      } catch (e) {
        console.error("Copy generated tool error", e);
      }
    });
  });
}

function setupConversationControls() {
  const clearButton = $("clear-conversation-btn");

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      clearConversationHistory();
    });
  }
}

function setupCounters() {
  const questionInput = $("question-input");
  const charCount = $("char-count");

  if (questionInput && charCount) {
    const update = () => {
      charCount.textContent = `${questionInput.value.length} حرف`;
    };

    questionInput.addEventListener("input", update);
    update();
  }
}

function setupCriminalToggle() {
  const caseType = $("case-type-select");
  const panel = $("criminal-details-panel");

  if (!caseType || !panel) return;

  const toggle = () => {
    if (caseType.value === "جنائي") {
      panel.classList.remove("hidden");
    } else {
      panel.classList.add("hidden");
    }
  };

  caseType.addEventListener("change", toggle);
  toggle();
}

function setupEnterToSend() {
  const questionInput = $("question-input");
  const button = $("analyze-btn");

  if (!questionInput || !button) return;

  questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      button.click();
    }
  });
}

function setupLegalAnalysis() {
  const button = $("analyze-btn");

  if (!button) return;

  button.addEventListener("click", async () => {
    const question = valueOf("question-input", "").trim();
    const questionFilesInput = $("question-files-input");
    const hasQuestionFiles = questionFilesInput && questionFilesInput.files && questionFilesInput.files.length > 0;

    if (!question && !hasQuestionFiles) {
      renderError("يرجى كتابة السؤال القانوني أو رفع ملف مرتبط بالسؤال.");
      return;
    }

    const criminalDetails = {
      alleged_crime: valueOf("alleged-crime-input", ""),
      has_prior_record: valueOf("has-prior-record-select", "غير معروف"),
      prior_count: valueOf("prior-count-input", ""),
      confession: valueOf("confession-select", "غير معروف"),
      witnesses: valueOf("witnesses-select", "غير معروف"),
      harm: valueOf("harm-select", "غير معروف"),
      mitigating_factors: valueOf("mitigating-factors-input", ""),
      aggravating_factors: valueOf("aggravating-factors-input", ""),
    };

    const payload = {
      question,
      country: valueOf("country", ""),
      case_type: getSelectedCaseType(),
      selected_case_type: getSelectedCaseType(),
      assistant_mode: valueOf("assistant-mode-select", "case_analysis"),
      audience_mode: valueOf("audience-mode-select", getAssistantPageConfig().userRole || "individual"),
      conversation_history: getConversationHistoryForApi(),
      case_id: valueOf("case-id-select", "") ? Number(valueOf("case-id-select", "")) : null,
      criminal_details: criminalDetails,
    };

    try {
      const _modeEl = document.getElementById("assistant-mode-select");
      const _modeVal = _modeEl ? _modeEl.value : "case_analysis";
      const _modeMessages = {
        legal_research: "جاري البحث في التشريعات المعتمدة...",
        case_analysis: "جاري تحليل الوقائع قانونيًا...",
        document_analysis: "جاري تحليل المستندات القانونية...",
        contract_review: "جاري مراجعة العقد وتحديد المخاطر...",
        legal_drafting: "جاري إعداد الصياغة القانونية...",
        litigation_strategy: "جاري بناء الاستراتيجية القضائية...",
        corporate_advisory: "جاري تحليل المخاطر المؤسسية...",
      };
      const _loadingMsg = hasQuestionFiles
        ? "جاري تحليل المستندات مع السؤال القانوني..."
        : (conversationHistory.length ? "جاري متابعة النقاش القانوني..." : (_modeMessages[_modeVal] || "جاري التحليل القانوني..."));
      setLoading(true, _loadingMsg);

      let response;

      if (hasQuestionFiles) {
        const formData = new FormData();
        for (const file of questionFilesInput.files) {
          formData.append("files", file);
        }
        formData.append("question", question || "حلل الملفات المرفقة واشرح القضية أو الموقف القانوني المرتبط بها.");
        formData.append("country", payload.country || "");
        formData.append("case_type", payload.case_type || "غير محدد");
        formData.append("selected_case_type", payload.selected_case_type || "غير محدد");
        formData.append("assistant_mode", payload.assistant_mode || "case_analysis");
        formData.append("audience_mode", payload.audience_mode || "individual");
        formData.append("case_id", payload.case_id ? String(payload.case_id) : "");
        formData.append("conversation_history", JSON.stringify(payload.conversation_history || []));
        formData.append("criminal_details", JSON.stringify(criminalDetails || {}));

        response = await fetch("/api/analyze-with-documents", {
          method: "POST",
          body: formData,
        });
      } else {
        response = await fetch("/api/analyze", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
      }

      const data = await parseApiResponse(response);

      if (response.status === 401) {
        renderError(data.detail || "يجب تسجيل الدخول أولًا.");
        return;
      }

      if (!response.ok) {
        throw new Error(data.detail || "حدث خطأ أثناء التحليل.");
      }

      renderLegalResult(data, question || "تحليل الملفات المرفقة");
      resetCurrentQuestionInput();
      if (questionFilesInput) questionFilesInput.value = "";
    } catch (error) {
      console.error(error);
      renderError(error.message || "حدث خطأ أثناء التحليل.");
    } finally {
      setLoading(false);
    }
  });
}

function setupDocumentAnalysis() {
  const button = $("analyze-document-btn");

  if (!button) return;

  button.addEventListener("click", async () => {
    const fileInput = $("document-file-input");

    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
      renderError("يرجى رفع ملف واحد على الأقل لتحليله.");
      return;
    }

    const formData = new FormData();

    for (const file of fileInput.files) {
      formData.append("files", file);
    }

    formData.append("country", valueOf("country", ""));
    formData.append("document_type", valueOf("document-type-select", "مستند قانوني"));
    formData.append("plan", "");
    formData.append("question", valueOf("document-question-input", ""));
    formData.append("case_id", valueOf("case-id-select", ""));
    formData.append("selected_case_type", getSelectedCaseType());
    formData.append("assistant_mode", valueOf("assistant-mode-select", "document_analysis"));

    try {
      setLoading(true, fileInput.files.length > 1 ? "جاري تحليل المستندات..." : "جاري تحليل المستند...");

      const response = await fetch("/api/analyze-document", {
        method: "POST",
        body: formData,
      });

      const data = await parseApiResponse(response);

      if (response.status === 401) {
        renderError(data.detail || "يجب تسجيل الدخول أولًا.");
        return;
      }

      if (!response.ok) {
        throw new Error(data.detail || "حدث خطأ أثناء تحليل المستندات.");
      }

      renderDocumentResult(data);
      fileInput.value = "";
    } catch (error) {
      console.error(error);
      renderError(error.message || "حدث خطأ أثناء تحليل المستندات.");
    } finally {
      setLoading(false);
    }
  });
}

function initAssistantPage() {
  console.log("✅ initAssistantPage case type + conversation started");

  setupCounters();
  setupCriminalToggle();
  setupLegalAnalysis();
  setupDocumentAnalysis();
  setupDynamicResultButtons();
  setupConversationControls();
  setupEnterToSend();
  renderConversationHistoryPanel();

  console.log("✅ initAssistantPage case type + conversation finished");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAssistantPage);
} else {
  initAssistantPage();
}