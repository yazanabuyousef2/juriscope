console.log("✅ Mizan assistant.js case type + conversation v20260528-2");

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
  setButtonLoading("analyze-document-btn", show, "تحليل المستند", "جاري تحليل المستند...");
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
    general_question: "سؤال قانوني عام",
    case_analysis: "تحليل حالة",
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
    individual: "فرد",
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
  const requestType = data.request_type || "general_question";
  const audienceMode = data.audience_mode || "individual";

  if (requestType === "legal_article_request") {
    return [
      "case_type_correction",
      "short_answer",
      "articles_requested",
      "verified_legal_materials",
      "mizan_sources_summary",
      "legal_sources",
      "disclaimer",
    ];
  }

  if (requestType === "legislation_request") {
    return [
      "case_type_correction",
      "short_answer",
      "legislation_summary",
      "verified_legal_materials",
      "mizan_sources_summary",
      "legal_sources",
      "disclaimer",
    ];
  }

  if (requestType === "procedure_guidance") {
    return [
      "case_type_correction",
      "short_answer",
      "plain_explanation",
      "procedure_steps",
      "relevant_documents",
      "when_to_consult_lawyer",
      "disclaimer",
    ];
  }

  if (requestType === "general_question") {
    if (audienceMode === "lawyer") {
      return [
        "case_type_correction",
        "short_answer",
        "legal_basis",
        "verified_legal_materials",
        "unverified_legal_points",
        "confidence",
        "disclaimer",
      ];
    }

    if (audienceMode === "law_student") {
      return [
        "case_type_correction",
        "short_answer",
        "plain_explanation",
        "legal_basis",
        "educational_notes",
        "verified_legal_materials",
        "disclaimer",
      ];
    }

    if (audienceMode === "company") {
      return [
        "case_type_correction",
        "short_answer",
        "plain_explanation",
        "practical_meaning",
        "legal_basis",
        "business_risks",
        "disclaimer",
      ];
    }

    return [
      "case_type_correction",
      "short_answer",
      "plain_explanation",
      "practical_meaning",
      "legal_basis",
      "when_to_consult_lawyer",
      "disclaimer",
    ];
  }

  if (requestType === "lawyer_brief") {
    return [
      "case_type_correction",
      "short_answer",
      "case_understanding",
      "legal_classification",
      "legal_basis",
      "proof_points",
      "defenses_or_arguments",
      "key_risks",
      "lawyer_summary",
      "verified_legal_materials",
      "legal_sources",
      "disclaimer",
    ];
  }

  if (requestType === "case_analysis") {
    if (audienceMode === "individual") {
      return [
        "case_type_correction",
        "short_answer",
        "plain_explanation",
        "practical_meaning",
        "legal_classification",
        "key_risks",
        "relevant_documents",
        "next_steps",
        "when_to_consult_lawyer",
        "verified_legal_materials",
        "disclaimer",
      ];
    }

    if (audienceMode === "company") {
      return [
        "case_type_correction",
        "short_answer",
        "case_understanding",
        "legal_classification",
        "business_risks",
        "key_risks",
        "relevant_documents",
        "next_steps",
        "verified_legal_materials",
        "disclaimer",
      ];
    }

    if (audienceMode === "lawyer") {
      return [
        "case_type_correction",
        "short_answer",
        "case_understanding",
        "legal_classification",
        "legal_basis",
        "analysis_based_on_sources",
        "proof_points",
        "defenses_or_arguments",
        "key_risks",
        "relevant_documents",
        "lawyer_summary",
        "verified_legal_materials",
        "legal_sources",
        "confidence",
        "disclaimer",
      ];
    }

    if (audienceMode === "law_student") {
      return [
        "case_type_correction",
        "short_answer",
        "plain_explanation",
        "legal_classification",
        "legal_basis",
        "educational_notes",
        "next_steps",
        "verified_legal_materials",
        "disclaimer",
      ];
    }

    return [
      "case_type_correction",
      "short_answer",
      "case_understanding",
      "legal_classification",
      "key_risks",
      "next_steps",
      "verified_legal_materials",
      "disclaimer",
    ];
  }

  return [
    "case_type_correction",
    "short_answer",
    "plain_explanation",
    "disclaimer",
  ];
}

function getCardsToShow(data) {
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

    case "confidence":
      if (!hasText(data.confidence_level) && !hasText(data.confidence_reason) && !hasText(data.legal_accuracy_note)) return "";
      return cardHtml(
        "مستوى الثقة والدقة القانونية",
        `
          <div class="space-y-3">
            ${data.confidence_level ? `<p><strong>مستوى الثقة:</strong> ${escapeHtml(data.confidence_level)}</p>` : ""}
            ${data.confidence_reason ? `<p>${textWithBreaks(data.confidence_reason)}</p>` : ""}
            ${data.legal_accuracy_note ? `<p class="text-yellow-200">${textWithBreaks(data.legal_accuracy_note)}</p>` : ""}
          </div>
        `,
        { border: "border-yellow-500/20", bg: "bg-yellow-500/5", titleColor: "text-yellow-300" }
      );

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
  const selectedCaseType = data.selected_case_type || "غير محدد";
  const detectedCaseType = data.detected_case_type || "غير محدد";

  return `
    <div class="glass-card rounded-2xl border border-white/10 p-4">
      <div class="flex flex-wrap gap-2">
        ${badge(getRequestTypeLabel(data.request_type), "bg-gold-400/10 border-gold-400/30 text-gold-200")}
        ${badge(getAudienceLabel(data.audience_mode), "bg-blue-500/10 border-blue-400/30 text-blue-200")}
        ${badge(`نوع القضية: ${detectedCaseType}`, "bg-purple-500/10 border-purple-400/30 text-purple-200")}
        ${selectedCaseType && selectedCaseType !== "غير محدد" ? badge(`اختيارك: ${selectedCaseType}`, "bg-white/5 border-white/10 text-slate-300") : ""}
        ${data.session_mode === "staff_unlimited" ? badge("Staff Unlimited", "bg-yellow-500/10 border-yellow-400/30 text-yellow-200") : ""}
      </div>
      ${data.staff_mode_note ? `<p class="mt-3 text-xs text-yellow-200">${escapeHtml(data.staff_mode_note)}</p>` : ""}
    </div>
  `;
}

function summarizeAnswerForHistory(data) {
  const parts = [
    data.short_answer,
    data.legal_classification,
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

function renderLegalResult(data, questionText = "") {
  showOnly("result-state");

  const resultState = $("result-state");
  if (!resultState) return;

  const cardsToShow = getCardsToShow(data);
  const htmlParts = [];

  htmlParts.push(renderMetaHeader(data));

  cardsToShow.forEach((cardName) => {
    const html = renderCardByName(cardName, data);
    if (html) htmlParts.push(html);
  });

  htmlParts.push(`
    <button id="new-analysis-btn" class="w-full py-3 rounded-xl border border-white/15 text-sm text-slate-300 hover:text-white hover:border-white/30 hover:bg-white/5 transition-all">
      بدء تحليل جديد
    </button>
  `);

  resultState.innerHTML = htmlParts.join("");

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

  cards.push(renderMetaHeader({
    request_type: "document_analysis",
    audience_mode: data.audience_mode || "",
    session_mode: data.session_mode || "",
    staff_mode_note: data.staff_mode_note || "",
    detected_case_type: data.detected_case_type || "غير محدد",
    selected_case_type: data.selected_case_type || "غير محدد",
  }));

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

      setTimeout(() => {
        copyButton.textContent = "نسخ";
      }, 1500);
    });
  }
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

    if (!question) {
      renderError("يرجى كتابة السؤال القانوني أولًا.");
      return;
    }

    const payload = {
      question,
      country: valueOf("country", ""),
      case_type: getSelectedCaseType(),
      selected_case_type: getSelectedCaseType(),
      conversation_history: getConversationHistoryForApi(),
      case_id: valueOf("case-id-select", "") ? Number(valueOf("case-id-select", "")) : null,
      criminal_details: {
        alleged_crime: valueOf("alleged-crime-input", ""),
        has_prior_record: valueOf("has-prior-record-select", "غير معروف"),
        prior_count: valueOf("prior-count-input", ""),
        confession: valueOf("confession-select", "غير معروف"),
        witnesses: valueOf("witnesses-select", "غير معروف"),
        harm: valueOf("harm-select", "غير معروف"),
        mitigating_factors: valueOf("mitigating-factors-input", ""),
        aggravating_factors: valueOf("aggravating-factors-input", ""),
      },
    };

    try {
      setLoading(true, conversationHistory.length ? "جاري متابعة النقاش..." : "جاري تجهيز الرد القانوني...");

      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const data = await parseApiResponse(response);

      if (response.status === 401) {
        renderError(data.detail || "يجب تسجيل الدخول أولًا.");
        return;
      }

      if (!response.ok) {
        throw new Error(data.detail || "حدث خطأ أثناء التحليل.");
      }

      renderLegalResult(data, question);
      resetCurrentQuestionInput();
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
      renderError("يرجى رفع ملف لتحليله.");
      return;
    }

    const formData = new FormData();

    formData.append("file", fileInput.files[0]);
    formData.append("country", valueOf("country", ""));
    formData.append("document_type", valueOf("document-type-select", "مستند قانوني"));
    formData.append("plan", "");
    formData.append("question", valueOf("document-question-input", ""));
    formData.append("case_id", valueOf("case-id-select", ""));
    formData.append("selected_case_type", getSelectedCaseType());

    try {
      setLoading(true, "جاري تحليل المستند...");

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
        throw new Error(data.detail || "حدث خطأ أثناء تحليل المستند.");
      }

      renderDocumentResult(data);
    } catch (error) {
      console.error(error);
      renderError(error.message || "حدث خطأ أثناء تحليل المستند.");
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