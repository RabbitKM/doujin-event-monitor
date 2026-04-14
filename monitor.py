"""
開拓動漫祭 社團報名監控腳本
自動偵測官網報名時間是否公告，並發送 Discord 通知
"""

import re
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
from pathlib import Path

# ── 設定 ──────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.environ.get("FF_DISCORD_WEBHOOK", "")

TARGET_URL       = "https://www.f-2.com.tw/%e6%b4%bb%e5%8b%95%e5%a0%b4%e5%9c%b0%e4%ba%a4%e9%80%9a%e8%b3%87%e8%a8%8a/"
ANNOUNCEMENT_URL = "https://www.f-2.com.tw/%e7%a4%be%e5%9c%98%e7%9b%b8%e9%97%9c%e5%85%ac%e5%91%8a/"

STATE_FILE = Path(__file__).parent / "state.json"

SHOW_ENDED = False  # 改為 True 可顯示已結束場次

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
# ──────────────────────────────────────────────────────


def fetch_page():
    resp = requests.get(TARGET_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def format_event_date(date_str):
    """將 '2026年 5月 16日（六）' 壓縮為 '5/16（六）'"""
    m = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[（(]([^）)]+)', date_str)
    if m:
        return f"{int(m.group(1))}/{int(m.group(2))}（{m.group(3)}）"
    return ""


def parse_events(html):
    """解析頁面，自動偵測所有場次的報名資訊（含活動日期範圍）"""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.get_text(separator="\n")
    lines = [l.strip() for l in content.splitlines() if l.strip()]

    results = {}
    current_event = None
    collecting_dates = False
    first_date = ""
    last_date = ""

    for line in lines:
        # 自動偵測任何 XXnn / XXXnn 場次標題，例如 ✦FF47 活動資訊✦、✦FFK18 活動資訊✦
        match = re.search(r'\b([A-Z]{2,3}\d+)\b', line)
        if match and "活動資訊" in line:
            current_event = match.group(1)
            collecting_dates = False
            first_date = ""
            last_date = ""
            if current_event not in results:
                results[current_event] = {
                    "status": "pending",
                    "reg_start": "待公佈",
                    "reg_end": "待公佈",
                    "event_date": "",
                    "ended": False,
                }
            continue

        if not current_event:
            continue

        if "已結束" in line:
            results[current_event]["ended"] = True

        # 偵測活動日期區塊開始
        if "◆活動日期" in line:
            collecting_dates = True
            d = format_event_date(line)
            if d:
                first_date = d
                last_date = d
            continue

        # 收集後續日期行（直到遇到下一個 ◆ 項目）
        if collecting_dates:
            if line.startswith("◆"):
                collecting_dates = False
                if first_date:
                    results[current_event]["event_date"] = (
                        first_date if first_date == last_date
                        else f"{first_date} ～ {last_date}"
                    )
            else:
                d = format_event_date(line)
                if d:
                    if not first_date:
                        first_date = d
                    last_date = d

        if "開始接受報名" in line:
            collecting_dates = False
            if first_date:
                results[current_event]["event_date"] = (
                    first_date if first_date == last_date
                    else f"{first_date} ～ {last_date}"
                )
            if "待公佈" in line:
                results[current_event]["status"] = "pending"
                results[current_event]["reg_start"] = "待公佈"
            else:
                results[current_event]["status"] = "open"
                text = re.sub(r'^開始接受報名[：:]\s*', '', line).strip()
                results[current_event]["reg_start"] = text

        if "報名截止" in line:
            m = re.search(r'報名截止(?:與報名費匯款截止)?[：:]\s*(.+)', line)
            if m:
                results[current_event]["reg_end"] = m.group(1).strip()

    return results


def is_date_passed(date_str):
    """判斷中文日期字串（如 '2026 年 3 月 2 日'）是否已過期"""
    m = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', date_str)
    if m:
        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        return d < datetime.now().date()
    return False


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_discord(event_name, reg_start, reg_end="待公佈"):
    """發送 Discord Webhook 通知（報名時間公告）"""
    if not DISCORD_WEBHOOK_URL:
        print("[警告] 未設定 DISCORD_WEBHOOK_URL，跳過通知")
        return

    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")

    payload = {
        "username": "開拓動漫祭 報名小助手",
        "avatar_url": "https://www.f-2.com.tw/wp-content/uploads/2025/03/FF_Logo.png",
        "embeds": [
            {
                "title": f"🎉 開拓動漫祭 · {event_name} 報名時間公告！",
                "description": (
                    f"**{event_name}** 的社團報名資訊已更新，快去確認！\n\n"
                    f"📅 **報名開始**：{reg_start}\n"
                    f"⏰ **報名截止**：{reg_end}\n\n"
                    f"[➡️ 前往官網確認]({TARGET_URL})\n"
                    f"[📝 前往報名系統](https://circle.f-2.com.tw/login)"
                ),
                "color": 0x7F77DD,
                "footer": {"text": f"偵測時間：{now_str}"},
            }
        ],
    }

    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    if resp.status_code in (200, 204):
        print(f"[OK] Discord 通知已發送：{event_name}")
    else:
        print(f"[錯誤] Discord 通知失敗：{resp.status_code} {resp.text}")


def fetch_announcements(html: str) -> list:
    """
    解析社團相關公告頁，回傳含「社團報名開始」的文章列表。
    每筆格式：{"title": "...", "date": "YYYY-MM-DD", "url": "..."}
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for div in soup.find_all("div", class_="post-preview"):
        h2 = div.find("h2", class_="title")
        if not h2:
            continue
        a = h2.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        if "社團報名開始" not in title:
            continue
        url = a["href"]
        # 日期：div.submitted 內的文字，格式「發表於 YYYY-MM-DD HH:MM」
        submitted = div.find("div", class_="submitted")
        date_str = ""
        if submitted:
            m = re.search(r'(\d{4}-\d{2}-\d{2})', submitted.get_text())
            if m:
                date_str = m.group(1)
        results.append({"title": title, "date": date_str, "url": url})
    return results


def send_discord_announcement(title: str, date: str, url: str):
    """📣 公告頁新公告通知（非靜音）"""
    if not DISCORD_WEBHOOK_URL:
        print("[警告] 未設定 DISCORD_WEBHOOK_URL，跳過通知")
        return

    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    payload = {
        "username": "開拓動漫祭 報名小助手",
        "avatar_url": "https://www.f-2.com.tw/wp-content/uploads/2025/03/FF_Logo.png",
        "embeds": [
            {
                "title": "📣 開拓動漫祭 · 社團公告",
                "description": (
                    f"**{title}**\n\n"
                    f"📅 **公告日期**：{date}\n\n"
                    f"[➡️ 查看公告]({url})"
                ),
                "color": 0xE67E22,
                "footer": {"text": f"偵測時間：{now_str}"},
            }
        ],
    }
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    if resp.status_code in (200, 204):
        print(f"[OK] 公告通知已發送：{title}")
    else:
        print(f"[錯誤] 公告通知失敗：{resp.status_code} {resp.text}")


def send_discord_heartbeat(checked_events):
    """每天執行一次，發送「確認運作中」的靜音通知"""
    if not DISCORD_WEBHOOK_URL:
        return

    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")

    # 依 SHOW_ENDED 決定是否過濾已結束場次
    if not SHOW_ENDED:
        checked_events = {k: v for k, v in checked_events.items() if not v.get("ended")}

    # FF(0) → PF(1) → 其他(2)，各組內由大到小
    def sort_key(name):
        m = re.match(r'([A-Z]+)(\d+)', name)
        if m:
            order = {"FF": 0, "PF": 1}.get(m.group(1), 2)
            return (order, -int(m.group(2)))
        return (3, 0)

    sorted_events = sorted(checked_events.keys(), key=sort_key)

    ff_lines = []
    pf_lines = []
    other_lines = []

    for event in sorted_events:
        info = checked_events[event]
        ended_tag = " ~~已結束~~" if info.get("ended") else ""

        if info["status"] == "pending":
            reg_start = "⏳ 待公佈"
            reg_end_display = "⏳ 待公佈"
        else:
            reg_start = info.get("reg_start", "—")
            reg_end_raw = info.get("reg_end", "—")
            if reg_end_raw != "待公佈" and is_date_passed(reg_end_raw) and not info.get("ended"):
                reg_end_display = f"⚠️ **{reg_end_raw}（報名已截止）**"
            else:
                reg_end_display = reg_end_raw

        event_date = info.get("event_date", "")
        date_line = f"\n　活動日期：{event_date}" if event_date else ""
        line = f"**{event}**{ended_tag}{date_line}\n　報名開始：{reg_start}\n　報名截止：{reg_end_display}"

        if re.match(r'^FF\d+$', event):
            ff_lines.append(line)
        elif re.match(r'^PF\d+$', event):
            pf_lines.append(line)
        else:
            other_lines.append(line)

    fields = []
    if ff_lines:
        fields.append({"name": "── FF ──", "value": "\n\n".join(ff_lines), "inline": False})
    if pf_lines:
        fields.append({"name": "── PF ──", "value": "\n\n".join(pf_lines), "inline": False})
    if other_lines:
        fields.append({"name": "── 其他 ──", "value": "\n\n".join(other_lines), "inline": False})

    payload = {
        "username": "開拓動漫祭 報名小助手",
        "avatar_url": "https://www.f-2.com.tw/wp-content/uploads/2025/03/FF_Logo.png",
        "flags": 4096,
        "embeds": [
            {
                "title": "📋 開拓動漫祭 · 每日確認",
                "description": (
                    f"[➡️ 前往官網確認]({TARGET_URL})　"
                    f"[📝 前往報名系統](https://circle.f-2.com.tw/login)"
                ),
                "fields": fields,
                "color": 0x888780,
                "footer": {"text": f"確認時間：{now_str}"},
            }
        ],
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)


def main():
    print(f"[{datetime.now().strftime('%Y/%m/%d %H:%M:%S')}] 開始檢查...")

    try:
        html = fetch_page()
    except Exception as e:
        print(f"[錯誤] 無法抓取頁面：{e}")
        return

    current = parse_events(html)
    previous = load_state()

    print(f"解析結果：{current}")

    # 每日心跳通知（可以把這行註解掉，如果不想每天收到確認訊息）
    send_discord_heartbeat(current)

    for event, info in current.items():
        prev = previous.get(event, {})

        # 狀態從「待公佈」變成有實際日期 → 發通知！
        if prev.get("status") == "pending" and info["status"] == "open":
            print(f"[新公告] {event}：{info['reg_start']}")
            send_discord(event, info["reg_start"], info.get("reg_end", "待公佈"))

        # 第一次執行、還沒有紀錄 → 靜默記錄，不發通知
        elif event not in previous:
            print(f"[首次記錄] {event}：{info['reg_start']}")

    # 偵測公告頁新公告
    try:
        ann_resp = requests.get(ANNOUNCEMENT_URL, headers=HEADERS, timeout=15)
        ann_resp.encoding = "utf-8"
        new_anns = fetch_announcements(ann_resp.text)
        seen_urls = previous.get("seen_announcement_urls", [])
        for ann in new_anns:
            if ann["url"] not in seen_urls:
                print(f"[新公告] {ann['title']}（{ann['date']}）")
                send_discord_announcement(ann["title"], ann["date"], ann["url"])
                seen_urls.append(ann["url"])
        previous["seen_announcement_urls"] = seen_urls
    except Exception as e:
        print(f"[錯誤] 無法抓取公告頁：{e}")

    # 更新 state
    previous.update(current)
    save_state(previous)

    print("完成。")


if __name__ == "__main__":
    main()
