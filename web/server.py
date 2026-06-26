import json
import re
import os
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from monitor.state import CheckState
from config import REPORTS_DIR, WEB_HOST, WEB_PORT, DATA_DIR
from .emailer import send_report_email
from checker.report import generate_report
from .settings_manager import SettingsManager

SETTINGS_PATH = Path(DATA_DIR) / "settings.json"

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
        "settings": "Настройки",
        "upload": "Загрузить",
        "sort_by": "Сортировка",
        "filter_date": "Фильтр по дате",
        "all": "Все",
        "today": "Сегодня",
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
        "settings": "Settings",
        "upload": "Upload",
        "sort_by": "Sort",
        "filter_date": "Filter by date",
        "all": "All",
        "today": "Today",
    },
}

DASHBOARD_TMPL = """<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DXF Checker</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',sans-serif;background:#0f0f1a;color:#e0e0e0;padding:30px}}
h1{{color:#b0b0d0;margin-bottom:20px;display:inline-block}}
.top-bar{{float:right;display:flex;gap:8px}}
.top-bar button{{background:#2a2a4a;border:1px solid #3a3a5a;color:#e0e0e0;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:12px}}
.top-bar button:hover{{background:#3a3a5a}}
.stats{{display:flex;gap:20px;margin-bottom:30px}}
.stat-card{{background:#1a1a35;border:1px solid #2a2a4a;border-radius:8px;padding:20px;min-width:150px}}
.stat-card .num{{font-size:28px;font-weight:700;color:#e0e0ff}}
.stat-card .label{{font-size:12px;color:#888;margin-top:4px}}
.controls{{display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap}}
.controls select,.controls input{{background:#16162a;border:1px solid #2a2a4a;color:#e0e0e0;padding:6px 10px;border-radius:4px;font-size:12px}}
.controls label{{font-size:12px;color:#888}}
table{{width:100%;border-collapse:collapse;background:#16162a;border-radius:8px;overflow:hidden}}
th{{background:#1a1a35;padding:10px 14px;text-align:left;font-size:12px;color:#888;border-bottom:2px solid #2a2a4a;cursor:pointer;user-select:none;white-space:nowrap}}
th:hover{{color:#e0e0e0}}
th::after{{content:' \\u2195';font-size:10px;opacity:.4}}
th.sort-asc::after{{content:' \\u2191';opacity:1;color:#4ade80}}
th.sort-desc::after{{content:' \\u2193';opacity:1;color:#f87171}}
td{{padding:10px 14px;border-bottom:1px solid #2a2a4a;font-size:13px}}
tr{{cursor:pointer}}tr:hover{{background:#1e1e3a}}
.status-ok{{color:#4ade80;font-weight:600}}
.status-error{{color:#f87171;font-weight:600}}
.status-pending{{color:#facc15;font-weight:600}}
.hidden{{display:none!important}}
</style></head>
<body>
<h1>DXF Checker</h1>
<div class="top-bar">
  <button onclick="location.href='/upload'">{upload}</button>
  <button onclick="location.href='/settings'">{settings}</button>
  <button onclick="toggleLang()">{other_lang}</button>
</div>
<div class="stats" id="stats"></div>
<div class="controls">
  <label>{sort_by}: <select id="sort-select" onchange="applySortFilter()">
    <option value="filename">{file_h}</option>
    <option value="checked_at">{checked_h}</option>
    <option value="total_problems">{problems_h}</option>
    <option value="status">{status_h}</option>
  </select></label>
  <label>{filter_date}: <input type="date" id="date-filter" onchange="applySortFilter()"></label>
  <button class="refresh" onclick="loadData()" style="background:#2a2a4a;border:1px solid #3a3a5a;color:#e0e0e0;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:12px">{refresh}</button>
</div>
<table><thead><tr>
<th data-col="filename" onclick="sortBy('filename')">{file_h}</th>
<th data-col="status" onclick="sortBy('status')">{status_h}</th>
<th data-col="total_problems" onclick="sortBy('total_problems')">{problems_h}</th>
<th data-col="checked_at" onclick="sortBy('checked_at')">{checked_h}</th>
<th>{report_h}</th>
</tr></thead><tbody id="files-body"></tbody></table>
<script>
const LANG='{lang}';
const TXT={{no:'{no}',stat_today:'{stat_today}',stat_errors:'{stat_errors}',stat_total:'{stat_total}'}};
const otherLang=LANG==='ru'?'en':'ru';
let allFiles=[];
let sortCol='checked_at';
let sortDesc=true;

function sortBy(col){{
  if(sortCol===col)sortDesc=!sortDesc;
  else{{sortCol=col;sortDesc=col==='checked_at'||col==='total_problems'}}
  document.querySelectorAll('th').forEach(th=>th.classList.remove('sort-asc','sort-desc'));
  const el=document.querySelector('th[data-col="'+col+'"]');
  if(el)el.classList.add(sortDesc?'sort-desc':'sort-asc');
  renderTable();
}}

function applySortFilter(){{
  document.getElementById('sort-select').value=sortCol;
  renderTable();
}}

function renderTable(){{
  const dateFilter=document.getElementById('date-filter').value;
  const sortSel=document.getElementById('sort-select').value;
  sortCol=sortSel;

  let files=[...allFiles];

  if(dateFilter){{
    files=files.filter(f=>f.checked_at&&f.checked_at.startsWith(dateFilter));
  }}

  files.sort((a,b)=>{{
    let va=a[sortCol]??'',vb=b[sortCol]??'';
    if(sortCol==='total_problems'){{va=Number(va)||0;vb=Number(vb)||0}}
    else{{va=String(va).toLowerCase();vb=String(vb).toLowerCase()}}
    if(va<vb)return sortDesc?1:-1;
    if(va>vb)return sortDesc?-1:1;
    return 0;
  }});

  document.getElementById('files-body').innerHTML=files.map(f=>{{
    const c=f.has_errors?'status-error':'status-ok';
    const l=f.has_errors?'\\u26A0 '+f.total_problems:'\\u2713 OK';
    const rn=f.report_path&&f.report_exists?f.report_path.split(/[\\\\/]/).pop():'';
    const openLink=rn?'<a href="/report/'+rn+'" target="_blank" onclick="event.stopPropagation()">{open_l}</a>':TXT.no;
    return '<tr'+(rn?' onclick="window.open(\\'/report/'+rn+'\\',\\'_blank\\')"':'')+'>'
      +'<td>'+f.filename+'</td><td class="'+c+'">'+f.status+'</td><td>'+l+'</td>'
      +'<td>'+(f.checked_at||TXT.no)+'</td><td>'+openLink+'</td></tr>';
  }}).join('');
}}

async function loadData(){{
  const[s,r]=await Promise.all([
    fetch('/api/stats?lang='+LANG).then(r=>r.json()),
    fetch('/api/recent?lang='+LANG).then(r=>r.json())
  ]);
  document.getElementById('stats').innerHTML=
    '<div class="stat-card"><div class="num">'+s.today_checked+'</div><div class="label">'+TXT.stat_today+'</div></div>'
    +'<div class="stat-card"><div class="num">'+s.with_errors+'</div><div class="label">'+TXT.stat_errors+'</div></div>'
    +'<div class="stat-card"><div class="num">'+s.total+'</div><div class="label">'+TXT.stat_total+'</div></div>';
  allFiles=r;
  renderTable();
}}
loadData();
setInterval(loadData,10000);
function toggleLang(){{const u=new URL(window.location);u.searchParams.set('lang',otherLang);window.location=u}}
</script></body></html>"""

SETTINGS_TMPL = """<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Settings — DXF Checker</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',sans-serif;background:#0f0f1a;color:#e0e0e0;padding:30px;max-width:800px;margin:0 auto}}
h1{{color:#b0b0d0;margin-bottom:24px}}
h2{{color:#888;font-size:14px;margin:20px 0 10px;border-bottom:1px solid #2a2a4a;padding-bottom:6px}}
.form-group{{margin-bottom:12px;display:flex;align-items:center;gap:12px}}
.form-group label{{min-width:200px;font-size:13px;color:#b0b0d0}}
.form-group input,.form-group select{{flex:1;background:#16162a;border:1px solid #2a2a4a;color:#e0e0e0;padding:8px 12px;border-radius:4px;font-size:13px;max-width:400px}}
.form-group input[type="checkbox"]{{max-width:20px;min-width:20px;height:20px}}
.form-group .hint{{font-size:11px;color:#666;margin-top:2px}}
.btn-row{{display:flex;gap:12px;margin-top:24px}}
.btn-row button{{padding:8px 20px;border-radius:4px;cursor:pointer;font-size:13px;border:1px solid #3a3a5a}}
.btn-save{{background:#1a4a3a;color:#4ade80;border-color:#2a6a4a}}
.btn-back{{background:#2a2a4a;color:#e0e0e0}}
.btn-save:hover{{background:#2a6a4a}}
.btn-back:hover{{background:#3a3a5a}}
.msg{{padding:10px 14px;border-radius:4px;margin-bottom:16px;font-size:13px;display:none}}
.msg.ok{{display:block;background:#1a3a2a;color:#4ade80;border:1px solid #2a5a3a}}
.msg.err{{display:block;background:#3a1a1a;color:#f87171;border:1px solid #5a2a2a}}
</style></head>
<body>
<h1>Settings</h1>
<div id="msg" class="msg"></div>
<form id="settings-form">
<h2>Checker</h2>
<div class="form-group"><label>Tolerance (mm)</label><input name="checker.tolerance" type="number" step="0.01" value="{{tolerance}}"></div>
<div class="form-group"><label>Min problem distance (mm)</label><input name="checker.min_problem_distance" type="number" step="0.001" value="{{min_distance}}"></div>
<div class="form-group"><label>Double line check</label><input name="checker.double_line_check" type="checkbox" {{double_line_check}}></div>
<div class="form-group"><label>Bridge check</label><input name="checker.bridge_check" type="checkbox" {{bridge_check}}></div>
<div class="form-group"><label>Bridge min gap (mm)</label><input name="checker.bridge_min" type="number" step="0.1" value="{{bridge_min}}"></div>
<div class="form-group"><label>Bridge max gap (mm)</label><input name="checker.bridge_max" type="number" step="0.1" value="{{bridge_max}}"></div>
<div class="form-group"><label>Bridge exclude colors</label><input name="checker.bridge_exclude_colors" value="{{bridge_exclude_colors}}"><div class="hint">Comma-separated hex colors, e.g. #00ffff,#ff0000</div></div>
<div class="form-group"><label>Bridge max hole diameter (mm)</label><input name="checker.bridge_max_hole_diameter" type="number" step="0.5" value="{{bridge_max_hole}}"></div>
<h2>Monitor</h2>
<div class="form-group"><label>Poll interval (sec)</label><input name="monitor.poll_interval" type="number" value="{{poll_interval}}"></div>
<div class="form-group"><label>Watchdog enabled</label><input name="monitor.watchdog" type="checkbox" {{watchdog}}></div>
<div class="form-group"><label>Max workers</label><input name="monitor.max_workers" type="number" value="{{max_workers}}"></div>
<h2>Email</h2>
<div class="form-group"><label>SMTP host</label><input name="email.smtp_host" value="{{smtp_host}}"></div>
<div class="form-group"><label>SMTP port</label><input name="email.smtp_port" type="number" value="{{smtp_port}}"></div>
<div class="form-group"><label>From address</label><input name="email.from_addr" value="{{from_addr}}"></div>
<div class="form-group"><label>To address</label><input name="email.to_addr" value="{{to_addr}}"></div>
<div class="form-group"><label>SMTP password</label><input name="email.smtp_password" type="password" value="{{smtp_password}}"></div>
<div class="form-group"><label>Use TLS</label><input name="email.use_tls" type="checkbox" {{use_tls}}></div>
<h2>Web</h2>
<div class="form-group"><label>Port</label><input name="web.port" type="number" value="{{web_port}}"></div>
</form>
<div class="btn-row">
<button class="btn-save" onclick="saveSettings()">Save</button>
<button class="btn-back" onclick="location.href='/'">Back</button>
</div>
<script>
async function saveSettings(){{
  const form=document.getElementById('settings-form');
  const data={{}};
  form.querySelectorAll('[name]').forEach(el=>{{
    let val=el.type==='checkbox'?el.checked:el.value;
    if(el.type==='number')val=parseFloat(val);
    const keys=el.name.split('.');
    let obj=data;
    for(let i=0;i<keys.length-1;i++){{
      if(!obj[keys[i]])obj[keys[i]]={{}};
      obj=obj[keys[i]];
    }}
    obj[keys[keys.length-1]]=val;
  }});
  // Handle bridge_exclude_colors as array
  if(typeof data.checker?.bridge_exclude_colors==='string'){{
    data.checker.bridge_exclude_colors=data.checker.bridge_exclude_colors.split(',').map(s=>s.trim()).filter(Boolean);
  }}
  try{{
    const r=await fetch('/api/settings',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
    const j=await r.json();
    const msg=document.getElementById('msg');
    if(j.ok){{msg.className='msg ok';msg.textContent='Saved'}}else{{msg.className='msg err';msg.textContent=j.message||'Error'}}
    msg.style.display='block';
    setTimeout(()=>msg.style.display='none',3000);
  }}catch(e){{
    const msg=document.getElementById('msg');
    msg.className='msg err';msg.textContent='Network error';
    msg.style.display='block';
  }}
}}
</script></body></html>"""

UPLOAD_TMPL = """<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Upload DXF — DXF Checker</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',sans-serif;background:#0f0f1a;color:#e0e0e0;padding:30px;max-width:600px;margin:0 auto}}
h1{{color:#b0b0d0;margin-bottom:20px}}
.drop-zone{{border:2px dashed #3a3a5a;border-radius:12px;padding:60px 20px;text-align:center;cursor:pointer;transition:all .2s;margin-bottom:16px}}
.drop-zone:hover,.drop-zone.dragover{{border-color:#4ade80;background:#1a2a2a}}
.drop-zone p{{font-size:16px;color:#888;margin-bottom:8px}}
.drop-zone .hint{{font-size:12px;color:#555}}
#file-input{{display:none}}
#status{{margin-top:16px;font-size:14px;display:none;padding:12px;border-radius:6px}}
#status.loading{{display:block;background:#1a1a35;color:#888}}
#status.done{{display:block;background:#1a3a2a;color:#4ade80;border:1px solid #2a5a3a}}
#status.error{{display:block;background:#3a1a1a;color:#f87171;border:1px solid #5a2a2a}}
#status a{{color:#60a5fa}}
.btn-back{{display:inline-block;margin-top:16px;background:#2a2a4a;color:#e0e0e0;padding:8px 16px;border-radius:4px;text-decoration:none;font-size:13px}}
.btn-back:hover{{background:#3a3a5a}}
</style></head>
<body>
<h1>Upload DXF</h1>
<div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
  <p>Drop DXF file here or click to select</p>
  <div class="hint">Only .dxf files</div>
  <input type="file" id="file-input" accept=".dxf">
</div>
<div id="status"></div>
<a class="btn-back" href="/">Back</a>
<script>
const dz=document.getElementById('drop-zone');
const fi=document.getElementById('file-input');
const st=document.getElementById('status');
const LANG='{lang}';
['dragover','dragenter'].forEach(e=>dz.addEventListener(e,e=>{{e.preventDefault();dz.classList.add('dragover')}}));
['dragleave','drop'].forEach(e=>dz.addEventListener(e,e=>{{e.preventDefault();dz.classList.remove('dragover')}}));
dz.addEventListener('drop',e=>{{const f=e.dataTransfer.files[0];if(f)upload(f)}});
fi.addEventListener('change',()=>{{if(fi.files[0])upload(fi.files[0])}});
async function upload(file){{
  if(!file.name.toLowerCase().endsWith('.dxf')){{st.className='msg error';st.textContent=LANG==='ru'?'Только .dxf файлы':'Only .dxf files';return}}
  const form=new FormData();
  form.append('file',file);
  st.className='msg loading';
  st.textContent=LANG==='ru'?'Проверка...':'Checking...';
  try{{
    const r=await fetch('/api/upload',{{method:'POST',body:form}});
    const j=await r.json();
    if(j.ok){{
      st.className='msg done';
      const txt=LANG==='ru'?'Проверено. Отчёт: ':'Checked. Report: ';
      st.innerHTML=txt+'<a href="/report/'+j.report_file.split(/[\\\\/]/).pop()+'" target="_blank">'+j.report_file.split(/[\\\\/]/).pop()+'</a>';
      if(j.total_problems>0)st.innerHTML+='<br>'+j.total_problems+' '+(LANG==='ru'?'проблем(ы)':'problem(s)');
    }}else{{
      st.className='msg error';
      st.textContent=j.message||'Error';
    }}
  }}catch(e){{
    st.className='msg error';
    st.textContent='Network error';
  }}
}}
</script></body></html>"""


def _build_dashboard(lang):
    d = LANG.get(lang, LANG["ru"])
    return DASHBOARD_TMPL.format(lang=lang, **d)


def _build_settings(lang):
    sm = SettingsManager(str(SETTINGS_PATH))
    s = sm.all()
    c = s.get("checker", {})
    m = s.get("monitor", {})
    e = s.get("email", {})
    w = s.get("web", {})
    exclude_colors = c.get("bridge_exclude_colors", ["#00ffff"])
    return SETTINGS_TMPL.format(
        lang=lang,
        tolerance=c.get("tolerance", 0.1),
        min_distance=c.get("min_problem_distance", 0.001),
        double_line_check="checked" if c.get("double_line_check", True) else "",
        bridge_check="checked" if c.get("bridge_check", True) else "",
        bridge_min=c.get("bridge_min", 1.0),
        bridge_max=c.get("bridge_max", 6.0),
        bridge_exclude_colors=",".join(exclude_colors),
        bridge_max_hole=c.get("bridge_max_hole_diameter", 10.0),
        poll_interval=m.get("poll_interval", 30),
        watchdog="checked" if m.get("watchdog", True) else "",
        max_workers=m.get("max_workers", 4),
        smtp_host=e.get("smtp_host", "192.168.1.100"),
        smtp_port=e.get("smtp_port", 25),
        from_addr=e.get("from_addr", "ab@lasertechno.ru"),
        to_addr=e.get("to_addr", "shtamp_error@lasertechno.ru"),
        smtp_password=e.get("smtp_password", ""),
        use_tls="checked" if e.get("use_tls", False) else "",
        web_port=w.get("port", 8080),
    )


def _build_upload(lang):
    return UPLOAD_TMPL.format(lang=lang)


class CheckerAPIHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        self.state = kwargs.pop("state", None)
        self.settings = SettingsManager(str(SETTINGS_PATH))
        super().__init__(*args, **kwargs)

    def _lang(self):
        return parse_qs(urlparse(self.path).query).get("lang", ["ru"])[0]

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._send_html(_build_dashboard(self._lang()))
        elif path == "/settings":
            self._send_html(_build_settings(self._lang()))
        elif path == "/upload":
            self._send_html(_build_upload(self._lang()))
        elif path == "/api/stats":
            self._send_json(self.state.get_stats())
        elif path == "/api/recent":
            self._send_json(self.state.get_recent(limit=200))
        elif path == "/api/settings":
            self._send_json(self.settings.all())
        elif path.startswith("/report/"):
            self._serve_report(path.split("/")[-1])
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/send-report":
            self._handle_send_report()
        elif path == "/api/settings":
            self._handle_save_settings()
        elif path == "/api/upload":
            self._handle_upload()
        else:
            self.send_error(404)

    def _handle_send_report(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except Exception:
            self._send_json({"ok": False, "message": "Invalid request"})
            return

        filepath = body.get("filepath", "")
        from pathlib import PurePosixPath, PureWindowsPath
        if ":" in filepath:
            filepath = PureWindowsPath(filepath).as_posix()
        else:
            filepath = Path(filepath).as_posix()

        fp = Path(filepath)
        report_filename = f"{fp.stem}_report.html"
        report_path = REPORTS_DIR / report_filename
        report_file = str(report_path) if report_path.exists() else None

        info = self.state.get_file_info(filepath)
        problems = []
        if info and info.get("error_details"):
            problems = info["error_details"].get("problems", [])

        smtp_host = self.settings.get("email", "smtp_host", default="192.168.1.100")
        smtp_port = self.settings.get("email", "smtp_port", default=25)
        from_addr = self.settings.get("email", "from_addr", default="ab@lasertechno.ru")
        to_addr = self.settings.get("email", "to_addr", default="shtamp_error@lasertechno.ru")
        smtp_pass = self.settings.get("email", "smtp_password", default="")
        use_tls = self.settings.get("email", "use_tls", default=False)

        result = send_report_email(
            filename=fp.name,
            report_path=report_file,
            problems=problems,
            total_segments=0,
            tolerance=0.1,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            from_addr=from_addr,
            to_addr=to_addr,
            smtp_password=smtp_pass,
            use_tls=use_tls,
        )
        self._send_json(result)

    def _handle_save_settings(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except Exception as e:
            self._send_json({"ok": False, "message": str(e)})
            return
        self.settings.update_from_dict(body)
        self._send_json({"ok": True})

    def _handle_upload(self):
        import tempfile
        import shutil
        import uuid

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"ok": False, "message": "Expected multipart/form-data"})
            return

        try:
            boundary = content_type.split("boundary=")[1].strip()
        except Exception:
            self._send_json({"ok": False, "message": "No boundary"})
            return

        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))

        # Simple multipart parser
        boundary_bytes = ("--" + boundary).encode()
        parts = body.split(boundary_bytes)
        filename = None
        file_data = None

        for part in parts:
            if b'name="file"' in part or b'filename="' in part:
                # Extract filename
                import re as re_m
                m = re_m.search(rb'filename="([^"]*)"', part)
                if m:
                    filename = m.group(1).decode("utf-8", errors="replace")
                # Find double CRLF separating headers from body
                idx = part.find(b"\r\n\r\n")
                if idx > 0:
                    file_data = part[idx + 4:].rstrip(b"\r\n--")

        if not filename or not file_data:
            self._send_json({"ok": False, "message": "No file received"})
            return

        if not filename.lower().endswith(".dxf"):
            self._send_json({"ok": False, "message": "Only .dxf files allowed"})
            return

        temp_dir = Path(tempfile.gettempdir()) / "dxf_uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        dest = temp_dir / f"{uuid.uuid4().hex}_{filename}"
        dest.write_bytes(file_data)

        try:
            flat = self.settings.to_flat()
            result = generate_report(str(dest), str(REPORTS_DIR), settings=flat, lang=self._lang())
            self._send_json({
                "ok": True,
                "filename": result["filename"],
                "total_problems": result["total_problems"],
                "has_errors": result["has_errors"],
                "report_file": result["report_file"],
            })
        except Exception as e:
            self._send_json({"ok": False, "message": str(e)})
        finally:
            if dest.exists():
                try:
                    dest.unlink()
                except Exception:
                    pass

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
