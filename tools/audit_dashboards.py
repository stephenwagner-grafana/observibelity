"""Walk every dashboard, test every panel's first query, classify result.

Output:
  /tmp/dashboard_audit.csv — dashboard,panel_id,panel_title,kind,query,result,notes
  /tmp/dashboard_audit.md  — human-readable summary

Skips text/row panels. For Prometheus panels we use /api/v1/query (instant).
For Loki panels we use the same proxy + a 5-min range. Anything that
returns 0 series is flagged.
"""
import csv
import json
import os
import sys
import urllib.parse
from pathlib import Path

import urllib.request, urllib.error

def _http_get(url, params, headers, timeout=15):
    import urllib.parse, urllib.request, urllib.error
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{qs}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")
    except Exception as e:
        return -1, str(e)


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
    def json(self):
        import json as _j
        return _j.loads(self._body) if self._body else {}


class _Requests:
    def get(self, url, params=None, headers=None, timeout=15):
        s, b = _http_get(url, params or {}, headers or {}, timeout)
        return _Resp(s, b)


requests = _Requests()


DASHDIR = Path("/workspace/observibelity/dashboards")
GRAFANA = "https://stephenwagner.grafana.net"
TOKEN = open("/workspace/.grafana-token.env").read().strip().split("=", 1)[1]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def run_prom(expr: str) -> tuple[int, str]:
    """Return (series_count, error_or_empty)."""
    try:
        r = requests.get(
            f"{GRAFANA}/api/datasources/proxy/uid/grafanacloud-prom/api/v1/query",
            params={"query": expr},
            headers=HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return (-1, f"HTTP {r.status_code}")
        j = r.json()
        if j.get("status") != "success":
            return (-1, j.get("error", "non-success"))
        return (len(j.get("data", {}).get("result", [])), "")
    except Exception as e:
        return (-1, str(e)[:80])


def run_loki(expr: str) -> tuple[int, str]:
    try:
        import time as t
        end = int(t.time())
        start = end - 300
        r = requests.get(
            f"{GRAFANA}/api/datasources/proxy/uid/grafanacloud-logs/loki/api/v1/query_range",
            params={"query": expr, "start": start * 1_000_000_000, "end": end * 1_000_000_000, "limit": 50},
            headers=HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return (-1, f"HTTP {r.status_code}")
        j = r.json()
        if j.get("status") != "success":
            return (-1, j.get("error", "non-success"))
        return (len(j.get("data", {}).get("result", [])), "")
    except Exception as e:
        return (-1, str(e)[:80])


def variable_substitute(expr: str) -> str:
    """Replace dashboard template-variable references with safe defaults.

    We can't always know what `$specialist` should be, so most filters get
    `.*` (regex match-all). Time-range substitutions use 5m.
    """
    subs = {
        "$__rate_interval": "5m",
        "$__range": "5m",
        "$__interval": "1m",
        "$rate_interval": "5m",
        "$interval": "1m",
        "$datasource_prom": "grafanacloud-prom",
        "$datasource_loki": "grafanacloud-logs",
    }
    for k, v in subs.items():
        expr = expr.replace(k, v)
    # Match-all variables — anything else like ${var:regex} or $var that's
    # used inside a label selector. The regex below catches $foo and ${foo}.
    import re
    def _sub(m):
        v = m.group(1) or m.group(2)
        # Common boolean-ish variables get true; everything else regex-match-all
        if v in {"__all", "All"}:
            return ".*"
        return ".*"
    expr = re.sub(r"\$\{([a-zA-Z0-9_:]+)\}|\$([a-zA-Z0-9_]+)", _sub, expr)
    return expr


def walk_panels(dash: dict):
    """Yield (panel_id, title, dtype, expr) for every leaf panel with a query."""
    def _emit(p):
        if p.get("type") in {"text", "row", "dashlist", "news"}:
            return
        ds = (p.get("datasource") or {}).get("type", "")
        for t in p.get("targets", []):
            raw_expr = t.get("expr") or t.get("rawSql") or ""
            if not raw_expr:
                continue
            yield (
                p.get("id"),
                p.get("title", ""),
                ds or t.get("datasource", {}).get("type", ""),
                raw_expr,
            )
            break  # only test first target per panel — most panels have only one
    for p in dash.get("panels", []):
        yield from _emit(p)
        for sub in p.get("panels", []) or []:
            yield from _emit(sub)


def main():
    rows = []
    audit_summary = {}
    for f in sorted(DASHDIR.glob("*.json")):
        try:
            dash = json.loads(f.read_text())
        except Exception as e:
            rows.append({"dashboard": f.stem, "panel_id": "-", "panel_title": "PARSE ERROR", "kind": "-", "query": "", "result": "ERR", "notes": str(e)[:80]})
            continue
        empty = 0
        ok = 0
        err = 0
        for pid, ptitle, dtype, expr in walk_panels(dash):
            sub = variable_substitute(expr)
            if "loki" in dtype:
                n, e = run_loki(sub)
            else:
                n, e = run_prom(sub)
            res = "OK" if n > 0 else ("EMPTY" if n == 0 else "ERR")
            if res == "OK": ok += 1
            elif res == "EMPTY": empty += 1
            else: err += 1
            rows.append({
                "dashboard": f.stem, "panel_id": pid, "panel_title": ptitle[:60],
                "kind": dtype, "query": expr[:200].replace("\n", " "),
                "result": res, "notes": e[:80] if e else (f"{n} series" if n >= 0 else ""),
            })
        audit_summary[f.stem] = {"ok": ok, "empty": empty, "err": err}

    # CSV
    with open("/tmp/dashboard_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["dashboard", "panel_id", "panel_title", "kind", "query", "result", "notes"])
        w.writeheader()
        w.writerows(rows)

    # Markdown summary
    with open("/tmp/dashboard_audit.md", "w") as f:
        f.write("# Dashboard panel audit\n\n")
        f.write("| Dashboard | OK | Empty | Err |\n|---|---|---|---|\n")
        for d, s in sorted(audit_summary.items()):
            f.write(f"| {d} | {s['ok']} | {s['empty']} | {s['err']} |\n")
        f.write("\n\n## Empty/error panels\n\n")
        for r in rows:
            if r["result"] in {"EMPTY", "ERR"}:
                f.write(f"### {r['dashboard']} :: panel {r['panel_id']} — {r['panel_title']}\n")
                f.write(f"- result: **{r['result']}** ({r['notes']})\n")
                f.write(f"- query: `{r['query']}`\n\n")

    # Print summary table for terminal
    print(f"{'dashboard':<35} {'OK':>5} {'EMPTY':>7} {'ERR':>5}")
    for d, s in sorted(audit_summary.items()):
        print(f"{d:<35} {s['ok']:>5} {s['empty']:>7} {s['err']:>5}")
    totals = {k: sum(v[k] for v in audit_summary.values()) for k in ("ok", "empty", "err")}
    print(f"{'TOTAL':<35} {totals['ok']:>5} {totals['empty']:>7} {totals['err']:>5}")
    print()
    print(f"CSV:      /tmp/dashboard_audit.csv")
    print(f"Markdown: /tmp/dashboard_audit.md")


if __name__ == "__main__":
    main()
