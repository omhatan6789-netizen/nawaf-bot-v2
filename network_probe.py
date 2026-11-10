import asyncio
import json
import os
import time
import tempfile
import html
import shutil
from urllib.parse import parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import asyncpg
import httpx

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SOURCE_DATABASE_URL = os.environ.get("SOURCE_DATABASE_URL", "").strip()
TRANSFER_SECRET = os.environ.get("TRANSFER_SECRET", "").strip()

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
button,.button{display:block;box-sizing:border-box;text-align:center;text-decoration:none;background:#a92f38;color:white;border:0;border-radius:10px;padding:13px 18px;font-size:16px;width:100%;margin-top:12px}
input{box-sizing:border-box;width:100%;padding:13px;border-radius:9px;border:1px solid #555;background:#111;color:white}
</style></head>
<body><main>
<h2>اختبار سرعة سيرفر فرانكفورت</h2>
<p>{{STATUS}}</p>
<div class="item"><div>اتصال Telegram API</div><div class="value {{TG_CLASS}}">{{TG_VALUE}}</div><small>{{TG_NOTE}}</small></div>
<div class="item"><div>متوسط الاستعلامات على اتصال ثابت (10 مرات)</div><div class="value {{DB_CLASS}}">{{DB_VALUE}}</div><small>{{DB_NOTE}}</small></div>
<div class="item"><div>وقت فتح اتصال قاعدة البيانات</div><div class="value {{CONNECT_CLASS}}">{{CONNECT_VALUE}}</div><small>يقاس منفصلًا ولا يدخل في متوسط الاستعلامات</small></div>
<a class="button" href="/probe?refresh=1">إعادة الاختبار</a>
<hr style="border:0;border-top:1px solid #393943;margin:22px 0">
<h2 style="font-size:18px">نسخ قاعدة سنغافورة إلى فرانكفورت</h2>
<p>هذه العملية تنسخ مخطط public وبياناته. لن تلمس قاعدة الإنتاج أو تغيّر اتصال البوت. لن يبدأ النسخ إلا بعد إرسال النموذج أدناه.</p>
<form action="/transfer" method="post">
<input name="secret" type="password" autocomplete="off" required placeholder="مفتاح النسخ الذي أضفته في Render">
<label style="display:block;margin-top:14px;color:#ddd;line-height:1.7"><input type="checkbox" required style="width:auto"> أؤكد أنني أريد نسخ قاعدة سنغافورة إلى قاعدة فرانكفورت الفارغة</label>
<button type="submit">بدء النسخ والتحقق</button>
</form>
</main></body></html>"""

TRANSFER_RESULT_PAGE = """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>نتيجة نسخ قاعدة البيانات</title>
<style>body{margin:0;padding:24px;background:#101014;color:#f5f5f5;font-family:Arial}main{max-width:520px;margin:35px auto;padding:22px;background:#1c1c23;border:1px solid #393943;border-radius:18px}h2{color:#e24b4b}.ok{color:#54d68b}.bad{color:#ff7777}p{line-height:1.8;white-space:pre-wrap}.button{display:block;text-align:center;background:#a92f38;color:white;text-decoration:none;padding:13px;border-radius:10px;margin-top:18px}</style></head>
<body><main><h2>نتيجة عملية النسخ</h2><p class="{{CLASS}}">{{MESSAGE}}</p><a class="button" href="/probe">العودة إلى صفحة الاختبار</a></main></body></html>"""

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

async def _table_counts(conn):
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    counts = {}
    for row in tables:
        name = row["tablename"].replace('"', '""')
        counts[row["tablename"]] = await conn.fetchval(f'SELECT count(*) FROM public."{name}"')
    return counts


async def transfer_database():
    if not SOURCE_DATABASE_URL or not DATABASE_URL:
        return {"ok": False, "error": "SOURCE_DATABASE_URL أو DATABASE_URL غير مضبوط."}
    if not TRANSFER_SECRET:
        return {"ok": False, "error": "TRANSFER_SECRET غير مضبوط."}
    missing_tools = [name for name in ("pg_dump", "pg_restore") if not shutil.which(name)]
    if missing_tools:
        return {"ok": False, "error": "أدوات PostgreSQL غير مثبتة على السيرفر: " + ", ".join(missing_tools) + ". تحقق من apt.txt ثم أعد النشر."}
    target = None
    dump_path = None
    try:
        target = await asyncpg.connect(DATABASE_URL, timeout=15, ssl="require")
        if await target.fetchval("SELECT to_regclass('transfer_admin.copy_complete') IS NOT NULL"):
            return {"ok": False, "error": "تم النسخ سابقًا؛ أوقفت العملية لمنع استبدال بيانات فرانكفورت."}
        target_tables = await target.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
        if target_tables:
            return {"ok": False, "error": f"قاعدة الوجهة ليست فارغة: عُثر على {target_tables} جدولًا. لم يبدأ النسخ."}
        await target.close()
        target = None
        with tempfile.NamedTemporaryFile(prefix="nawaf-db-", suffix=".dump", delete=False) as tmp:
            dump_path = tmp.name
        env = os.environ.copy()
        env["PGCONNECT_TIMEOUT"] = "20"
        dump = await asyncio.create_subprocess_exec(
            "pg_dump", "--format=custom", "--no-owner", "--no-acl", "--schema=public",
            "--file", dump_path, SOURCE_DATABASE_URL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )
        _, dump_err = await asyncio.wait_for(dump.communicate(), timeout=900)
        if dump.returncode != 0:
            return {"ok": False, "error": "فشل تصدير المصدر. قد يكون الرابط Transaction Pooler؛ نحتاج Direct Connection أو Session Pooler.", "details": dump_err.decode(errors="replace")[-1800:]}
        restore = await asyncio.create_subprocess_exec(
            "pg_restore", "--no-owner", "--no-acl", "--exit-on-error", "--clean", "--if-exists",
            "--dbname", DATABASE_URL, dump_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )
        _, restore_err = await asyncio.wait_for(restore.communicate(), timeout=1800)
        if restore.returncode != 0:
            return {"ok": False, "error": "فشل الاستيراد إلى فرانكفورت. لم يتم اعتماد النقل.", "details": restore_err.decode(errors="replace")[-2500:]}
        source = await asyncpg.connect(SOURCE_DATABASE_URL, timeout=20, ssl="require")
        target = await asyncpg.connect(DATABASE_URL, timeout=20, ssl="require")
        try:
            source_counts, target_counts = await asyncio.gather(_table_counts(source), _table_counts(target))
            if source_counts != target_counts:
                return {"ok": False, "error": "اكتمل الاستيراد لكن لم تتطابق الجداول أو أعداد السجلات.", "source_tables": len(source_counts), "target_tables": len(target_counts)}
            await target.execute("CREATE SCHEMA IF NOT EXISTS transfer_admin")
            await target.execute("""CREATE TABLE transfer_admin.copy_complete (
                completed_at timestamptz NOT NULL DEFAULT now(),
                table_count integer NOT NULL,
                row_count bigint NOT NULL
            )""")
            total_rows = sum(int(v) for v in target_counts.values())
            await target.execute("INSERT INTO transfer_admin.copy_complete(table_count, row_count) VALUES($1, $2)", len(target_counts), total_rows)
            return {"ok": True, "message": f"نجح النسخ والتحقق. عدد الجداول: {len(target_counts)}، مجموع السجلات: {total_rows}. قاعدة سنغافورة لم تتغير.", "table_count": len(target_counts), "row_count": total_rows}
        finally:
            await source.close()
            await target.close()
    except asyncio.TimeoutError:
        return {"ok": False, "error": "انتهت مهلة النسخ؛ لم يتم تأكيد النجاح. راجع السجلات قبل إعادة المحاولة."}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:500]}
    finally:
        if target is not None:
            await target.close()
        if dump_path and os.path.exists(dump_path):
            os.unlink(dump_path)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        print(f"HTTP {self.command} {path}", flush=True)
        if path == "/probe":
            payload = asyncio.run(run_probe())
            tg = payload.get("telegram", {})
            db = payload.get("database", {})
            tg_value = f"{tg['avg_ms']} ms" if tg.get("avg_ms") is not None else "تعذر القياس"
            db_value = f"{db['query_avg_ms']} ms" if db.get("query_avg_ms") is not None else "تعذر القياس"
            connect_value = f"{db['connect_ms']} ms" if db.get("connect_ms") is not None else "—"
            tg_note = tg.get("error") or f"10 طلبات • أقل {tg.get('min_ms', '—')} ms • أعلى {tg.get('max_ms', '—')} ms • HTTP {tg.get('http_status', '—')} • {tg.get('http_version', '—')}"
            db_note = db.get("error") or f"10 استعلامات • أقل {db.get('query_min_ms', '—')} ms • أعلى {db.get('query_max_ms', '—')} ms"
            values = {
                "{{STATUS}}": "اكتمل الاختبار. يتم القياس من السيرفر عند فتح الصفحة.",
                "{{TG_VALUE}}": html.escape(str(tg_value)),
                "{{DB_VALUE}}": html.escape(str(db_value)),
                "{{CONNECT_VALUE}}": html.escape(str(connect_value)),
                "{{TG_NOTE}}": html.escape(str(tg_note)),
                "{{DB_NOTE}}": html.escape(str(db_note)),
                "{{TG_CLASS}}": "ok" if tg.get("ok") else "bad",
                "{{DB_CLASS}}": "ok" if db.get("ok") else "bad",
                "{{CONNECT_CLASS}}": "ok" if db.get("ok") else "bad",
            }
            page = PAGE
            for marker, value in values.items():
                page = page.replace(marker, value)
            body = page.encode("utf-8")
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

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/transfer":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 4096)
            form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
            supplied = form.get("secret", [""])[0]
        except Exception:
            supplied = ""
        expected = TRANSFER_SECRET
        if not expected or not __import__("hmac").compare_digest(supplied, expected):
            result, status = {"ok": False, "error": "مفتاح النسخ غير صحيح أو غير مضبوط."}, 401
        else:
            try:
                result = asyncio.run(transfer_database())
                status = 200 if result.get("ok") else 500
            except Exception as exc:
                result, status = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:500]}, 500
        message = result.get("message") or result.get("error") or "انتهت العملية دون رسالة."
        if result.get("details"):
            message += "\\n" + result["details"]
        page = TRANSFER_RESULT_PAGE.replace("{{CLASS}}", "ok" if result.get("ok") else "bad")
        page = page.replace("{{MESSAGE}}", html.escape(str(message)))
        body = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
