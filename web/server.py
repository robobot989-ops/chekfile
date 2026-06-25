import json
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from monitor.state import CheckState
from config import REPORTS_DIR, WEB_HOST, WEB_PORT


INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>DXF Checker Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0f0f1a;color:#e0e0e0;padding:30px}
h1{color:#b0b0d0;margin-bottom:20px}
.stats{display:flex;gap:20px;margin-bottom:30px}
.stat-card{background:#1a1a35;border:1px solid #2a2a4a;border-radius:8px;padding:20px;min-width:150px}
.stat-card .num{font-size:28px;font-weight:700;color:#e0e0ff}
.stat-card .label{font-size:12px;color:#888;margin-top:4px}
table{width:100%;border-collapse:collapse;background:#16162a;border-radius:8px;overflow:hidden}
th{background:#1a1a35;padding:10px 14px;text-align:left;font-size:12px;color:#888;border-bottom:2px solid #2a2a4a}
td{padding:10px 14px;border-bottom:1px solid #2a2a4a;font-size:13px}
tr:hover{background:#1e1e3a}
.status-ok{color:#4ade80;font-weight:600}
.status-error{color:#f87171;font-weight:600}
a{color:#60a5fa;text-decoration:none}
a:hover{text-decoration:underline}
.refresh{background:#2a2a4a;border:1px solid #3a3a5a;color:#e0e0e0;padding:8px 16px;border-radius:4px;cursor:pointer;margin-bottom:20px;font-size:13px}
.refresh:hover{background:#3a3a5a}
</style></head>
<body>
<h1>DXF Checker Dashboard</h1>
<div class="stats" id="stats"></div>
<button class="refresh" onclick="loadData()">Обновить</button>
<table id="files-table">
<thead><tr><th>Файл</th><th>Статус</th><th>Проблем</th><th>Проверен</th><th>Отчёт</th></tr></thead>
<tbody id="files-body"></tbody></table>
<script>
async function loadData(){
  const [stats,recent] = await Promise.all([
    fetch('/api/stats').then(r=>r.json()),
    fetch('/api/recent').then(r=>r.json())
  ]);
  document.getElementById('stats').innerHTML = `
    <div class="stat-card"><div class="num">${stats.today_checked}</div><div class="label">Проверено сегодня</div></div>
    <div class="stat-card"><div class="num">${stats.with_errors}</div><div class="label">С ошибками</div></div>
    <div class="stat-card"><div class="num">${stats.total}</div><div class="label">Всего проверено</div></div>
  `;
  const tbody = document.getElementById('files-body');
  tbody.innerHTML = recent.map(f => {
    const cls = f.has_errors ? 'status-error' : 'status-ok';
    const label = f.has_errors ? '\u26A0 ' + f.total_problems : '\u2713 OK';
    const rname = f.report_path ? f.report_path.split(/[\\\\/]/).pop() : '';
    const rlink = rname ? '<a href="/report/' + rname + '" target="_blank">\u041E\u0442\u043A\u0440\u044B\u0442\u044C</a>' : '';
    return '<tr>'
      + '<td>' + f.filename + '</td>'
      + '<td class="' + cls + '">' + f.status + '</td>'
      + '<td>' + label + '</td>'
      + '<td>' + (f.checked_at || '') + '</td>'
      + '<td>' + rlink + '</td>'
      + '</tr>';
  }).join('');
}
loadData();
setInterval(loadData, 10000);
</script>
</body></html>"""


class CheckerAPIHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        self.state = kwargs.pop("state", None)
        super().__init__(*args, **kwargs)

    def do_GET(self):
        from urllib.parse import urlparse
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._send_html(INDEX_HTML)
        elif path == "/api/stats":
            self._send_json(self.state.get_stats())
        elif path == "/api/recent":
            self._send_json(self.state.get_recent(limit=100))
        elif path.startswith("/report/"):
            filename = path.split("/")[-1]
            self._serve_report(filename)
        else:
            self.send_error(404)

    def _serve_report(self, filename: str):
        report_path = REPORTS_DIR / filename
        if not report_path.exists():
            self.send_error(404, "Report not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        with open(report_path, "rb") as f:
            self.wfile.write(f.read())

    def _send_html(self, html: str):
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
        print(f"[WEB] {args[0]} {args[1]} {args[2]}")


def run_server(state: CheckState, host: str = WEB_HOST, port: int = WEB_PORT):
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
        print(f"[WEB] Failed to start server on {host}:{port} — {e}")
        print(f"[WEB] Try a different port: --web-port PORT or change WEB_PORT in config.py")
        return None
