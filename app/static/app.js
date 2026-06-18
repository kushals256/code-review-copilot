const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function showLoading(show) {
  $("#loading").classList.toggle("hidden", !show);
  $("#output").classList.toggle("hidden", show);
  $("#results").classList.remove("hidden");
  if (show) {
    $("#results-subtitle").textContent = "Running AI review…";
    setButtonsDisabled(true);
    $("#results").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } else {
    setButtonsDisabled(false);
  }
}

function setButtonsDisabled(disabled) {
  $$(".btn-primary, .btn-secondary").forEach((btn) => {
    btn.disabled = disabled;
  });
}

function scoreClass(score) {
  if (score >= 75) return "good";
  if (score >= 50) return "medium";
  return "bad";
}

function esc(str) {
  const d = document.createElement("div");
  d.textContent = str ?? "";
  return d.innerHTML;
}

function countSeverities(comments) {
  const counts = {};
  for (const c of comments) {
    counts[c.severity] = (counts[c.severity] || 0) + 1;
  }
  return counts;
}

function renderReview(data) {
  const review = data.review;
  const rs = review.risk_summary;
  const github = data.github || {};

  $("#results-subtitle").textContent = `PR #${review.pr_number} · ${review.repo}`;

  const sevCounts = countSeverities(review.comments);
  const sevTags = Object.entries(sevCounts)
    .map(([k, v]) => `<span class="result-stat">${esc(k)}: ${v}</span>`)
    .join("");

  let html = `
    <div class="result-stats">
      <span class="result-stat">${review.comments.length} comments</span>
      <span class="result-stat">Score ${rs.quality_score}/100</span>
      ${sevTags}
    </div>
    <div class="score-display">
      <div class="score-circle ${scoreClass(rs.quality_score)}">${rs.quality_score}</div>
      <div>
        <div class="merge-rec ${esc(rs.merge_recommendation)}">${esc(rs.merge_recommendation.replace(/_/g, " "))}</div>
        <p class="meta-text">${esc(rs.merge_rationale)}</p>
      </div>
    </div>
  `;

  if (github.comments_posted !== undefined) {
    html += `<p class="meta-text" style="margin-bottom:0.5rem">Posted <strong>${github.comments_posted}</strong> of <strong>${github.comments_total || review.comments.length}</strong> comments to GitHub</p>`;
  }

  if (rs.highest_risk_changes.length) {
    html += `<div class="section-title">Highest-Risk Changes</div><ul class="risk-list">`;
    for (const r of rs.highest_risk_changes) {
      html += `<li class="risk-item">
        <span class="severity-badge ${esc(r.severity)}">${esc(r.severity)}</span>
        <strong>${esc(r.file_path)}</strong>
        <span class="meta-text"> · risk ${r.risk_score}/10</span>
        <div class="comment-detail">${esc(r.description)}</div>
      </li>`;
    }
    html += `</ul>`;
  }

  if (review.comments.length) {
    html += `<div class="section-title">Inline Comments (${review.comments.length})</div><ul class="comment-list">`;
    for (const c of review.comments) {
      html += `<li class="comment-item">
        <div class="comment-meta">${esc(c.file_path)}:${c.line}</div>
        <span class="severity-badge ${esc(c.severity)}">${esc(c.severity)}</span>
        <div class="comment-issue">${esc(c.issue)}</div>
        <div class="comment-detail"><strong>Why:</strong> ${esc(c.why_it_matters)}</div>
        <div class="comment-detail"><strong>Fix:</strong> <code>${esc(c.suggested_fix)}</code></div>
        <div class="comment-detail"><strong>Learn:</strong> ${esc(c.explanation)}</div>
      </li>`;
    }
    html += `</ul>`;
  }

  if (review.conventions_applied.length) {
    html += `<div class="section-title">Conventions Applied</div><ul class="convention-list">`;
    for (const rule of review.conventions_applied) {
      html += `<li class="convention-item">${esc(rule)}</li>`;
    }
    html += `</ul>`;
  }

  $("#output").innerHTML = html;
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderConventions(data) {
  $("#results-subtitle").textContent = `Rules from ${data.repo}`;

  let html = `
    <div class="result-stats">
      <span class="result-stat">${data.rules.length} rules found</span>
      <span class="result-stat">${data.prs_analyzed} PRs scanned</span>
    </div>
  `;
  html += `<ul class="convention-list">`;
  for (const r of data.rules) {
    html += `<li class="convention-item">
      <span class="severity-badge suggestion">${Math.round(r.confidence * 100)}%</span>
      <strong>${esc(r.rule)}</strong>
      <div class="comment-detail">${esc(r.description)}</div>
      ${r.examples.length ? `<div class="comment-detail"><strong>Examples:</strong> ${esc(r.examples.join("; "))}</div>` : ""}
    </li>`;
  }
  html += `</ul>`;
  $("#output").innerHTML = html;
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function showError(msg) {
  $("#results").classList.remove("hidden");
  $("#results-subtitle").textContent = "Something went wrong";
  $("#output").innerHTML = `<div class="error-box">${esc(msg)}</div>`;
  $("#results").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function apiCall(endpoint, body) {
  showLoading(true);
  try {
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Request failed");
    return data;
  } finally {
    showLoading(false);
  }
}

function normalizeUrl(raw, type) {
  let url = raw.trim();
  if (!url) return "";
  if (!/^https?:\/\//i.test(url)) url = "https://" + url;
  if (type === "pr" && !/\/pull\/\d+/.test(url)) return "";
  return url;
}

$("#btn-review").addEventListener("click", async () => {
  const prUrl = normalizeUrl($("#pr-url").value, "pr");
  if (!prUrl) return showError("Enter a valid GitHub PR URL (e.g. github.com/owner/repo/pull/123)");

  const conventions = $("#conventions").value
    .split("\n").map((s) => s.trim()).filter(Boolean);

  try {
    const data = await apiCall("/api/review", { pr_url: prUrl, conventions });
    renderReview(data);
  } catch (e) {
    showError(e.message);
  }
});

$("#btn-dry-run").addEventListener("click", async () => {
  const prUrl = normalizeUrl($("#pr-url").value, "pr");
  if (!prUrl) return showError("Enter a valid GitHub PR URL (e.g. github.com/owner/repo/pull/123)");

  const conventions = $("#conventions").value
    .split("\n").map((s) => s.trim()).filter(Boolean);

  try {
    const data = await apiCall("/api/review/dry-run", { pr_url: prUrl, conventions });
    renderReview(data);
  } catch (e) {
    showError(e.message);
  }
});

$("#btn-extract").addEventListener("click", async () => {
  const repoUrl = normalizeUrl($("#repo-url").value, "repo");
  if (!repoUrl) return showError("Enter a valid GitHub repo URL (e.g. github.com/owner/repo)");

  try {
    const data = await apiCall("/api/conventions/extract", { repo_url: repoUrl, max_prs: 20 });
    renderConventions(data);
  } catch (e) {
    showError(e.message);
  }
});

// Theme
const savedTheme = localStorage.getItem("theme");
if (savedTheme === "dark") document.documentElement.classList.add("dark");

$("#theme-toggle").addEventListener("click", () => {
  document.documentElement.classList.toggle("dark");
  localStorage.setItem(
    "theme",
    document.documentElement.classList.contains("dark") ? "dark" : "light"
  );
});

// Health
fetch("/health")
  .then((r) => r.json())
  .then((d) => {
    const el = $("#health-status");
    if (d.github_configured && d.llm_configured) {
      el.textContent = `${d.llm_provider} · ${d.llm_model.split("/").pop()}`;
      el.classList.add("ok");
    } else {
      el.textContent = "Missing API keys in .env";
      el.classList.add("err");
    }
  })
  .catch(() => {
    const el = $("#health-status");
    el.textContent = "Server offline";
    el.classList.add("err");
  });
