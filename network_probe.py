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
<div class="item"><div>متوسط الاستعلامات على اتصال ثابت (10 مرات)</div><div class="value" id="database">...</div><small id="database-note"></small></div>
<div class="item"><div>وقت فتح اتصال قاعدة البيانات</div><div class="value" id="db-connect">...</div><small>يقاس منفصلًا ولا يدخل في متوسط الاستعلامات</small></div>
<button onclick="run()">إعادة الاختبار</button>
</main>
<script>
async function run(){
 const status=document.getElementById('status');
 status.textContent='جاري الاختبار...';
 for(const id of ['telegram','database','db-connect']){document.getElementById(id).textContent='...';}
 document.getElementById('telegram-note').textContent='';
 document.getElementById('database-note').textContent='';
 try{
  const r=await fetch('/probe/data?ts='+Date.now(),{cache:'no-store'});
  if(!r.ok) throw new Error('HTTP '+r.status);
  const d=await r.json();
  for(const id of ['telegram','database']){
   const x=d[id]||{};
   const el=document.getElementById(id);
   if(id==='database'){
    if(x.query_avg_ms!==undefined){el.textContent=x.query_avg_ms+' ms';el.className='value '+(x.ok?'ok':'bad');}
    else{el.textContent='تعذر القياس';el.className='value bad';}
    document.getElementById('database-note').textContent=x.error||('10 استعلامات • أقل '+x.query_min_ms+' ms • أعلى '+x.query_max_ms+' ms');
    const connect=document.getElementById('db-connect');
    connect.textContent=x.connect_ms!==undefined?x.connect_ms+' ms':'—';
    connect.className='value '+(x.ok?'ok':'bad');
   }else{
    if(x.avg_ms!==undefined){el.textContent=x.avg_ms+' ms';el.className='value '+(x.ok?'ok':'bad');}
    else{el.textContent='تعذر القياس';el.className='value bad';}
    document.getElementById('telegram-note').textContent=x.error||('10 طلبات متتالية • أقل '+x.min_ms+' ms • أعلى '+x.max_ms+' ms • HTTP '+(x.http_status||'—')+(x.http_version?' • '+x.http_version:''));
   }
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
        samples = []
        try:
            # Reuse one HTTP/2 client like a persistent bot connection.
            async with httpx.AsyncClient(http2=True, timeout=12.0) as client:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"

                # Warm up DNS/TLS/HTTP2 connection; exclude this first request.
                warmup = await client.get(url)
                if warmup.status_code != 200:
                    raise RuntimeError(f"Telegram warm-up HTTP {warmup.status_code}")

                statuses = []
                versions = []
                for _ in range(10):
                    started = time.perf_counter()
                    response = await client.get(url)
                    samples.append(round((time.perf_counter() - started) * 1000, 2))
                    statuses.append(response.status_code)
                    versions.append(response.http_version)
                    if response.status_code != 200:
                        raise RuntimeError(f"Telegram HTTP {response.status_code}")

            result["telegram"] = {
                "ok": True,
                "http_status": statuses[-1],
                "http_version": versions[-1],
                "avg_ms": round(sum(samples) / len(samples), 2),
                "min_ms": round(min(samples), 2),
                "max_ms": round(max(samples), 2),
                "samples_ms": samples,
                "request_count": len(samples),
            }
        except Exception as exc:
            result["telegram"] = {
                "ok": False,
                "error": type(exc).__name__ + ": " + str(exc)[:120],
                "avg_ms": round(sum(samples) / len(samples), 2) if samples else None,
                "min_ms": round(min(samples), 2) if samples else None,
                "max_ms": round(max(samples), 2) if samples else None,
            }

    if not DATABASE_URL:
        result["database"] = {"error": "DATABASE_URL is not configured"}
    else:
        conn = None
        connect_started = time.perf_counter()
        try:
            # Measure connection establishment separately from query latency.
            conn = await asyncio.wait_for(
                asyncpg.connect(DATABASE_URL, timeout=8),
                timeout=10,
            )
            connect_ms = round((time.perf_counter() - connect_started) * 1000, 1)

            # Warm up the connection once; exclude this first query from the samples.
            await conn.fetchval("SELECT 1")

            samples = []
            for _ in range(10):
                query_started = time.perf_counter()
                value = await conn.fetchval("SELECT 1")
                elapsed_ms = (time.perf_counter() - query_started) * 1000
                if value != 1:
                    raise RuntimeError("Unexpected database response")
                samples.append(round(elapsed_ms, 2))

            result["database"] = {
                "ok": True,
                "connect_ms": connect_ms,
                "query_avg_ms": round(sum(samples) / len(samples), 2),
                "query_min_ms": round(min(samples), 2),
                "query_max_ms": round(max(samples), 2),
                "query_samples_ms": samples,
                "query_count": len(samples),
            }
        except Exception as exc:
            result["database"] = {
                "ok": False,
                "error": type(exc).__name__,
                "connect_ms": round((time.perf_counter() - connect_started) * 1000, 1),
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
