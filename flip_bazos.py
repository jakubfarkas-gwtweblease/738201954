import requests
import json
import os
import re
import time
import datetime
import unicodedata
from bs4 import BeautifulSoup

# ─────────────────────────── KONFIG ───────────────────────────
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
EXTRA_CHAT_IDS = os.environ.get("EXTRA_CHAT_IDS", "")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36"}
SEEN_FILE = "seen_ads.json"
PSC = "81105"
OKRUH = "15"

PRICE_MIN = 0
PRICE_MAX = 40          # do 40 €
MISS_LIMIT = 3          # 3x nevidno inzerat -> vymaze sa zo seen
ONLY_TODAY = False      # viz vysvetlenie; True = posielaj len dnes pridane (krehke, vylad podla logu)

# Co hladame na bazose (dotazy do vyhladavania)
SEARCH_QUERIES = [
    "iphone",
    "ipad",
    "macbook",
    "imac",
    "mac mini",
    "apple watch",
    "bicykel",
    "bike",
]

# POZITIVNY filter: nazov MUSI obsahovat aspon jedno z tychto (uz bez diakritiky)
PRODUCT_WORDS = [
    "iphone", "ajfon", "ifon",
    "ipad",
    "macbook", "mac book",
    "imac", "mac mini", "mac studio",
    "apple watch", "applewatch", "iwatch",
    "bicykel", "bicykle", "bike", "mtb", "bmx", "ebike", "e-bike",
]

# PRISLUSENSTVO: ak je nejake z tychto slov PRED produktovym slovom -> je to prislusenstvo, prec
ACCESSORY_WORDS = [
    "obal", "kryt", "puzdro", "case", "sklo", "folia", "ochranne",
    "kabel", "nabijacka", "charger", "adapter", "dock",
    "stojan", "drziak", "drzak", "taska", "kosik", "nosic",
    "blatnik", "sedlo", "pedal", "retaz",
    "prilba", "helma", "pumpa", "svetlo", "svetla", "zamok",
    "sluchadla", "remienok", "naramok", "pasik", "klucenka",
]

# TVRDY blok: vzdy prec, bez ohladu na poziciu
HARD_BLOCK = [
    "replika", "repliky", "napodobenina", "kopia", "fake", "icloud",
]


# ─────────────────────────── POMOCNE ───────────────────────────
def norm(s):
    """Mala pismena, bez diakritiky -> spolahlive porovnavanie."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def load_seen():
    """Vrati dict {url: miss_count}. Zvlada aj stary format (list)."""
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {u: 0 for u in data}
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"Chyba pri citani {SEEN_FILE}: {e}")
    return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False)


def get_all_chat_ids():
    ids = []
    if CHAT_ID:
        ids.append(CHAT_ID)
    if EXTRA_CHAT_IDS:
        for cid in EXTRA_CHAT_IDS.split(","):
            cid = cid.strip()
            if cid and cid not in ids:
                ids.append(cid)
    return ids


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for cid in get_all_chat_ids():
        try:
            requests.post(url, data={"chat_id": cid, "text": msg}, timeout=10)
        except Exception as e:
            print(f"Telegram chyba ({cid}): {e}")


# ─────────────────────────── FILTRE ───────────────────────────
def classify(title):
    """keep / block_hard / no_product / accessory"""
    t = norm(title)

    for w in HARD_BLOCK:
        if w in t:
            return "block_hard"

    prod_hits = [t.find(w) for w in PRODUCT_WORDS if w in t]
    if not prod_hits:
        return "no_product"
    prod_idx = min(prod_hits)

    acc_hits = [t.find(w) for w in ACCESSORY_WORDS if w in t]
    if acc_hits and min(acc_hits) < prod_idx:
        return "accessory"   # prislusenstvo "X na iphone" -> preZ

    return "keep"


def parse_price(price_text):
    """Vrati (je_v_rozsahu, zobrazena_cena)."""
    raw = (price_text or "").strip()
    p = norm(raw)
    if any(x in p for x in ["zadarmo", "zdarma", "darujem"]):
        return True, "Zadarmo"
    nums = re.findall(r"\d+", p.replace(" ", "").replace("\xa0", ""))
    if not nums:
        # Dohodou / V texte -> server uz filtroval do 40, nechaj prejst
        return True, raw or "?"
    val = int(nums[0])
    return (PRICE_MIN <= val <= PRICE_MAX), raw


def is_today(date_text):
    if not ONLY_TODAY:
        return True
    t = norm(date_text)
    if "dnes" in t:
        return True
    today = datetime.date.today()
    cand = f"{today.day}.{today.month}."
    if cand in t.replace(" ", ""):
        return True
    # fail-open len ak je datum prazdny (radsej ping navyse nez zmeskany flip)
    return t.strip() == ""


def get_description(ad):
    el = (ad.select_one(".popis") or ad.select_one(".inzeratypopis")
          or ad.select_one("div.maincontent p"))
    if el:
        txt = el.get_text(strip=True)
        return txt[:200] + "..." if len(txt) > 200 else txt
    return ""


# ─────────────────────────── HLAVNY BEH ───────────────────────────
def check():
    seen = load_seen()
    first_run = len(seen) == 0
    found_now = set()
    new_ads = []   # (title, price, date, desc, link)
    debug_dates = 0

    for query in SEARCH_QUERIES:
        print(f"Skenujem: {query}")
        try:
            url = (
                f"https://www.bazos.sk/search.php"
                f"?hledat={requests.utils.quote(query)}"
                f"&rubriky=www"
                f"&hlokalita={PSC}"
                f"&humkreis={OKRUH}"
                f"&cenaod={PRICE_MIN}"
                f"&cenado={PRICE_MAX}"
                f"&Submit=H%C4%BEada%C5%A5"
            )
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")

            ads = soup.select(".inzeraty") or soup.find_all(
                "div", class_=lambda c: c and "inzerat" in c.split())

            for ad in ads:
                try:
                    title_el = ad.select_one("h2 a") or ad.select_one(".nadpis")
                    if not title_el:
                        continue
                    title = title_el.text.strip()
                    href = title_el.get("href", "")
                    if not href:
                        continue
                    link = href if href.startswith("http") else "https://www.bazos.sk" + href

                    cls = classify(title)
                    if cls != "keep":
                        continue

                    price_el = ad.select_one(".inzeratycena") or ad.select_one(".cena")
                    price_text = price_el.text.strip() if price_el else ""
                    ok, price_disp = parse_price(price_text)
                    if not ok:
                        continue

                    date_el = ad.select_one(".velikost10") or ad.select_one(".datum")
                    date = date_el.text.strip() if date_el else "?"
                    if ONLY_TODAY and debug_dates < 5:
                        print(f"  DEBUG datum: '{date}'")
                        debug_dates += 1
                    if not is_today(date):
                        continue

                    found_now.add(link)
                    if link not in seen:
                        new_ads.append((title, price_disp, date, get_description(ad), link))
                    seen[link] = 0   # zive -> vynuluj miss

                except Exception as e:
                    print(f"Chyba pri inzerate: {e}")
                    continue

        except Exception as e:
            print(f"Chyba pri dotaze '{query}': {e}")

        time.sleep(2)

    # PRUNING: co sme tento beh nevideli -> +1 miss; po MISS_LIMIT prec
    for url in list(seen):
        if url not in found_now:
            seen[url] = seen.get(url, 0) + 1
            if seen[url] >= MISS_LIMIT:
                del seen[url]

    # NOTIFIKACIE
    if first_run:
        send_telegram(
            f"FLIP da Bazos spusteny.\n"
            f"Sledujem {len(found_now)} inzeratov do {PRICE_MAX} EUR.\n"
            f"Odteraz ti pingnem len kazdy novy."
        )
        print(f"Prvy beh: ulozenych {len(found_now)} inzeratov (bez spamu).")
    else:
        for title, price, date, desc, link in new_ads:
            msg = f"NOVY FLIP - BAZOS\n\n{title}\n"
            if desc:
                msg += f"{desc}\n"
            msg += f"\nCena\n{price}\n\nDatum\n{date}\n\nLink\n{link}"
            send_telegram(msg)
            print(f"POSLANE: {title} ({price})")
            time.sleep(1)
        print(f"Hotovo. Novych: {len(new_ads)} | sledovanych: {len(seen)}")

    save_seen(seen)


if __name__ == "__main__":
    check()
