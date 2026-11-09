import asyncio
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import asyncpg
import httpx

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

PAGE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>اختبار سرعة فرانكفورت</title>
<style>
body{margin:0;background:#101014;color:#f5f5f5;font-family:Arial,sans-serif;padding:24px}
main{max-width:520px;margin:35px auto;background:#1c1c23;border:1px solid #393943;border-radius:18px;padding:22px}
h2{color:#e24b4b;margin-top:0}p{color:#c7c7ce;line-height:1.7}
.item{background:#292932;border-radius:12px;padding:15px;margin:12px 0}
.value{font-size:25px;font-weight:bold;margin-top:7px}
small{color:#aaa}.ok{color:#54d68b}.bad{color:#ff7777}
button{background:#a92f38;color:white;border:0;border-radius:10px;padding:12px 18px;font-size:16px;width:100%;margin-top:12px}
</style></head>
<body><main>
<h2>اختبار سرعة سيرفر فرانكفورت</h2>
<p id="status">جاري قياس الاتصال بتيليجرام وقاعدة البيانات... انتظر قليلًا</p>
<div class="item"><div>اتصال Telegram API</div><div class="value" id="telegram">...</div><small id="telegram-note"></small></div>
<div class="item"><div>اتصال قاعدة البيانات</div><div class="value" id="database">...</div><small id="database-note"></small></div>
<button onclick="run()">إعادة الاختبار</button>
</main>
<script>
async function run(){
 const status=document.getElementById('status');
 status.textContent='جاري الاختبار...';
 for(const id of ['telegram','database']){document.getElementById(id).textContent='...';document.getElementById(id+'-note').textContent='';}
 try{
  const r=await fetch('/probe/data?ts='+Date.now(),{cache:'no-store'});
  if(!r.ok) throw new Error('HTTP '+r.status);
  const d=await r.json();
  for(const id of ['telegram','database']){
   const x=d[id]||{};
   const el=document.getElementById(id);
   if(x.duration_ms!==undefined){el.textContent=x.duration_ms+' ms';el.className='value '+(x.ok?'ok':'bad');}
   else{el.textContent='تعذر القياس';el.className='value bad';}
   document.getElementById(id+'-note').textContent=x.error||('HTTP '+(x.http_status||'—')+(x.http_version?' • '+x.http_version:''));
  }
  status.textContent='اكتمل الاختبار. هذه أوقات الاتصال من فرانكفورت.';
 }catch(e){status.textContent='فشل تحميل نتيجة الاختبار: '+e.message;}
}
run();
</script></body></html>"""

async def run_probe():
    result = {}
    if not BOT_TOKEN:
        result["telegram"] = {"error": "BOT_TOKEN is not configured"}
    else:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(http2=True, timeout=12.0) as client:
                response = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
                result["telegram"] = {
                    "http_status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "http_version": response.http_version,
                    "ok": response.status_code == 200,
                }
        except Exception as exc:
            result["telegram"] = {
                "error": type(exc).__name__,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }

    if not DATABASE_URL:
        result["database"] = {"error": "DATABASE_URL is not configured"}
    else:
        started = time.perf_counter()
        conn = None
        try:
            async def db_check():
                nonlocal conn
                conn = await asyncpg.connect(DATABASE_URL, timeout=8)
                return await conn.fetchval("SELECT 1")
            await asyncio.wait_for(db_check(), timeout=10)
            result["database"] = {
                "ok": True,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        except Exception as exc:
            result["database"] = {
                "error": type(exc).__name__,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        finally:
            if conn is not None:
                try:
                    await conn.close(timeout=2)
                except Exception:
                    pass
    return result

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        print(f"HTTP {self.command} {path}", flush=True)
        if path == "/probe":
            body = PAGE.encode("utf-8")
            content_type = "text/html; charset=utf-8"
            status = 200
        elif path == "/probe/data":
            payload = asyncio.run(run_probe())
            print("PROBE_RESULT " + json.dumps(payload), flush=True)
            body = json.dumps(payload).encode("utf-8")
            content_type = "application/json; charset=utf-8"
            status = 200
        elif path in ("/", "/health"):
            body = "Frankfurt network probe ready".encode()
            content_type = "text/plain; charset=utf-8"
            status = 200
        else:
            body = b"Not found"
            content_type = "text/plain; charset=utf-8"
            status = 404
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print(f"Frankfurt probe listening on port {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
