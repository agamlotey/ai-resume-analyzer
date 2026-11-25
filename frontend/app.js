const API = window.API_BASE || "";
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const state = { token: null, user: null, jobs: [], authMode: "login", jobMode: "posting" };

function load(key) { try { return localStorage.getItem(key); } catch { return null; } }
function save(key, value) { try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch {} }

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.add("hidden"), 2800);
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (state.token) headers.Authorization = "Bearer " + state.token;
  if (options.json) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.json);
  }
  const res = await fetch(API + path, { ...options, headers });
  const type = res.headers.get("content-type") || "";
  if (!type.includes("application/json")) {
    if (!res.ok) throw new Error("Request failed (" + res.status + ")");
    return res;
  }
  const data = await res.json();
  if (res.status === 401 && state.token) logout();
  if (!res.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function showView(name) {
  $$(".view").forEach((v) => v.classList.add("hidden"));
  $("#view-" + name).classList.remove("hidden");
  $$("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "history") loadHistory();
  if (name === "jobs") renderJobs();
  if (name === "admin") loadStats();
}

function setUser(token, user) {
  state.token = token;
  state.user = user;
  save("rm_token", token);
  save("rm_user", user ? JSON.stringify(user) : null);
  const loggedIn = !!user;
  $("#nav").classList.toggle("hidden", !loggedIn);
  $("#userbox").classList.toggle("hidden", !loggedIn);
  if (loggedIn) {
    $("#username").textContent = user.name || user.email;
    $("#rolebadge").textContent = user.role;
    $$(".admin-only").forEach((el) => el.classList.toggle("hidden", user.role !== "admin"));
    loadJobs();
    showView("analyze");
  } else {
    showView("auth");
  }
}

function logout() { setUser(null, null); }

function setAuthMode(mode) {
  state.authMode = mode;
  $("#tab-login").classList.toggle("active", mode === "login");
  $("#tab-register").classList.toggle("active", mode === "register");
  $("#name-field").classList.toggle("hidden", mode === "login");
  $("#pw-hint").classList.toggle("hidden", mode === "login");
  $("#auth-submit").textContent = mode === "login" ? "Log in" : "Create account";
  $("#auth-error").textContent = "";
}

async function submitAuth(e) {
  e.preventDefault();
  const form = new FormData(e.target);
  const body = Object.fromEntries(form.entries());
  const btn = $("#auth-submit");
  btn.disabled = true;
  $("#auth-error").textContent = "";
  try {
    const path = state.authMode === "login" ? "/api/auth/login" : "/api/auth/register";
    const data = await api(path, { method: "POST", json: body });
    e.target.reset();
    setUser(data.token, data.user);
    toast("Welcome, " + (data.user.name || data.user.email));
  } catch (err) {
    $("#auth-error").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
}

async function loadJobs() {
  try {
    const data = await api("/api/jobs");
    state.jobs = data.jobs;
  } catch (err) {
    state.jobs = [];
  }
  const select = $("#job-select");
  select.innerHTML = state.jobs.map((j) => `<option value="${esc(j.id)}">${esc(j.title)}${j.company ? " · " + esc(j.company) : ""}</option>`).join("")
    || `<option value="">No job postings yet</option>`;
  updateJobPreview();
  renderJobs();
}

function updateJobPreview() {
  const job = state.jobs.find((j) => j.id === $("#job-select").value);
  $("#job-preview").textContent = job ? "Skills in this posting: " + (job.skills || []).join(", ") : "";
}

function setJobMode(mode) {
  state.jobMode = mode;
  $$(".seg button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  $("#mode-posting").classList.toggle("hidden", mode !== "posting");
  $("#mode-custom").classList.toggle("hidden", mode !== "custom");
}

function setFile(file) {
  const drop = $("#drop");
  if (!file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  $("#resume-input").files = dt.files;
  $("#drop-text").textContent = file.name + " (" + Math.round(file.size / 1024) + " KB)";
  drop.classList.add("has-file");
}

async function submitAnalyze(e) {
  e.preventDefault();
  const form = new FormData(e.target);
  if (state.jobMode === "posting") {
    form.delete("job_title");
    form.delete("job_description");
  } else {
    form.delete("job_id");
  }
  const btn = $("#analyze-btn");
  btn.disabled = true;
  $("#analyze-error").textContent = "";
  $("#result").className = "card";
  $("#result").innerHTML = `<div class="empty"><div class="spinner"></div><p>Uploading to cloud storage and analyzing...</p></div>`;
  try {
    const data = await api("/api/analyze", { method: "POST", body: form });
    renderResult($("#result"), data.match);
    toast("Saved to your history");
  } catch (err) {
    $("#analyze-error").textContent = err.message;
    $("#result").className = "card result-empty";
    $("#result").innerHTML = `<div class="empty"><div class="empty-ring"></div><p>${esc(err.message)}</p></div>`;
  } finally {
    btn.disabled = false;
  }
}

function verdictClass(score) {
  return score >= 60 ? "v-good" : score >= 40 ? "v-warn" : "v-bad";
}

function ring(score) {
  const r = 58, c = 2 * Math.PI * r, off = c * (1 - score / 100);
  const color = score >= 60 ? "var(--good)" : score >= 40 ? "var(--warn)" : "var(--bad)";
  return `<div class="ring"><svg width="140" height="140" viewBox="0 0 140 140">
    <circle cx="70" cy="70" r="${r}" fill="none" stroke="var(--surface-2)" stroke-width="12"/>
    <circle cx="70" cy="70" r="${r}" fill="none" stroke="${color}" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${off}"/></svg>
    <div class="value"><span class="num">${Math.round(score)}</span><span class="of">out of 100</span></div></div>`;
}

function chips(list, cls) {
  if (!list || !list.length) return `<span class="hint">None</span>`;
  return `<div class="chips">${list.map((s) => `<span class="chip ${cls}">${esc(s)}</span>`).join("")}</div>`;
}

function renderResult(el, match) {
  const r = match.result;
  const labels = { skills: "Skill coverage", text_similarity: "Content similarity", experience: "Experience fit", education: "Education fit" };
  const wkeys = { skills: "skills", text_similarity: "text", experience: "experience", education: "education" };
  const bars = ["skills", "text_similarity", "experience", "education"].map((k) => [k, r.breakdown[k]]).map(([k, v]) => `
    <div class="bar-row"><span>${labels[k]} <span class="hint">(${Math.round(r.weights[wkeys[k]] * 100)}%)</span></span>
    <div class="bar"><span style="width:${v}%"></span></div><b>${Math.round(v)}%</b></div>`).join("");
  const res = r.resume, c = res.contact || {};
  el.className = "card";
  el.innerHTML = `
    <div class="score-head">
      ${ring(r.score)}
      <div>
        <span class="verdict ${verdictClass(r.score)}">${esc(r.verdict)}</span>
        <h2 style="margin:8px 0 4px">${esc(match.job_title)}</h2>
        <div class="meta">${esc(match.resume_name)} · ${new Date(match.created_at).toLocaleString()}</div>
        <button class="ghost small" style="margin-top:8px" data-resume="${esc(match.id)}">Open stored resume</button>
      </div>
    </div>
    <div class="bars">${bars}</div>
    <h3>Matched skills (${r.matched_skills.length})</h3>${chips(r.matched_skills, "ok")}
    <h3>Missing skills (${r.missing_skills.length})</h3>${chips(r.missing_skills, "miss")}
    ${r.weak_skills.length ? `<h3>Weak skills (mentioned once, job stresses them)</h3>${chips(r.weak_skills, "weak")}` : ""}
    <h3>Suggestions</h3>
    <ol class="suggestions">${r.suggestions.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
    <h3>What we extracted from your resume</h3>
    <div class="facts">
      <div class="fact"><small>Name</small><b>${esc(c.name || "Not found")}</b></div>
      <div class="fact"><small>Email</small><b>${esc(c.email || "Not found")}</b></div>
      <div class="fact"><small>Experience</small><b>${res.years_experience ? esc(res.years_experience) + " yrs" : "Not stated"}</b></div>
      <div class="fact"><small>Highest degree</small><b>${esc(res.degree || "Not found")}</b></div>
      <div class="fact"><small>Skills found</small><b>${res.skills.length}</b></div>
      <div class="fact"><small>Sections</small><b>${esc(res.sections_found.join(", ") || "None")}</b></div>
    </div>
    ${r.extra_skills.length ? `<h3>Other skills you have</h3>${chips(r.extra_skills, "")}` : ""}`;
  el.querySelector("[data-resume]").addEventListener("click", () => openResume(match.id));
}

async function openResume(id) {
  try {
    const res = await api(`/api/matches/${id}/resume`);
    if (res.url) {
      window.open(res.url, "_blank");
    } else {
      const blob = await res.blob();
      window.open(URL.createObjectURL(blob), "_blank");
    }
  } catch (err) {
    toast(err.message);
  }
}

async function loadHistory() {
  const all = $("#history-all").checked ? "?all=1" : "";
  $("#history-list").innerHTML = `<div class="spinner"></div>`;
  $("#history-detail").innerHTML = "";
  try {
    const data = await api("/api/matches" + all);
    if (!data.matches.length) {
      $("#history-list").innerHTML = `<p class="hint">No analyses yet. Run one from the Analyze tab.</p>`;
      return;
    }
    $("#history-list").innerHTML = `<div class="table-wrap"><table class="table"><thead><tr>
      <th>Date</th><th>Job</th><th>Resume</th>${all ? "<th>User</th>" : ""}<th>Score</th></tr></thead><tbody>
      ${data.matches.map((m) => `<tr class="click" data-id="${esc(m.id)}">
        <td>${new Date(m.created_at).toLocaleDateString()}</td><td>${esc(m.job_title)}</td><td>${esc(m.resume_name)}</td>
        ${all ? `<td>${esc(m.user_email)}</td>` : ""}
        <td><span class="verdict ${verdictClass(m.score)}">${Math.round(m.score)}</span></td></tr>`).join("")}
      </tbody></table></div>`;
    $$("#history-list tr.click").forEach((tr) => tr.addEventListener("click", () => showMatch(tr.dataset.id)));
  } catch (err) {
    $("#history-list").innerHTML = `<p class="error">${esc(err.message)}</p>`;
  }
}

async function showMatch(id) {
  const box = $("#history-detail");
  box.innerHTML = `<div class="card"><div class="spinner"></div></div>`;
  try {
    const data = await api("/api/matches/" + id);
    box.innerHTML = `<div class="card"></div>`;
    renderResult(box.firstElementChild, data.match);
    box.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    box.innerHTML = `<p class="error">${esc(err.message)}</p>`;
  }
}

function renderJobs() {
  const isAdmin = state.user && state.user.role === "admin";
  $("#jobs-list").innerHTML = state.jobs.map((j) => `
    <div class="job">
      <h3>${esc(j.title)}</h3>
      <p>${esc([j.company, j.location].filter(Boolean).join(" · "))}</p>
      ${chips((j.skills || []).slice(0, 10), "")}
      <div class="actions">
        <button class="ghost small" data-use="${esc(j.id)}">Match my resume</button>
        ${isAdmin ? `<button class="ghost small danger" data-del="${esc(j.id)}">Delete</button>` : ""}
      </div>
    </div>`).join("") || `<p class="hint">No job postings yet.</p>`;
  $$("[data-use]").forEach((b) => b.addEventListener("click", () => {
    setJobMode("posting");
    $("#job-select").value = b.dataset.use;
    updateJobPreview();
    showView("analyze");
  }));
  $$("[data-del]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("Delete this job posting?")) return;
    await api("/api/jobs/" + b.dataset.del, { method: "DELETE" });
    toast("Job deleted");
    loadJobs();
  }));
}

async function loadStats() {
  try {
    const s = await api("/api/stats");
    $("#stats").innerHTML = [
      ["Analyses run", s.total_matches], ["Active users", s.total_users],
      ["Job postings", s.total_jobs], ["Average score", s.average_score],
    ].map(([k, v]) => `<div class="stat"><small>${k}</small><b>${esc(v)}</b></div>`).join("");
    const max = Math.max(1, ...s.top_missing_skills.map((x) => x[1]));
    $("#missing-chart").innerHTML = s.top_missing_skills.length ? `<div class="bars">${s.top_missing_skills.map(([k, v]) => `
      <div class="bar-row"><span>${esc(k)}</span><div class="bar"><span style="width:${(v / max) * 100}%"></span></div><b>${v}</b></div>`).join("")}</div>`
      : `<p class="hint">No data yet.</p>`;
  } catch (err) {
    $("#stats").innerHTML = `<p class="error">${esc(err.message)}</p>`;
  }
}

async function submitJob(e) {
  e.preventDefault();
  $("#job-error").textContent = "";
  try {
    const body = Object.fromEntries(new FormData(e.target).entries());
    await api("/api/jobs", { method: "POST", json: body });
    e.target.reset();
    toast("Job published");
    await loadJobs();
    loadStats();
  } catch (err) {
    $("#job-error").textContent = err.message;
  }
}

async function loadFooter() {
  try {
    const h = await api("/api/health");
    $("#footer").textContent = `Served by ${h.instance_id} (${h.availability_zone}) · storage: ${h.storage} · database: ${h.database} · auth: ${h.auth}`;
  } catch {
    $("#footer").textContent = "Backend unreachable";
  }
}

function init() {
  $("#tab-login").addEventListener("click", () => setAuthMode("login"));
  $("#tab-register").addEventListener("click", () => setAuthMode("register"));
  $("#auth-form").addEventListener("submit", submitAuth);
  $("#logout").addEventListener("click", logout);
  $$("#nav button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  $$(".seg button").forEach((b) => b.addEventListener("click", () => setJobMode(b.dataset.mode)));
  $("#job-select").addEventListener("change", updateJobPreview);
  $("#analyze-form").addEventListener("submit", submitAnalyze);
  $("#job-form").addEventListener("submit", submitJob);
  $("#history-all").addEventListener("change", loadHistory);
  $("#resume-input").addEventListener("change", (e) => setFile(e.target.files[0]));
  const drop = $("#drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); setFile(e.dataTransfer.files[0]); });

  const token = load("rm_token");
  const user = load("rm_user");
  if (token && user) {
    state.token = token;
    api("/api/auth/me").then((d) => setUser(token, d.user)).catch(() => setUser(null, null));
  } else {
    setUser(null, null);
  }
  loadFooter();
}

init();
