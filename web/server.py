import json
import re
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from monitor.state import CheckState
from config import REPORTS_DIR, WEB_HOST, WEB_PORT
from .emailer import send_report_email

LANG = {
    "ru": {
        "refresh": "Обновить",
        "file_h": "Файл", "status_h": "Статус", "problems_h": "Проблем",
        "checked_h": "Проверен", "report_h": "Отчёт", "open_l": "Открыть",
        "stat_today": "Проверено сегодня",
        "stat_errors": "С ошибками",
        "stat_total": "Всего проверено",
        "other_lang": "EN",
        "no": "—",
    },
    "en": {
        "refresh": "Refresh",
        "file_h": "File", "status_h": "Status", "problems_h": "Problems",
        "checked_h": "Checked", "report_h": "Report", "open_l": "Open",
        "stat_today": "Checked today",
        "stat_errors": "With errors",
        "stat_total": "Total checked",
        "other_lang": "RU",
        "no": "—",
    },
}

DASHBOARD_TMPL = """<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="UTF-8"><title>DXF Checker</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',sans-serif;background:#0f0f1a;color:#e0e0e0;padding:30px}}
h1{{color:#b0b0d0;margin-bottom:20px;display:inline-block}}
.lang-switch{{float:right;background:#2a2a4a;border:1px solid #3a3a5a;color:#e0e0e0;padding:6px 12px;border-radius:4px;cursor:pointer;font-size:12px}}
.lang-switch:hover{{background:#3a3a5a}}
.stats{{display:flex;gap:20px;margin-bottom:30px}}
.stat-card{{background:#1a1a35;border:1px solid #2a2a4a;border-radius:8px;padding:20px;min-width:150px}}
.stat-card .num{{font-size:28px;font-weight:700;color:#e0e0ff}}
.stat-card .label{{font-size:12px;color:#888;margin-top:4px}}
table{{width:100%;border-collapse:collapse;background:#16162a;border-radius:8px;overflow:hidden}}
th{{background:#1a1a35;padding:10px 14px;text-align:left;font-size:12px;color:#888;border-bottom:2px solid #2a2a4a}}
td{{padding:10px 14px;border-bottom:1px solid #2a2a4a;font-size:13px}}
tr{{cursor:pointer}}tr:hover{{background:#1e1e3a}}
.status-ok{{color:#4ade80;font-weight:600}}
.status-error{{color:#f87171;font-weight:600}}
.refresh{{background:#2a2a4a;border:1px solid #3a3a5a;color:#e0e0e0;padding:8px 16px;border-radius:4px;cursor:pointer;margin-bottom:20px;font-size:13px}}
.refresh:hover{{background:#3a3a5a}}
</style></head>
<body>
<h1>DXF Checker</h1>
<button class="lang-switch" onclick="toggleLang()">{other_lang}</button>
<div class="stats" id="stats"></div>
<button class="refresh" onclick="loadData()">{refresh}</button>
<table><thead><tr>
<th>{file_h}</th><th>{status_h}</th><th>{problems_h}</th><th>{checked_h}</th><th>{report_h}</th>
</tr></thead><tbody id="files-body"></tbody></table>
<script>
const LANG='{lang}';
const TXT={{no:'{no}',stat_today:'{stat_today}',stat_errors:'{stat_errors}',stat_total:'{stat_total}'}};
const otherLang=LANG==='ru'?'en':'ru';
async function loadData(){{
  const[s,r]=await Promise.all([
    fetch('/api/stats?lang='+LANG).then(r=>r.json()),
    fetch('/api/recent?lang='+LANG).then(r=>r.json())
  ]);
  document.getElementById('stats').innerHTML=
    '<div class="stat-card"><div class="num">'+s.today_checked+'</div><div class="label">'+TXT.stat_today+'</div></div>'
    +'<div class="stat-card"><div class="num">'+s.with_errors+'</div><div class="label">'+TXT.stat_errors+'</div></div>'
    +'<div class="stat-card"><div class="num">'+s.total+'</div><div class="label">'+TXT.stat_total+'</div></div>';
  document.getElementById('files-body').innerHTML=r.map(f=>{{
    const c=f.has_errors?'status-error':'status-ok';
    const l=f.has_errors?'\\u26A0 '+f.total_problems:'\\u2713 OK';
    const rn=f.report_path&&f.report_exists?f.report_path.split(/[\\\\/]/).pop():'';
    const openLink=rn?'<a href="/report/'+rn+'" target="_blank" onclick="event.stopPropagation()">{open_l}</a>':TXT.no;
    return '<tr'+(rn?' onclick="window.open(\\'/report/'+rn+'\\',\\'_blank\\')"':'')+'>'
      +'<td>'+f.filename+'</td><td class="'+c+'">'+f.status+'</td><td>'+l+'</td>'
      +'<td>'+(f.checked_at||TXT.no)+'</td><td>'+openLink+'</td></tr>';
  }}).join('');
}}
loadData();
setInterval(loadData,10000);
function toggleLang(){{const u=new URL(window.location);u.searchParams.set('lang',otherLang);window.location=u}}
</script></body></html>"""


def _build_dashboard(lang):
    d = LANG.get(lang, LANG["ru"])
    return DASHBOARD_TMPL.format(lang=lang, **d)


class CheckerAPIHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        self.state = kwargs.pop("state", None)
        super().__init__(*args, **kwargs)

    def _lang(self):
        return parse_qs(urlparse(self.path).query).get("lang", ["ru"])[0]

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._send_html(_build_dashboard(self._lang()))
        elif path == "/api/stats":
            self._send_json(self.state.get_stats())
        elif path == "/api/recent":
            self._send_json(self.state.get_recent(limit=100))
        elif path.startswith("/report/"):
            self._serve_report(path.split("/")[-1])
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/send-report":
            self.send_error(404)
            return

        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except Exception:
            self._send_json({"ok": False, "message": "Invalid request"})
            return

        filepath = body.get("filepath", "")
        # Normalize path for DB lookup (Posix style)
        from pathlib import PurePosixPath, PureWindowsPath
        if ":" in filepath:
            filepath = PureWindowsPath(filepath).as_posix()
        else:
            filepath = Path(filepath).as_posix()

        fp = Path(filepath)
        report_filename = f"{fp.stem}_report.html"
        report_path = REPORTS_DIR / report_filename
        report_file = str(report_path) if report_path.exists() else None

        # Get problems from state (try both normalized and original)
        info = self.state.get_file_info(filepath)
        problems = []
        total_segments = 0
        if info and info.get("error_details"):
            problems = info["error_details"].get("problems", [])

        result = send_report_email(
            filename=fp.name,
            report_path=report_file,
            problems=problems,
            total_segments=total_segments,
            tolerance=0.1,
        )
        self._send_json(result)

    def _serve_report(self, filename):
        rp = REPORTS_DIR / filename
        if not rp.exists():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body style='background:#0f0f1a;color:#888;font-family:sans-serif;padding:40px'><h2>Report not found</h2><p>The report file <b>" + filename.encode() + b"</b> does not exist.</p><a href='/' style='color:#60a5fa'>Back to dashboard</a></body></html>")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        with open(rp, "rb") as f:
            self.wfile.write(f.read())

    def _send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        if len(args) >= 3:
            print(f"[WEB] {args[0]} {args[1]} {args[2]}")
        else:
            print(f"[WEB] {' '.join(str(a) for a in args)}")


def run_server(state, host=WEB_HOST, port=WEB_PORT):
    from threading import Thread
    import socket

    def _make_handler(*args, **kwargs):
        return CheckerAPIHandler(*args, state=state, **kwargs)

    try:
        server = HTTPServer((host, port), _make_handler)
        thread = Thread(target=server.serve_forever, daemon=True, name="web-server")
        thread.start()
        print(f"[WEB] Server: http://{host}:{port}")
        return server
    except (OSError, socket.error) as e:
        print(f"[WEB] Failed: {host}:{port} — {e}")
        return None
