(() => {
  const state = {
    token: localStorage.getItem("csiq_token") || null,
    user: JSON.parse(localStorage.getItem("csiq_user") || "null"),
    leagues: [],
    leagueId: localStorage.getItem("csiq_league") || null,
    slate: null,
  };

  const el = {
    auth: document.getElementById("view-auth"),
    home: document.getElementById("view-home"),
    logout: document.getElementById("btn-logout"),
    loginForm: document.getElementById("form-login"),
    displayName: document.getElementById("display-name"),
    leagueName: document.getElementById("league-name"),
    leagueNotice: document.getElementById("league-notice"),
    leagueSelect: document.getElementById("league-select"),
    createLeague: document.getElementById("form-create-league"),
    joinLeague: document.getElementById("form-join-league"),
    questions: document.getElementById("slate-questions"),
    slateMeta: document.getElementById("slate-meta"),
    leaderboard: document.getElementById("leaderboard"),
    audit: document.getElementById("audit-box"),
    seedDemo: document.getElementById("btn-seed-demo"),
    settleDemo: document.getElementById("btn-settle-demo"),
  };

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const res = await fetch(path, { ...options, headers });
    const body = await res.json();
    if (!body.ok) {
      const err = new Error(body.error?.message || "Request failed");
      err.code = body.error?.code;
      throw err;
    }
    return body.data;
  }

  function showAuth() {
    el.auth.hidden = false;
    el.home.hidden = true;
    el.logout.hidden = true;
  }

  function showHome() {
    el.auth.hidden = true;
    el.home.hidden = false;
    el.logout.hidden = false;
  }

  function persist() {
    if (state.token) localStorage.setItem("csiq_token", state.token);
    else localStorage.removeItem("csiq_token");
    if (state.user) localStorage.setItem("csiq_user", JSON.stringify(state.user));
    else localStorage.removeItem("csiq_user");
    if (state.leagueId) localStorage.setItem("csiq_league", state.leagueId);
    else localStorage.removeItem("csiq_league");
  }

  async function refreshLeagues() {
    state.leagues = await api("/api/me/leagues");
    el.leagueSelect.innerHTML = "";
    if (!state.leagues.length) {
      el.leagueName.textContent = "Create or join a league";
      el.questions.innerHTML = "<p class='fineprint'>No league yet.</p>";
      el.leaderboard.innerHTML = "";
      return;
    }
    if (!state.leagueId || !state.leagues.some((l) => l.id === state.leagueId)) {
      state.leagueId = state.leagues[0].id;
      persist();
    }
    for (const league of state.leagues) {
      const opt = document.createElement("option");
      opt.value = league.id;
      opt.textContent = league.name;
      if (league.id === state.leagueId) opt.selected = true;
      el.leagueSelect.appendChild(opt);
    }
    await refreshLeague();
  }

  async function refreshLeague() {
    const league = await api(`/api/leagues/${state.leagueId}`);
    el.leagueName.textContent = league.name;
    el.leagueNotice.textContent = `${league.no_prize_notice} · Invite: ${league.invite_code}`;
    state.slate = await api(`/api/leagues/${state.leagueId}/slates/current`);
    renderSlate();
    const board = await api(`/api/leagues/${state.leagueId}/leaderboard?window=slate`);
    renderBoard(board);
  }

  function renderSlate() {
    const slate = state.slate;
    el.questions.innerHTML = "";
    if (!slate) {
      el.slateMeta.textContent = "No slate yet — commissioners can load a demo slate.";
      return;
    }
    el.slateMeta.textContent = `Slate ${slate.date_utc} · scoring ${slate.scoring_version} · status ${slate.status}`;
    for (const q of slate.questions) {
      const node = document.createElement("article");
      node.className = "question";
      const locked = q.is_locked || q.status !== "open";
      const mine = q.my_prediction?.predicted_value;
      node.innerHTML = `
        <p class="question-prompt">${escapeHtml(q.prompt_text)}
          ${locked ? '<span class="locked-badge">Locked</span>' : ""}
        </p>
        <p class="question-meta">${escapeHtml(q.player_name)} · ${q.stat}
          · tipoff ${q.scheduled_tipoff_utc}
          · baseline ${q.frozen_baseline}
          ${q.result ? ` · actual ${q.result.actual_value}` : ""}
        </p>
        <form class="predict-row" data-qid="${q.id}">
          <div>
            <label for="pred-${q.id}">Your prediction</label>
            <input id="pred-${q.id}" name="predicted_value" type="number" step="0.5" min="0" max="100"
              value="${mine ?? ""}" ${locked ? "disabled" : "required"} />
          </div>
          <button type="submit" ${locked ? "disabled" : ""}>${locked ? "Locked" : "Submit"}</button>
        </form>
        <div class="reveal" data-reveal="${q.id}"></div>
      `;
      el.questions.appendChild(node);
      const form = node.querySelector("form");
      form.addEventListener("submit", onSubmitPrediction);
      if (locked && q.forecasts) {
        const reveal = node.querySelector(`[data-reveal="${q.id}"]`);
        reveal.innerHTML = q.forecasts
          .map(
            (f) =>
              `<div>${escapeHtml(f.display_name)}${f.is_house_ai ? " (AI)" : ""}: <strong>${f.predicted_value}</strong></div>`
          )
          .join("");
        reveal.addEventListener("click", () => showAudit(q.id));
        reveal.style.cursor = "pointer";
        reveal.title = "Tap to view audit history";
      }
    }
  }

  function renderBoard(board) {
    el.leaderboard.innerHTML = "";
    if (!board.entries?.length) {
      el.leaderboard.innerHTML = "<li><span class='fineprint'>No graded results yet.</span></li>";
      return;
    }
    for (const e of board.entries) {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="rank">${e.rank}</span>
        <span>
          ${escapeHtml(e.display_name)}${e.is_house_ai ? " · AI" : ""}
          ${e.provisional ? '<span class="provisional"> provisional</span>' : ""}
          <div class="fineprint">${e.completed_count} graded · skill Δ ${e.experimental_mean_skill_delta}</div>
        </span>
        <span class="score">${e.mean_accuracy.toFixed(1)}</span>
      `;
      el.leaderboard.appendChild(li);
    }
  }

  async function showAudit(questionId) {
    const data = await api(`/api/questions/${questionId}/audit`);
    el.audit.textContent = JSON.stringify(data, null, 2);
  }

  async function onSubmitPrediction(ev) {
    ev.preventDefault();
    const form = ev.currentTarget;
    const qid = form.dataset.qid;
    const value = Number(new FormData(form).get("predicted_value"));
    try {
      await api(`/api/questions/${qid}/forecasts`, {
        method: "POST",
        body: JSON.stringify({
          predicted_value: value,
          client_request_id: crypto.randomUUID(),
        }),
      });
      await refreshLeague();
    } catch (err) {
      alert(err.message);
    }
  }

  el.loginForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      const data = await api("/api/auth/demo-login", {
        method: "POST",
        body: JSON.stringify({ display_name: el.displayName.value.trim() }),
      });
      state.token = data.token;
      state.user = data.user;
      persist();
      showHome();
      await refreshLeagues();
    } catch (err) {
      alert(err.message);
    }
  });

  el.logout.addEventListener("click", () => {
    state.token = null;
    state.user = null;
    state.leagueId = null;
    persist();
    showAuth();
  });

  el.createLeague.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const name = document.getElementById("new-league-name").value.trim();
    if (!name) return;
    try {
      const league = await api("/api/leagues", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      state.leagueId = league.id;
      persist();
      document.getElementById("new-league-name").value = "";
      await refreshLeagues();
    } catch (err) {
      alert(err.message);
    }
  });

  el.joinLeague.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const code = document.getElementById("invite-code").value.trim();
    if (!code) return;
    try {
      const league = await api("/api/leagues/join", {
        method: "POST",
        body: JSON.stringify({ invite_code: code }),
      });
      state.leagueId = league.id;
      persist();
      document.getElementById("invite-code").value = "";
      await refreshLeagues();
    } catch (err) {
      alert(err.message);
    }
  });

  el.leagueSelect.addEventListener("change", async () => {
    state.leagueId = el.leagueSelect.value;
    persist();
    await refreshLeague();
  });

  el.seedDemo.addEventListener("click", async () => {
    if (!state.leagueId) {
      alert("Create or join a league first.");
      return;
    }
    // Demo slate uses a future tipoff so users can submit; results come from attributed fixture values.
    const tip = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString().replace(/\.\d{3}Z$/, "Z");
    const today = new Date().toISOString().slice(0, 10);
    const questions = [
      {
        game: {
          id: "game_demo_bos_ind",
          season: "2023-24",
          home_team_id: "BOS",
          away_team_id: "IND",
          scheduled_tipoff_utc: tip,
          status: "scheduled",
        },
        player: {
          id: "ply_tatum",
          full_name: "Jayson Tatum",
          team_id: "BOS",
          position: "F",
        },
        stat: "PTS",
        frozen_baseline: 27,
        prompt_text: "How many points will Jayson Tatum score?",
        scheduled_tipoff_utc: tip,
      },
      {
        game: {
          id: "game_demo_bos_ind",
          season: "2023-24",
          home_team_id: "BOS",
          away_team_id: "IND",
          scheduled_tipoff_utc: tip,
          status: "scheduled",
        },
        player: {
          id: "ply_haliburton",
          full_name: "Tyrese Haliburton",
          team_id: "IND",
          position: "G",
        },
        stat: "AST",
        frozen_baseline: 10,
        prompt_text: "How many assists will Tyrese Haliburton finish with?",
        scheduled_tipoff_utc: tip,
      },
    ];
    try {
      await api(`/api/leagues/${state.leagueId}/slates`, {
        method: "POST",
        body: JSON.stringify({ date_utc: today, questions }),
      });
      await refreshLeague();
    } catch (err) {
      alert(err.message);
    }
  });

  // Commissioner-only demo settlement using the attributed offline fixture values.
  // Tipoff is rewritten server-side via result ingest; UI documents source URL.
  el.settleDemo.addEventListener("click", async () => {
    if (!state.slate?.questions?.length) {
      alert("Load a demo slate and submit predictions first.");
      return;
    }
    const fixtureMeta = {
      source_url: "https://www.nba.com/game/ind-vs-bos-0022300553/box-score",
      fetched_at_utc: "2024-01-16T12:00:00Z",
      fixture_id: "fx_2024_01_15_bos_ind",
      actuals: { PTS: 26, AST: 11 },
    };
    try {
      for (const q of state.slate.questions) {
        const actual = fixtureMeta.actuals[q.stat];
        if (actual == null) continue;
        await api(`/api/questions/${q.id}/results`, {
          method: "POST",
          body: JSON.stringify({
            actual_value: actual,
            source_url: fixtureMeta.source_url,
            fetched_at_utc: fixtureMeta.fetched_at_utc,
            fixture_id: fixtureMeta.fixture_id,
          }),
        });
      }
      await api(`/api/slates/${state.slate.id}/grade`, { method: "POST", body: "{}" });
      await refreshLeague();
      const first = state.slate.questions[0];
      if (first) await showAudit(first.id);
    } catch (err) {
      alert(err.message);
    }
  });

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  async function boot() {
    if (!state.token) {
      showAuth();
      return;
    }
    showHome();
    try {
      await refreshLeagues();
    } catch {
      state.token = null;
      state.user = null;
      persist();
      showAuth();
    }
  }

  boot();
})();
