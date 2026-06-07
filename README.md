# FLIP da Bazos

Druhý, oddelený scanner na Bazoš. Loví **platené kúsky do 40 €** v okruhu PSČ 81105:
iPhone, iPad, MacBook, iMac / Mac mini, Apple Watch a bicykle. Posiela na Telegram každých 10 min.
(Starý "zadarmo" scanner s týmto nemá nič spoločné — toto je samostatný repo/bot.)

## Ako filtruje (aby nevypadli veci, ktoré chceš)
1. **Pozitívny filter** — názov musí obsahovať produktové slovo (iphone, ipad, macbook, imac, apple watch, bicykel, bike…).
2. **Pozičné pravidlo** — slovo príslušenstva (obal, kábel, prilba, stojan…) vyhodí inzerát **len ak stojí PRED** produktovým slovom ("Obal na iPhone" preč, "iPhone + obal" ostáva).
3. **Tvrdý blok** — replika/kópia/fake/iCloud vždy preč.

Slová sa ladia v `flip_bazos.py` (zoznamy `PRODUCT_WORDS`, `ACCESSORY_WORDS`, `HARD_BLOCK`).

## Nastavenie
1. **@BotFather → /newbot** → skopíruj `TELEGRAM_TOKEN`.
2. Napíš novému botovi hocičo, potom otvor
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → nájdeš svoje `chat.id`.
3. **Settings → Secrets and variables → Actions** v tomto repo pridaj:
   - `TELEGRAM_TOKEN`
   - `CHAT_ID`
   - `EXTRA_CHAT_IDS` (voliteľné, ID oddelené čiarkou)
   > Repo je public — token NIKDY nepatrí do kódu, len do Secrets (sú šifrované).
4. Hotovo. Action beží podľa `.github/workflows/flip.yml`.

## Spustenie / časovanie
- GitHub `schedule` cron býva oneskorený o pár minút. Ak chceš spoľahlivých 10 min,
  necháš `cron-job.org` volať `workflow_dispatch` cez GitHub API — rovnako ako pri starom botovi.
- Ručne: záložka **Actions → FLIP da Bazos → Run workflow**.

## Stav (`seen_ads.json`)
Formát `{ "url": počet_minutí }`. Inzerát, ktorý sa 3× po sebe neukáže, sa vymaže
(ak sa znova objaví, pingne nanovo). Prvý beh nič nespamuje — len si veci zapamätá.

## Prepínače v `flip_bazos.py`
- `PRICE_MAX` — strop ceny (default 40)
- `MISS_LIMIT` — koľko minutí = vymazať (default 3)
- `ONLY_TODAY` — default `False`. Na `True` posiela len dnes pridané; je to krehké,
  kód ti pri zapnutí vypíše surový dátum do logu, podľa neho sa doladí.
