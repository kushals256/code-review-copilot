const $ = (sel) => document.querySelector(sel);

function showLoading(show) {
  $("#loading").classList.toggle("hidden", !show);
  $("#output").classList.toggle("hidden", show);
  $("#results").classList.remove("hidden");
}

function scoreClass(score) {
  if (score >= 75) return "good";
  if (score >= 50) return "medium";
  return "bad";
}

function renderReview(data) {
  const review = data.review;
  const rs = review.risk_summary;
  const github = data.github || {};

  let html = `
    <div class="score-display">
      <div class="score-circle ${scoreClass(rs.quality_score)}">${rs.quality_score}</div>
      <div>
        <div class="merge-rec ${rs.merge_recommendation}">${rs.merge_recommendation.replace(/_/g, " ").toUpperCase()}</div>
        <p style="color:var(--muted);font-size:0.9rem;margin-top:0.3rem">${rs.merge_rationale}</p>
      </div>
    </div>
  `;

  if (github.comments_posted !== undefined) {
    html += `<p style="font-size:0.85rem;color:var(--muted)">Posted ${github.comments_posted}/${github.comments_total || review.comments.length} comments to GitHub</p>`;
  }

  if (rs.highest_risk_changes.length) {
    html += `<div class="section-title">Highest-Risk Changes</div><ul class="risk-list">`;
    for (const r of rs.highest_risk_changes) {
      html += `<li class="risk-item">
        <span class="severity-badge ${r.severity}">${r.severity}</span>
        <strong>${r.file_path}</strong> (risk ${r.risk_score}/10)
        <div class="comment-detail">${r.description}</div>
      </li>`;
    }
    html += `</ul>`;
  }

  if (review.comments.length) {
    html += `<div class="section-title">Inline Comments (${review.comments.length})</div><ul class="comment-list">`;
    for (const c of review.comments) {
      html += `<li class="comment-item">
        <div class="comment-meta">${c.file_path}:${c.line}</div>
        <span class="severity-badge ${c.severity}">${c.severity}</span>
        <div class="comment-issue">${c.issue}</div>
        <div class="comment-detail"><strong>Why:</strong> ${c.why_it_matters}</div>
        <div class="comment-detail"><strong>Fix:</strong> <code>${c.suggested_fix}</code></div>
        <div class="comment-detail"><strong>Learn:</strong> ${c.explanation}</div>
      </li>`;
    }
    html += `</ul>`;
  }

  if (review.conventions_applied.length) {
    html += `<div class="section-title">Conventions Applied</div><ul class="convention-list">`;
    for (const rule of review.conventions_applied) {
      html += `<li class="convention-item">${rule}</li>`;
    }
    html += `</ul>`;
  }

  $("#output").innerHTML = html;
}

function renderConventions(data) {
  let html = `<p style="color:var(--muted);margin-bottom:1rem">Analyzed ${data.prs_analyzed} merged PRs from <strong>${data.repo}</strong></p>`;
  html += `<ul class="convention-list">`;
  for (const r of data.rules) {
    html += `<li class="convention-item">
      <strong>${r.rule}</strong> <span style="color:var(--muted);font-size:0.8rem">(${(r.confidence * 100).toFixed(0)}% confidence)</span>
      <div class="comment-detail">${r.description}</div>
      ${r.examples.length ? `<div class="comment-detail">Examples: ${r.examples.join("; ")}</div>` : ""}
    </li>`;
  }
  html += `</ul>`;
  $("#output").innerHTML = html;
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

$("#btn-review").addEventListener("click", async () => {
  const prUrl = $("#pr-url").value.trim();
  if (!prUrl) return alert("Enter a PR URL");

  const conventions = $("#conventions").value
    .split("\n").map(s => s.trim()).filter(Boolean);

  try {
    const data = await apiCall("/api/review", { pr_url: prUrl, conventions });
    renderReview(data);
  } catch (e) {
    $("#output").innerHTML = `<div class="error-box">${e.message}</div>`;
  }
});

$("#btn-dry-run").addEventListener("click", async () => {
  const prUrl = $("#pr-url").value.trim();
  if (!prUrl) return alert("Enter a PR URL");

  const conventions = $("#conventions").value
    .split("\n").map(s => s.trim()).filter(Boolean);

  try {
    const data = await apiCall("/api/review/dry-run", { pr_url: prUrl, conventions });
    renderReview(data);
  } catch (e) {
    $("#output").innerHTML = `<div class="error-box">${e.message}</div>`;
  }
});

$("#btn-extract").addEventListener("click", async () => {
  const repoUrl = $("#repo-url").value.trim();
  if (!repoUrl) return alert("Enter a repo URL");

  try {
    const data = await apiCall("/api/conventions/extract", { repo_url: repoUrl, max_prs: 20 });
    renderConventions(data);
  } catch (e) {
    $("#output").innerHTML = `<div class="error-box">${e.message}</div>`;
  }
});
