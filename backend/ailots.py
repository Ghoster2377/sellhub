"""AI-конвейер SellHub: ссылки на товары (+ подписи) -> черновики для панели.

Пользователь кидает одну или несколько ссылок (каждую можно подписать),
модуль для каждой: читает страницу, достаёт название/описание/цену,
определяет площадку и категорию, пишет заголовок и описание, считает цену
с наценкой 25% (округление до *9). Результат — черновики (status=draft):
ничего не публикуется без явного подтверждения владельца.
"""
import logging
import re
import urllib.request

log = logging.getLogger("sellhub.ailots")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
PRICE_JSON_RE = re.compile(r'"price"\s*:\s*"?\s*(\d[\d\s\u00a0]{0,7}(?:[.,]\d+)?)', re.I)
PRICE_TXT_RE = re.compile(r"(\d[\d\s\u00a0]{0,7})\s*(?:₽|руб\.?|rub)", re.I)

PO_KW = ["донат", "donate", "кристал", "гем", "gem", "roblox", "роблокс", "genshin",
         "геншин", "standoff", "мобильн", "mobile", "android", "ios", "пополнен",
         "top up", "topup", "coins", "монет", "валюта", "бакс", "uc ", "pubg"]
FP_KW = ["ключ", "key", "steam", "стим", "аккаунт", "account", "psn", "xbox",
         "nintendo", "battle", "ubisoft", "ea ", "кошелек", "wallet", "gift",
         "подарочн", "карта", "лицензи", "license", "pc", "пк"]
CATS = [
    ("donate", ["донат", "donate", "кристал", "гем", "gem", "coins", "монет", "uc ", "валюта", "roblox", "genshin"]),
    ("topup", ["пополнен", "top up", "topup", "баланс", "телефон", "номер"]),
    ("subs", ["подписк", "subscription", "premium", "премиум", "plus", "youtube", "spotify", "netflix", "кинопоиск"]),
    ("lic", ["лицензи", "license", "ключ", "key", "активаци", "activation"]),
    ("acc", ["аккаунт", "account", "профиль с ", "учётк"]),
    ("games", ["игра", "game", "dlc", "дополнен", "издан"]),
]
GAMES = ["genshin impact", "roblox", "minecraft", "pubg mobile", "pubg", "free fire",
         "standoff 2", "brawl stars", "mobile legends", "honkai", "zenless", "wuthering",
         "warframe", "fortnite", "steam", "cs2", "counter-strike", "dota 2", "valorant",
         "world of tanks", "world of warcraft", "escape from tarkov", "rust", "warface",
         "delta force", "apex legends", "call of duty", "ea sports fc", "dead by daylight",
         "hearthstone", "the sims", "cyberpunk", "red dead", "elden ring", "diablo",
         "overwatch", "lineage", "black desert", "lost ark", "path of exile", "albion",
         "aion", "discord nitro", "spotify", "youtube", "netflix", "playstation", "xbox",
         "nintendo", "psn", "gta", "clash royale", "arena breakout", "efootball"]


def _fetch(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.8",
                      "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(700_000).decode("utf-8", "ignore")


def _meta(html: str, *names) -> str:
    for n in names:
        m = re.search(r'<meta[^>]+(?:property|name)=["\']' + n + r'["\'][^>]+content=["\']([^"\']{1,500})["\']',
                      html, re.I)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']{1,500})["\'][^>]+(?:property|name)=["\']' + n + r'["\']',
                          html, re.I)
        if m:
            return m.group(1).strip()
    return ""


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&#39;", "'").replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", s).strip()


def _price(html: str):
    m = PRICE_JSON_RE.search(html) or PRICE_TXT_RE.search(_clean(html))
    if not m:
        return 0
    v = m.group(1).replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        v = float(v)
    except ValueError:
        return 0
    return int(v) if 10 <= v <= 500_000 else 0


def _classify(text: str, url: str):
    t = text.lower()
    po = sum(1 for k in PO_KW if k in t)
    fp = sum(1 for k in FP_KW if k in t)
    if "playerok" in url:
        po += 3
    if "funpay" in url:
        fp += 3
    platform = "po" if po >= fp else "fp"
    cat = next((c for c, kws in CATS if any(k in t for k in kws)),
               "donate" if platform == "po" else "games")
    game = next((g for g in GAMES if g in t), "")
    return platform, cat, game


def _nice_price(cost: int) -> int:
    if not cost:
        return 0
    p = int(cost * 1.25 // 10 * 10) + 9
    return max(59, p)


def build_drafts(text: str):
    """text — произвольный текст со ссылками и подписями. -> (drafts, report)."""
    caption = ""
    items = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        urls = URL_RE.findall(ln)
        if urls:
            cap = URL_RE.sub(" ", ln)
            cap = re.sub(r"\s+", " ", cap).strip(" -:–—,;")
            for u in urls:
                items.append((u, cap or caption))
            caption = ""
        else:
            caption = (caption + " " + ln).strip()[:300]

    drafts, report = [], []
    for url, cap in items[:12]:
        html, title, desc, price = "", "", "", 0
        try:
            html = _fetch(url)
            title = _clean(_meta(html, "og:title", "twitter:title") or
                           (re.search(r"<title[^>]*>([^<]{1,200})", html, re.I) or ["", ""])[1])
            desc = _clean(_meta(html, "og:description", "description"))
            price = _price(html)
        except Exception as e:
            log.info("ailots fetch %s: %s", url, e)
        base = cap or title or url.split("/")[-1] or "товар"
        blob = f"{cap} {title} {desc} {url}"
        pf, cat, game = _classify(blob, url)
        lot = (cap or title)[:60].strip() or "Товар по ссылке"
        d_desc = "\n".join(x for x in [
            (cap or title) + ".",
            desc[:300],
            "⚡ Моментальная передача через чат площадки после оплаты.",
            "✅ Гарантия продавца SellHub: возврат при любой проблеме.",
        ] if x)
        drafts.append({
            "platform": "playerok" if pf == "po" else "funpay",
            "game": game.title() if game else (cat if pf == "po" else "Steam / ключи"),
            "cat": cat, "lot": lot, "desc": d_desc,
            "price": _nice_price(price), "cost": price, "url": url,
            "dest": "playerok" if pf == "po" else "funpay", "status": "draft",
        })
        report.append(f"• {lot[:40]} → {'Playerok' if pf=='po' else 'FunPay'}, "
                      f"{cat}" + (f", цена источника {price} ₽ → наша {_nice_price(price)} ₽"
                                 if price else ", цену проверь вручную"))
    return drafts, report
