#!/usr/bin/env python3
# Display name: Bangumi
# 显示名称：番剧信息
# Description: Look up Bangumi (bgm.tv): what anime airs today or on a weekday, search anime, books, games and music by name, and read a subject's score, tags, summary, aired progress and episode list.
# 描述：查番组计划（bgm.tv）：今天播什么、某天的放送表，搜动画、书、游戏、音乐，看评分、标签、简介、播到第几集和剧集表。
# Timeout: 60
# Clicall: yes
# Parameters:
# {"type": "object", "properties": {
#   "action": {"type": "string", "enum": ["calendar", "search", "subject", "episodes"], "description": "calendar: the weekly airing schedule. search: find subjects by name. subject: details of one subject, with aired progress for anime. episodes: its episode list. Default: subject when query is given, calendar otherwise."},
#   "query": {"type": "string", "description": "A subject name (Chinese or original title) or a numeric bgm.tv subject id. A name opens the best match and lists the other candidates."},
#   "weekday": {"type": "string", "description": "calendar: today (default), tomorrow, week, mon-sun, 1-7, or 周一-周日 / 一-日."},
#   "type": {"type": "string", "enum": ["anime", "book", "game", "music", "real"], "description": "Subject type for search and name lookups. Default anime."},
#   "limit": {"type": "integer", "description": "calendar: titles per day (default all); search: results (default 8, max 25); episodes: the last N up to the next one to air (default all)."},
#   "format": {"type": "string", "enum": ["md", "json"], "description": "md (default) for reading; json for code, e.g. piping miyu call into jq or python."}
# }}
import datetime as dt
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.bgm.tv"
# Bangumi asks for an identifying User-Agent; anonymous ones get throttled.
UA = "miyu-scripts-bangumi/0.1 (+https://github.com/SHORiN-KiWATA)"
TIMEOUT = 20
TYPES = {"book": 1, "anime": 2, "music": 3, "game": 4, "real": 6}
TYPE_LABEL = {1: "书籍", 2: "动画", 3: "音乐", 4: "游戏", 6: "三次元"}
WEEKDAYS = {
    "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7,
    "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6, "sunday": 7,
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
    "today": 0, "今天": 0, "tomorrow": -1, "明天": -1, "week": -2, "本周": -2, "整周": -2, "全周": -2,
}


class Failed(Exception):
    pass


# ---------------------------------------------------------------- HTTP

def request(path, body=None, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise Failed("Bangumi 上没有这个条目。确认 id，或先用 action=search 查。") from exc
        if exc.code in (403, 429):
            raise Failed(f"Bangumi 拒绝了请求（HTTP {exc.code}），多半是限流，稍后再试。") from exc
        raise Failed(f"Bangumi 接口出错（HTTP {exc.code}），稍后再试。") from exc
    except urllib.error.URLError as exc:
        raise Failed(f"连不上 Bangumi：{exc.reason}。检查网络。") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise Failed(f"Bangumi {TIMEOUT} 秒没有回应，稍后再试。") from exc
    except json.JSONDecodeError as exc:
        raise Failed("Bangumi 返回的不是 JSON（可能在维护），稍后再试。") from exc


def calendar():
    """The weekly schedule changes at most daily, so one copy per day is kept in the cache directory."""
    cache_dir = os.environ.get("MIYU_SCRIPT_CACHE_DIR")
    today = dt.date.today().isoformat()
    path = os.path.join(cache_dir, f"calendar-{today}.json") if cache_dir else None
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
    days = request("/calendar")
    if path:
        try:
            for name in os.listdir(cache_dir):
                if name.startswith("calendar-") and name != os.path.basename(path):
                    os.remove(os.path.join(cache_dir, name))
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(days, fh, ensure_ascii=False)
        except OSError:
            pass
    return days


def search(keyword, subject_type, limit):
    body = {"keyword": keyword, "sort": "match", "filter": {"type": [subject_type]}}
    return request("/v0/search/subjects", body=body, params={"limit": limit}).get("data") or []


def subject(subject_id):
    return request(f"/v0/subjects/{subject_id}")


def episodes(subject_id):
    """Every main episode (type 0); long runs like One Piece go past a thousand, so page until the total."""
    out, offset = [], 0
    while True:
        data = request("/v0/episodes", params={"subject_id": subject_id, "type": 0, "limit": 100, "offset": offset})
        chunk = data.get("data") or []
        out.extend(chunk)
        offset += len(chunk)
        if not chunk or offset >= (data.get("total") or 0) or offset >= 5000:
            return out


def resolve(query, subject_type):
    text = query.strip()
    if text.isdigit():
        return int(text), []
    hits = search(text, subject_type, 6)
    if not hits:
        raise Failed(f"Bangumi 上搜不到「{text}」。换个写法（日文原名、中文译名），或改 type。")
    return hits[0]["id"], hits[1:]


# ---------------------------------------------------------------- helpers

def title(item):
    return item.get("name_cn") or item.get("name") or "?"


def full_title(item):
    name, cn = item.get("name") or "", item.get("name_cn") or ""
    return f"{cn}（{name}）" if cn and name and cn != name else (cn or name or "?")


def score(item):
    rating = item.get("rating") or {}
    return rating.get("score") or 0, rating.get("total") or 0, item.get("rank") or rating.get("rank")


def score_text(item):
    value, votes, _ = score(item)
    return f"{value:.1f}（{votes}人）" if votes else "—"


FEW_VOTES = 50


def rank_key(item):
    value, votes, _ = score(item)
    return votes < FEW_VOTES, -value


def parse_weekday(text):
    key = str(text or "today").strip().lower()
    for prefix in ("星期", "周", "礼拜"):
        if key.startswith(prefix) and len(key) > len(prefix):
            key = key[len(prefix):]
    if key in WEEKDAYS:
        value = WEEKDAYS[key]
    elif key.isdigit() and 1 <= int(key) <= 7:
        value = int(key)
    else:
        raise Failed(f"看不懂的星期「{text}」。写 today、tomorrow、week、mon-sun、1-7 或 周一-周日。")
    today = dt.date.today().isoweekday()
    if value == 0:
        return today
    if value == -1:
        return today % 7 + 1
    return value


def progress(eps):
    today = dt.date.today().isoformat()
    aired = [e for e in eps if e.get("airdate") and e["airdate"] <= today]
    upcoming = [e for e in eps if e.get("airdate") and e["airdate"] > today]
    return (aired[-1] if aired else None), (upcoming[0] if upcoming else None), len(aired)


def ep_brief(ep):
    if not ep:
        return None
    return {"ep": ep.get("ep"), "name": ep.get("name_cn") or ep.get("name") or "", "airdate": ep.get("airdate")}


# ---------------------------------------------------------------- actions

def do_calendar(args, fmt):
    weekday = parse_weekday(args.get("weekday"))
    limit = args.get("limit")
    days = calendar()
    picked = days if weekday == -2 else [d for d in days if d["weekday"]["id"] == weekday]
    if fmt == "json":
        return {"date": dt.date.today().isoformat(), "days": [{
            "weekday": d["weekday"]["cn"],
            "items": [{"id": it["id"], "name": it.get("name"), "name_cn": it.get("name_cn"), "air_date": it.get("air_date"),
                       "score": score(it)[0], "votes": score(it)[1], "rank": score(it)[2]}
                      for it in sorted(d["items"], key=rank_key)[:limit or None]],
        } for d in picked]}
    lines = [f"今天 {dt.date.today().isoformat()}（{'一二三四五六日'[dt.date.today().weekday()]}）"]
    for day in picked:
        items = sorted(day["items"], key=rank_key)
        shown = items[:limit] if limit else items
        lines += ["", f"## {day['weekday']['cn']}（{len(items)} 部，按评分排，评分人数不到 {FEW_VOTES} 的排后面）", ""]
        lines += [f"- {full_title(it)} · {score_text(it)} · 首播 {it.get('air_date') or '—'} · id {it['id']}" for it in shown]
        if len(items) > len(shown):
            lines.append(f"- ……还有 {len(items) - len(shown)} 部（把 limit 调大）")
    return "\n".join(lines)


def do_search(args, fmt, subject_type):
    query = str(args.get("query") or "").strip()
    if not query:
        raise Failed('search 要给 query，例：{"action": "search", "query": "芙莉莲"}')
    limit = args.get("limit") or 8
    hits = search(query, subject_type, max(1, min(limit, 25)))
    if fmt == "json":
        return {"query": query, "results": [{
            "id": it["id"], "name": it.get("name"), "name_cn": it.get("name_cn"), "type": TYPE_LABEL.get(it.get("type")),
            "date": it.get("date"), "eps": it.get("eps"), "score": score(it)[0], "votes": score(it)[1], "rank": score(it)[2],
        } for it in hits]}
    if not hits:
        return f"Bangumi 上搜不到「{query}」。换个写法（日文原名、中文译名），或改 type。"
    lines = [f"搜索「{query}」：{len(hits)} 条", ""]
    for it in hits:
        rank = score(it)[2]
        lines.append(f"- {full_title(it)} · {TYPE_LABEL.get(it.get('type'), '?')} · {it.get('date') or '—'}"
                     f" · {score_text(it)}" + (f" · 排名 {rank}" if rank else "") + f" · id {it['id']}")
    return "\n".join(lines)


def do_subject(args, fmt, subject_type):
    query = str(args.get("query") or "").strip()
    if not query:
        raise Failed('subject 要给 query（名字或 id），例：{"query": "葬送的芙莉莲"}')
    subject_id, others = resolve(query, subject_type)
    info = subject(subject_id)
    eps = episodes(subject_id) if info.get("type") in (2, 6) else []
    latest, upcoming, aired = progress(eps)
    value, votes, rank = score(info)
    tags = [t["name"] for t in (info.get("tags") or [])[:10]]
    summary = (info.get("summary") or "").replace("\r", "").strip()
    if fmt == "json":
        return {"id": info["id"], "name": info.get("name"), "name_cn": info.get("name_cn"),
                "type": TYPE_LABEL.get(info.get("type")), "platform": info.get("platform"), "date": info.get("date"),
                "eps": info.get("eps") or info.get("total_episodes"), "score": value, "votes": votes, "rank": rank,
                "tags": tags, "aired": aired if eps else None, "latest": ep_brief(latest), "next": ep_brief(upcoming),
                "summary": summary, "url": f"https://bgm.tv/subject/{info['id']}",
                "other_matches": [{"id": o["id"], "name": full_title(o)} for o in others]}
    lines = [f"# {full_title(info)}", ""]
    lines.append(f"- 类型：{TYPE_LABEL.get(info.get('type'), '?')}" + (f" · {info['platform']}" if info.get("platform") else ""))
    lines.append(f"- 日期：{info.get('date') or '—'} · 集数：{info.get('eps') or info.get('total_episodes') or '—'}")
    lines.append(f"- 评分：{score_text(info)}" + (f" · 排名 {rank}" if rank else ""))
    if eps:
        text = f"已播 {aired}/{len(eps)}"
        if latest:
            text += f"，最新第 {latest.get('ep')} 集「{latest.get('name_cn') or latest.get('name') or ''}」{latest.get('airdate')}"
        if upcoming:
            text += f"；下一集第 {upcoming.get('ep')} 集 {upcoming.get('airdate')}"
        elif aired == len(eps):
            text += "；已播完"
        lines.append(f"- 进度：{text}")
    if tags:
        lines.append(f"- 标签：{'、'.join(tags)}")
    lines.append(f"- 链接：https://bgm.tv/subject/{info['id']}")
    if summary:
        lines += ["", summary[:1500] + ("……（简介截断）" if len(summary) > 1500 else "")]
    if others:
        lines += ["", "其他匹配：" + "、".join(f"{full_title(o)}（id {o['id']}）" for o in others)]
    return "\n".join(lines)


def do_episodes(args, fmt, subject_type):
    query = str(args.get("query") or "").strip()
    if not query:
        raise Failed('episodes 要给 query（名字或 id），例：{"action": "episodes", "query": "葬送的芙莉莲"}')
    subject_id, _ = resolve(query, subject_type)
    info = subject(subject_id)
    eps = episodes(subject_id)
    limit = args.get("limit")
    today = dt.date.today().isoformat()
    # With a limit, show the window that ends at the next episode to air: that is what people ask about.
    upto = next((i + 1 for i, e in enumerate(eps) if e.get("airdate") and e["airdate"] > today), len(eps))
    start = max(0, upto - limit) if limit else 0
    shown = eps[start:upto] if limit else eps
    if fmt == "json":
        return {"id": info["id"], "name": full_title(info), "total": len(eps), "episodes": [
            {"ep": e.get("ep"), "name": e.get("name"), "name_cn": e.get("name_cn"), "airdate": e.get("airdate"),
             "aired": bool(e.get("airdate") and e["airdate"] <= today)} for e in shown]}
    if not eps:
        return f"{full_title(info)} 在 Bangumi 上没有剧集表。"
    lines = [f"{full_title(info)}：共 {len(eps)} 集（今天 {today}）", "", "| 集 | 标题 | 播出 |", "| ---: | --- | --- |"]
    if start:
        lines.append(f"| … | 前面还有 {start} 集 | |")
    for e in shown:
        mark = "" if e.get("airdate") and e["airdate"] <= today else "（未播）"
        lines.append(f"| {e.get('ep')} | {e.get('name_cn') or e.get('name') or ''} | {e.get('airdate') or '—'}{mark} |")
    if len(eps) > start + len(shown):
        lines.append(f"| … | 后面还有 {len(eps) - start - len(shown)} 集 | |")
    return "\n".join(lines)


def run(args):
    if not isinstance(args, dict):
        raise Failed('参数要是一个 JSON 对象，例：{"weekday": "today"}')
    fmt = args.get("format") or "md"
    if fmt not in ("md", "json"):
        raise Failed("format 只能是 md 或 json。")
    type_name = args.get("type") or "anime"
    if type_name not in TYPES:
        raise Failed("type 只能是 anime、book、game、music、real。")
    limit = args.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise Failed("limit 要是正整数。")
    action = args.get("action") or ("subject" if str(args.get("query") or "").strip() else "calendar")
    if action == "calendar":
        return do_calendar(args, fmt)
    if action == "search":
        return do_search(args, fmt, TYPES[type_name])
    if action == "subject":
        return do_subject(args, fmt, TYPES[type_name])
    if action == "episodes":
        return do_episodes(args, fmt, TYPES[type_name])
    raise Failed("action 只能是 calendar、search、subject、episodes。")


def main():
    try:
        args = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"错误：参数不是 JSON：{exc}")
        sys.exit(1)
    try:
        result = run(args)
    except Failed as exc:
        print(f"错误：{exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - the caller wants a reason, not a traceback
        print(f"错误：{type(exc).__name__}: {exc}")
        sys.exit(1)
    print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
