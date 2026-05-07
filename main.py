import os
import re
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse

SEEN_FILE = "seen_jobs.json"
FIRST_RUN_MARK_ONLY = True

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SITES = [
    {
        "name": "OJAS Gujarat",
        "url": "https://ojas.gujarat.gov.in/AdvtList.aspx?type=lCxUjNjnTp8%3D",
        "base": "https://ojas.gujarat.gov.in/",
    },
    {
        "name": "GSSSB Gujarat",
        "url": "https://gsssb.gujarat.gov.in/",
        "base": "https://gsssb.gujarat.gov.in/",
    },
    {
        "name": "GPSC Advertisement",
        "url": "https://gpsc.gujarat.gov.in/dashboard?stage=Advertisement",
        "base": "https://gpsc.gujarat.gov.in/",
    },
    {
        "name": "GPSC Recruitment Open",
        "url": "https://gpsc.gujarat.gov.in/RecruitmentOpen",
        "base": "https://gpsc.gujarat.gov.in/",
    },
]

DIVYANG_KEYWORDS = [
    "divyang", "દિવ્યાંગ", "viklang", "વિકલાંગ",
    "pwd", "disability", "disabled", "benchmark disability",
    "special recruitment", "physically handicapped", "ph candidate",
    "persons with disabilities", "person with disability"
]

BCA_GOOD_KEYWORDS = [
    "computer", "data entry", "operator", "it", "mis", "programmer",
    "clerk", "senior clerk", "junior clerk", "assistant",
    "office assistant", "accounts", "admin", "class-3", "class 3",
    "graduate", "bca", "bachelor"
]

BAD_JOB_KEYWORDS = [
    "police", "constable", "fireman", "forest guard",
    "physical test", "running", "height", "chest", "driver"
]

BAD_TEXT_KEYWORDS = [
    "home", "contact", "about", "login", "download", "result",
    "answer key", "call letter", "exam date", "syllabus only"
]


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, ensure_ascii=False, indent=2)


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text):
    text = clean_text(text).lower()
    text = re.sub(r"[^a-z0-9અ-હઁ-૿₹/%\- ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_link(link):
    try:
        parsed = urlparse(link)
        clean = parsed._replace(query="", fragment="")
        return urlunparse(clean).lower().rstrip("/")
    except:
        return link.lower().split("?")[0].split("#")[0].rstrip("/")


def make_id(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def job_unique_id(item):
    title = normalize_text(item.get("title", ""))
    details = normalize_text(item.get("details", ""))
    link = normalize_link(item.get("link", ""))
    combined = title + " " + details

    return make_id(
        item["source"].lower().strip()
        + "|"
        + link
        + "|"
        + combined[:350]
    )


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram token/chat id missing")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": False
    }

    try:
        r = requests.post(url, data=data, timeout=20)
        if r.status_code == 200:
            print("Telegram message sent ✅")
            return True
        print("Telegram error:", r.text)
        return False
    except Exception as e:
        print("Telegram send failed:", e)
        return False


def fetch_page(url):
    headers = {"User-Agent": "Mozilla/5.0 JobAlertBot"}
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print("Fetch failed:", url, e)
        return ""


def has_any(text, keywords):
    text = normalize_text(text)
    return any(normalize_text(k) in text for k in keywords)


def is_relevant_for_you(text):
    text_norm = normalize_text(text)

    if len(text_norm) < 15:
        return False

    if has_any(text_norm, BAD_TEXT_KEYWORDS):
        return False

    if has_any(text_norm, BAD_JOB_KEYWORDS):
        return False

    has_divyang = has_any(text_norm, DIVYANG_KEYWORDS)
    has_bca_job = has_any(text_norm, BCA_GOOD_KEYWORDS)

    if has_divyang and has_bca_job:
        return True

    if has_divyang:
        return True

    return False


def analyze_for_bca_fresher(text):
    text_low = normalize_text(text)

    score = 0
    reasons = []
    work = "Office/computer related kaam ho sakta hai."
    salary = "Official PDF me salary confirm karni hogi."

    if has_any(text_low, ["computer", "data entry", "operator", "it", "mis", "programmer"]):
        score += 3
        reasons.append("BCA/IT background ke liye suitable lag raha hai.")
        work = "Computer work, data entry, software handling, MIS, record management ya office system work."
        salary = "Approx ₹15,000–₹30,000/month ya official pay scale ke hisab se."

    if has_any(text_low, ["clerk", "assistant", "office assistant", "junior clerk", "senior clerk"]):
        score += 2
        reasons.append("Graduate/BCA fresher ke liye achhi office post ho sakti hai.")
        work = "Office files, documents, typing, data entry, records aur computer work."
        salary = "Class-3 me approx ₹19,900–₹63,200 ya post ke hisab se alag pay scale ho sakta hai."

    if has_any(text_low, ["graduate", "bca", "bachelor"]):
        score += 2
        reasons.append("Graduation/BCA eligibility match ho sakti hai.")

    if has_any(text_low, DIVYANG_KEYWORDS):
        score += 3
        reasons.append("Divyang/PwD related notice lag raha hai.")

    if score >= 6:
        suitability = "✅ HIGH priority for BCA Fresher"
    elif score >= 3:
        suitability = "🟡 Medium priority for BCA Fresher"
    else:
        suitability = "⚠️ Official PDF check required"

    if not reasons:
        reasons.append("Exact eligibility official PDF me check karni hogi.")

    return suitability, work, salary, reasons


def extract_items(site):
    html = fetch_page(site["url"])
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = []

    for a in soup.find_all("a"):
        title = clean_text(a.get_text(" ", strip=True))
        href = a.get("href")

        if not title or len(title) < 5:
            continue

        link = urljoin(site["base"], href) if href else site["url"]

        parent = a.find_parent(["tr", "li", "div", "td"])
        details = title

        if parent:
            details = clean_text(parent.get_text(" ", strip=True))

        full_text = title + " " + details

        if is_relevant_for_you(full_text):
            items.append({
                "source": site["name"],
                "title": title[:160],
                "details": details[:800],
                "link": link,
            })

    for tr in soup.find_all("tr"):
        row_text = clean_text(tr.get_text(" ", strip=True))

        if len(row_text) < 10:
            continue

        link = site["url"]
        a = tr.find("a")

        if a and a.get("href"):
            link = urljoin(site["base"], a.get("href"))

        if is_relevant_for_you(row_text):
            items.append({
                "source": site["name"],
                "title": row_text[:160],
                "details": row_text[:800],
                "link": link,
            })

    unique = {}

    for item in items:
        uid = job_unique_id(item)
        if uid not in unique:
            unique[uid] = item

    return list(unique.values())


def check_all_sites():
    first_run = not os.path.exists(SEEN_FILE)
    seen = load_seen()
    session_sent = set()

    new_count = 0
    marked_count = 0

    for site in SITES:
        print("Checking:", site["name"])
        items = extract_items(site)

        for item in items:
            unique_id = job_unique_id(item)

            if unique_id in seen or unique_id in session_sent:
                continue

            session_sent.add(unique_id)
            seen.add(unique_id)
            save_seen(seen)

            if first_run and FIRST_RUN_MARK_ONLY:
                marked_count += 1
                print("Marked old job, not sent:", item["title"])
                continue

            suitability, work, salary, reasons = analyze_for_bca_fresher(item["details"])
            reason_text = "\n".join(f"• {r}" for r in reasons)

            msg = f"""🚨 New Divyang/PwD Govt Job Alert

🏛 Source:
{item['source']}

📌 Notice:
{item['title']}

🎯 BCA Fresher Match:
{suitability}

💼 Kaam kya ho sakta hai:
{work}

💰 Salary Approx:
{salary}

✅ Tumhare liye reason:
{reason_text}

📝 Details:
{item['details']}

🔗 Link:
{item['link']}

⚠️ Official PDF me qualification, last date, age limit, salary aur Divyang reservation confirm kar lena.
"""

            if send_telegram(msg):
                new_count += 1

    print("Done")
    print("New alerts sent:", new_count)
    print("Old jobs marked only:", marked_count)


if __name__ == "__main__":
    check_all_sites()