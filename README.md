# agent-activity-map

A live map of what an agent session did, not a log — as a stdlib-only Python CLI. No network, no keys, no screenshots: any agent harness that can dump its calls as a JSONL session log feeds this CLI, and it answers *where the work went*.

**Pattern** (original code; pattern only, learned from today's radar): alexeyw/lot-map draws a live map beside the chat — every tool call, model step, hook, skill and subagent lights up as a pulse on a station ring; worn spokes show where the work went; the context window is a ring that fills as the session goes; errors leave a red dot; the same board renders in braille for plain terminals. This tool is that idea as a small local CLI for any session log: the ring is the map, `summarize` is the ledger, `check` is the quality gate.

## The map

Ten stations on a ring, in order: `you · model · memory · files · shell · network · browser · agents · skills · hooks`. Each call lights its station; a spoke grows thicker the more the station is used (`.` once, `:` a few times, `=` heavily worn); the route is the last stations in order; an error station is marked `@` with its count; the centre shows the context fill, amber at 70%, red at 90%.

## An event

One JSON object per line. Only station names are read — never call arguments, file contents, or prompts.

```json
{"ts": "2026-11-15T10:00:01Z", "station": "files", "call": "Read", "duration_ms": 120, "status": "ok"}
```

Optional keys: `"subagent"` (which subagent made the call), `"context_pct"` (context-window fill, 0–100), `"model"` (model in use). `"status"` is `ok`, `error` or `refused`.

## Usage

```bash
# a deterministic sample session, so the tool works out of the box
python3 -m agent_activity_map demo --events 40 --seed 7 --out examples/demo-session.jsonl

python3 -m agent_activity_map map examples/demo-session.jsonl
#                               O YOUx3
#                               :
#         HOKx2  O              :              O MDLx8
#                 ::            :            ==
#                   ::          :          ==
#                     ::        :        ==
#                       ::      :      ==
#      O:SKLx3            ::    :    ==           MEMx3::O
#           ::::::::        ::  :  ==        ::::::::
#                   ::::::::  :::==  ::::::::
#                           ::74.4%::
#                   ::::::::  :::==  ========
#           ::::::::        ::  :  ==        ========
#      O:AGTx3            ::    :    ==         FILx8!2==@
#                       ::      :      ==
#                     ::        :        ==
#                   ::          :          ==
#                 ::            :            ==
#         BRWx2  O              :              O SHLx5
#                               :
#                               O NETx3
# route: ... -> hooks -> model -> browser -> you -> model -> memory -> files -> shell -> model -> network -> agents -> skills
# errors: files!2
# subagents: reviewer
# models: opus -> sonnet
# context: [###############-----] 74.4% amber
# legend: o unused · O used · @ errors · . : = worn spokes · context amber >=70, red >=90

python3 -m agent_activity_map summarize examples/demo-session.jsonl
# {"calls": 40, "errors": 2, "error_rate": 0.05, "total_ms": 18473,
#  "per_station": {"files": {"calls": 8, "errors": 2, "refusals": 1, "ms": 1111}, ...},
#  "busiest_station": "files", "route": [...], "context_peak": 74.4,
#  "models": ["opus", "sonnet"], "subagents": ["reviewer"]}

python3 -m agent_activity_map check examples/demo-session.jsonl
# FAIL: files: 1 refused call(s) left standing
# FAIL: shell: 1 refused call(s) left standing
# ... (exit 1)
```

`check` is the CI gate: it fails on an error rate above `--max-error-rate` (default 5%), a context peak above `--max-context` (default 90%), or any refused call left standing. A clean session prints `clean: ...` and exits 0.

Exit codes: `0` ok / clean · `1` bad input or check findings.

## Tests

```bash
python3 -m unittest discover -s tests
# 28 tests, all passing
```

---

# agent-activity-map

نقشه‌ی زنده‌ی کاری که یک نشست ایجنت انجام داده، نه یک لاگ — با یک CLI فقط-stdlib پایتون. بدون شبکه، بدون کلید، بدون اسکرین‌شات: هر هارنس ایجنتی که بتواند فراخوانی‌هایش را به‌صورت لاگ JSONL بدهد، به این CLI می‌دهد و جواب می‌گیرد که *کار کجا رفته است*.

**الگو** (کد اورجینال؛ فقط الگو، از رادار امروز): alexeyw/lot-map کنار چت یک نقشه‌ی زنده می‌کشد — هر فراخوانی ابزار، قدم مدل، هوک، اسکیل و ساب‌ایجنت به‌صورت پالس روی یک حلقه‌ی ایستگاه روشن می‌شود؛ پره‌های فرسوده نشان می‌دهند کار کجا رفته؛ پنجره‌ی کانتکست حلقه‌ای است که با پیشرفت نشست پر می‌شود؛ خطاها یک نقطه‌ی قرمز می‌گذارند؛ همان تخته در ترمینال‌های ساده با نقطه‌های بریل هم رندر می‌شود. این ابزار همان ایده است به‌صورت یک CLI کوچک محلی برای هر لاگ نشست: حلقه نقشه است، `summarize` دفتر کل است، `check` دروازه‌ی کیفیت است.

## نقشه

ده ایستگاه روی یک حلقه، به ترتیب: `you · model · memory · files · shell · network · browser · agents · skills · hooks`. هر فراخوانی ایستگاهش را روشن می‌کند؛ پره با استفاده‌ی بیشتر ضخیم‌تر می‌شود (`.` یک بار، `:` چند بار، `=` خیلی پراستفاده)؛ مسیر، آخرین ایستگاه‌ها به ترتیب است؛ ایستگاه خطادار با `@` و تعدادش علامت می‌خورد؛ مرکز، پرشدگی کانتکست را نشان می‌دهد، کهربایی در ۷۰٪ و قرمز در ۹۰٪.

## یک رویداد

یک آبجکت JSON در هر خط. فقط نام ایستگاه‌ها خوانده می‌شود — هرگز آرگومان فراخوانی، محتوای فایل یا پرامپت.

```json
{"ts": "2026-11-15T10:00:01Z", "station": "files", "call": "Read", "duration_ms": 120, "status": "ok"}
```

کلیدهای اختیاری: `"subagent"` (کدام ساب‌ایجنت فراخوانی را زده)، `"context_pct"` (پرشدگی پنجره‌ی کانتکست، ۰ تا ۱۰۰)، `"model"` (مدل در حال استفاده). `"status"` یکی از `ok` ،`error` یا `refused` است.

## استفاده

```bash
# یک نشست نمونه‌ی قطعی، تا ابزار همان اول کار کند
python3 -m agent_activity_map demo --events 40 --seed 7 --out examples/demo-session.jsonl

python3 -m agent_activity_map map examples/demo-session.jsonl
python3 -m agent_activity_map summarize examples/demo-session.jsonl
python3 -m agent_activity_map check examples/demo-session.jsonl
# FAIL: files: 1 refused call(s) left standing
# ... (exit 1)
```

`check` دروازه‌ی CI است: اگر نرخ خطا بالاتر از `--max-error-rate` (پیش‌فرض ۵٪) باشد، یا اوج کانتکست بالاتر از `--max-context` (پیش‌فرض ۹۰٪)، یا هر فراخوانیِ ردشده‌ای بی‌پاسخ مانده باشد، شکست می‌خورد. نشست تمیز `clean: ...` چاپ می‌کند و با کد ۰ خارج می‌شود.

کدهای خروج: `0` موفق / تمیز · `1` ورودی بد یا یافته‌های check.

## تست‌ها

```bash
python3 -m unittest discover -s tests
# 28 tests, all passing
```
