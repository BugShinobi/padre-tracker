"""Flask dashboard for padre-tracker."""

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import Flask, render_template_string, request

DB_PATH = os.getenv("DB_PATH", "./data/calls.db")
app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Padre Tracker</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; }
body {
  background: #0d0f12;
  color: #e8ebef;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  font-size: 0.95rem;
  line-height: 1.4;
  -webkit-font-smoothing: antialiased;
}
a { color: #6aa6ff; }

.header { padding: 22px 28px 14px; border-bottom: 1px solid #1f242b; }
.header h1 {
  font-size: 1.05rem; color: #fff; letter-spacing: 0.12em;
  text-transform: uppercase; font-weight: 600;
}
.header .sub { color: #6b7380; font-size: 0.78rem; margin-top: 4px; letter-spacing: 0.05em; }

.stats {
  display: flex; gap: 32px; padding: 22px 28px;
  border-bottom: 1px solid #1f242b; flex-wrap: wrap;
}
.stat-val { font-size: 1.7rem; color: #fff; font-weight: 600; line-height: 1.1; }
.stat-val.sm { font-size: 1.05rem; }
.stat-label {
  font-size: 0.72rem; color: #6b7380; text-transform: uppercase;
  letter-spacing: 0.09em; margin-top: 6px; font-weight: 500;
}

.controls {
  display: flex; gap: 12px; align-items: center; padding: 16px 28px;
  border-bottom: 1px solid #1f242b; flex-wrap: wrap;
  background: #10141a;
}
.controls form { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
input[type=date], input[type=number], select {
  background: #181d25; border: 1px solid #2d3540; color: #e8ebef;
  padding: 7px 12px; font-family: inherit; font-size: 0.88rem; border-radius: 5px;
}
input[type=date]:focus, input[type=number]:focus, select:focus {
  outline: none; border-color: #4a6fa5;
}
input[type=number] { width: 84px; }
label { font-size: 0.82rem; color: #8a93a0; font-weight: 500; }
button {
  background: #2a3544; border: 1px solid #3d4a5c; color: #e8ebef;
  padding: 7px 16px; font-family: inherit; font-size: 0.88rem;
  cursor: pointer; border-radius: 5px; font-weight: 500;
}
button:hover { background: #34415a; border-color: #4a6fa5; }
button.ghost { background: transparent; }

.table-wrap { padding: 0 28px 40px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; margin-top: 18px; font-size: 0.9rem; }
thead { background: #10141a; }
th {
  text-align: left; color: #8a93a0; border-bottom: 1px solid #232a33;
  padding: 12px 14px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.07em; font-size: 0.72rem;
  white-space: nowrap; cursor: pointer; user-select: none;
}
th:hover { color: #e8ebef; }
th.right { text-align: right; }
td {
  padding: 11px 14px; border-bottom: 1px solid #181d25;
  vertical-align: middle; white-space: nowrap;
}
tr:hover td { background: #141922; }

.num { color: #5a6370; font-variant-numeric: tabular-nums; width: 40px; }
.ticker {
  color: #fff; font-weight: 600; font-size: 0.95rem;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
}
.ticker.unknown { color: #4a5260; font-weight: 400; font-style: italic; font-size: 0.82rem; }

.ca a {
  color: #6aa6ff; text-decoration: none; font-size: 0.82rem;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
}
.ca a:hover { text-decoration: underline; }

.lp {
  display: inline-block; padding: 3px 9px; border-radius: 4px;
  font-size: 0.74rem; font-weight: 600; letter-spacing: 0.03em;
  text-transform: lowercase;
}
.lp.pump { background: #2d1f3f; color: #b28cff; }
.lp.bags { background: #3a2a1a; color: #ffb46e; }
.lp.moon { background: #1a2e3a; color: #6ed2ff; }
.lp.bonk { background: #3a2a2a; color: #ff9090; }
.lp.none { color: #4a5260; font-weight: 400; text-transform: none; font-style: italic; font-size: 0.78rem; }

.calls { font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }
.calls.hot  { color: #ffb347; }
.calls.warm { color: #e8ebef; }
.calls.cold { color: #5a6370; }
.vel, .dur {
  color: #8a93a0; font-size: 0.82rem; text-align: right;
  font-variant-numeric: tabular-nums;
}

.group { font-size: 0.84rem; }
.group.tagged { color: #8ed8a5; font-weight: 500; }
.group.none { color: #3d4553; font-style: italic; }

.time {
  color: #6b7380; font-size: 0.82rem;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
}

.empty {
  color: #5a6370; padding: 80px 0; text-align: center;
  font-size: 1rem;
}
.row-hot td { border-left: 3px solid #ffb347; }
.row-hot td:first-child { padding-left: 11px; }
</style>
</head>
<body>

<div class="header">
  <h1>Padre Tracker</h1>
  <div class="sub">Alpha calls aggregated by contract address</div>
</div>

<div class="stats">
  <div>
    <div class="stat-val">{{ stats.tokens }}</div>
    <div class="stat-label">tokens</div>
  </div>
  <div>
    <div class="stat-val">{{ stats.total_calls }}</div>
    <div class="stat-label">total calls</div>
  </div>
  <div>
    <div class="stat-val">{{ stats.with_ticker }}</div>
    <div class="stat-label">with ticker</div>
  </div>
  <div>
    <div class="stat-val">{{ stats.with_group }}</div>
    <div class="stat-label">with group</div>
  </div>
  {% if stats.top_launchpad %}
  <div>
    <div class="stat-val sm">{{ stats.top_launchpad }}</div>
    <div class="stat-label">top launchpad</div>
  </div>
  {% endif %}
  {% if stats.top_group %}
  <div>
    <div class="stat-val sm">{{ stats.top_group }}</div>
    <div class="stat-label">top group</div>
  </div>
  {% endif %}
  <div style="margin-left:auto; text-align:right">
    <div class="stat-val sm" style="color:#8a93a0">{{ date_str }}</div>
    <div class="stat-label">date</div>
  </div>
</div>

<div class="controls">
  <form method="get">
    <label>Date</label>
    <input type="date" name="d" value="{{ date_str }}" max="{{ today }}">
    <label>Min calls</label>
    <input type="number" name="min_calls" value="{{ min_calls }}" min="1" max="999">
    <label>Launchpad</label>
    <select name="lp">
      <option value="">all</option>
      {% for l in all_launchpads %}
      <option value="{{ l }}" {% if l == selected_lp %}selected{% endif %}>{{ l }}</option>
      {% endfor %}
    </select>
    <label>Group</label>
    <select name="group">
      <option value="">all groups</option>
      {% for g in all_groups %}
      <option value="{{ g }}" {% if g == selected_group %}selected{% endif %}>{{ g }}</option>
      {% endfor %}
    </select>
    <button type="submit">Filter</button>
    <button type="button" class="ghost" onclick="window.location='/'">Today</button>
  </form>
</div>

<div class="table-wrap">
{% if calls %}
<table id="tbl">
  <thead>
    <tr>
      <th>#</th>
      <th onclick="sortBy('ticker')">ticker ↕</th>
      <th>contract</th>
      <th onclick="sortBy('lp')">launchpad ↕</th>
      <th class="right" onclick="sortBy('calls')">calls ↕</th>
      <th class="right" onclick="sortBy('vel')">calls/hr ↕</th>
      <th class="right" onclick="sortBy('dur')">active for ↕</th>
      <th>groups</th>
      <th>first</th>
      <th>last</th>
    </tr>
  </thead>
  <tbody>
    {% for c in calls %}
    <tr class="{{ 'row-hot' if c.call_count >= 20 else '' }}"
        data-ticker="{{ c.ticker or '' }}"
        data-calls="{{ c.call_count }}"
        data-vel="{{ c.velocity }}"
        data-dur="{{ c.duration_min }}"
        data-lp="{{ c.launchpad or '' }}">
      <td class="num">{{ loop.index }}</td>
      <td class="{{ 'ticker' if c.ticker else 'ticker unknown' }}">{{ c.ticker or 'unknown' }}</td>
      <td class="ca">
        <a href="https://dexscreener.com/solana/{{ c.contract_address }}" target="_blank">
          {{ c.contract_address[:6] }}…{{ c.contract_address[-6:] }}
        </a>
      </td>
      <td>
        {% if c.launchpad %}
          <span class="lp {{ c.launchpad.split('.')[0] }}">{{ c.launchpad }}</span>
        {% else %}
          <span class="lp none">—</span>
        {% endif %}
      </td>
      <td class="calls {{ 'hot' if c.call_count >= 20 else ('warm' if c.call_count >= 5 else 'cold') }}">
        {{ c.call_count }}
      </td>
      <td class="vel">{{ c.velocity }}</td>
      <td class="dur">{{ c.duration_str }}</td>
      <td class="{{ 'group tagged' if c.groups_mentioned else 'group none' }}">
        {{ c.groups_mentioned or '—' }}
      </td>
      <td class="time">{{ c.first_seen_at[11:16] }}</td>
      <td class="time">{{ c.last_seen_at[11:16] }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<p class="empty">No calls match the current filters.</p>
{% endif %}
</div>

<script>
let sortCol = null, sortDir = 1;
function sortBy(col) {
  const tbody = document.querySelector('#tbl tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  if (sortCol === col) sortDir *= -1; else { sortCol = col; sortDir = -1; }
  rows.sort((a, b) => {
    const av = a.dataset[col] || '', bv = b.dataset[col] || '';
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return (an - bn) * sortDir;
    return av.localeCompare(bv) * sortDir;
  });
  rows.forEach(r => tbody.appendChild(r));
  tbody.querySelectorAll('tr').forEach((r, i) => r.querySelector('td').textContent = i + 1);
}
setTimeout(() => location.reload(), 60000);
</script>
</body>
</html>
"""


def get_data(target_date: date, min_calls: int, group_filter: str, lp_filter: str):
    if not Path(DB_PATH).exists():
        return [], {}, [], []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    date_str = target_date.strftime("%Y-%m-%d")

    all_rows = conn.execute(
        """SELECT contract_address, ticker, chain, launchpad, call_count,
                  first_seen_at, last_seen_at, groups_mentioned
           FROM calls WHERE call_date = ?
           ORDER BY call_count DESC, first_seen_at""",
        (date_str,),
    ).fetchall()
    conn.close()

    all_rows = [dict(r) for r in all_rows]

    all_groups: set[str] = set()
    for r in all_rows:
        if r["groups_mentioned"]:
            for g in r["groups_mentioned"].split(","):
                g = g.strip()
                if g:
                    all_groups.add(g)

    all_launchpads = sorted({r["launchpad"] for r in all_rows if r["launchpad"]})

    lp_counts: dict[str, int] = {}
    for r in all_rows:
        if r["launchpad"]:
            lp_counts[r["launchpad"]] = lp_counts.get(r["launchpad"], 0) + 1

    group_counts: dict[str, int] = {}
    for r in all_rows:
        if r["groups_mentioned"]:
            for g in r["groups_mentioned"].split(","):
                g = g.strip()
                if g:
                    group_counts[g] = group_counts.get(g, 0) + 1

    stats = {
        "tokens": len(all_rows),
        "total_calls": sum(r["call_count"] for r in all_rows),
        "with_ticker": sum(1 for r in all_rows if r["ticker"]),
        "with_group": sum(1 for r in all_rows if r["groups_mentioned"]),
        "top_group": max(group_counts, key=group_counts.get) if group_counts else None,
        "top_launchpad": max(lp_counts, key=lp_counts.get) if lp_counts else None,
    }

    filtered = [r for r in all_rows if r["call_count"] >= min_calls]
    if group_filter:
        filtered = [r for r in filtered if r["groups_mentioned"] and group_filter in r["groups_mentioned"]]
    if lp_filter:
        filtered = [r for r in filtered if r["launchpad"] == lp_filter]

    for r in filtered:
        try:
            t0 = datetime.fromisoformat(r["first_seen_at"])
            t1 = datetime.fromisoformat(r["last_seen_at"])
            mins = max(1, (t1 - t0).total_seconds() / 60)
            hours = mins / 60
            r["duration_min"] = round(mins)
            r["duration_str"] = f"{round(mins)}m" if mins < 90 else f"{mins/60:.1f}h"
            r["velocity"] = f"{r['call_count'] / max(hours, 1/60):.1f}"
        except Exception:
            r["duration_min"] = 0
            r["duration_str"] = "—"
            r["velocity"] = "—"

    return filtered, stats, sorted(all_groups), all_launchpads


@app.route("/")
def index():
    d_str = request.args.get("d")
    min_calls = max(1, int(request.args.get("min_calls", 1) or 1))
    group_filter = request.args.get("group", "")
    lp_filter = request.args.get("lp", "")

    try:
        target = date.fromisoformat(d_str) if d_str else date.today()
    except ValueError:
        target = date.today()

    calls, stats, all_groups, all_launchpads = get_data(target, min_calls, group_filter, lp_filter)
    today = date.today()

    return render_template_string(
        HTML,
        calls=calls,
        stats=stats,
        all_groups=all_groups,
        all_launchpads=all_launchpads,
        selected_group=group_filter,
        selected_lp=lp_filter,
        min_calls=min_calls,
        date_str=target.isoformat(),
        today=today.isoformat(),
    )


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
