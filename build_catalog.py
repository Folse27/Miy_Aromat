#!/usr/bin/env python3
"""
MIY AROMAT — KeepinCRM YML feed -> public catalog data (v2)
============================================================
Produces products.js (in stock) and products-all.js (everything)
with ONLY public fields for the catalog frontend.

Rules (per owner's requests):
  - classification (Елітна/Ніша) is NOT exported
  - price_old is NOT exported
  - descriptions: Ukrainian only, full text (no truncation);
    generic "ТЕСТЕР - це демонстраційний зразок..." boilerplate removed
  - notes: translated to Ukrainian via dictionary; if any note of a
    product cannot be translated, the whole notes field is dropped
  - aroma tags: only values with a known Ukrainian mapping are kept

Usage:
  python3 build_catalog.py <feed.xml> <out_dir>

Production: run on a schedule (1-2x/day); feed URL with access token
comes from an environment variable, never from public code.
"""
import sys, json, re, html
import xml.etree.ElementTree as ET

EXCLUDED_CATEGORY_NAMES = {"Видалені"}
TESTER_BOILERPLATE = "ТЕСТЕР - це демонстраційний зразок"

# ---------------- aroma families (strict: unmapped -> dropped) --------
AROMA_MAP = {
    "древесные": "деревні", "цветочные": "квіткові", "мускусные": "мускусні",
    "ванильные": "ванільні", "цитрусовые": "цитрусові",
    "восточные (ориентальные)": "східні", "восточные": "східні",
    "фруктовые": "фруктові", "сладкие": "солодкі", "гурманские": "гурманські",
    "пряные": "пряні", "свежие": "свіжі", "кожаные": "шкіряні",
    "акватические": "акватичні", "морские": "акватичні", "водные": "акватичні",
    "зеленые": "зелені", "пудровые": "пудрові", "альдегидные": "альдегідні",
    "шипровые": "шипрові", "фужерные": "фужерні", "табачные": "тютюнові",
    "цветочно-фруктовые": "квітково-фруктові",
    "амбровые (лавандовые)": "амброві", "амбровые": "амброві",
    # UA passthrough
    "деревні": "деревні", "квіткові": "квіткові", "мускусні": "мускусні",
    "ванільні": "ванільні", "цитрусові": "цитрусові", "східні": "східні",
    "фруктові": "фруктові", "солодкі": "солодкі", "гурманські": "гурманські",
    "пряні": "пряні", "свіжі": "свіжі", "шкіряні": "шкіряні",
    "акватичні": "акватичні", "зелені": "зелені", "пудрові": "пудрові",
    "амброві": "амброві", "шипрові": "шипрові", "фужерні": "фужерні",
}

CLASSLESS = True  # kept for clarity: classification intentionally removed

TYPE_MAP = {
    "парфюмированная вода": "Парфумована вода", "парфумована вода": "Парфумована вода",
    "туалетная вода": "Туалетна вода", "туалетна вода": "Туалетна вода",
    "духи": "Парфуми", "парфуми": "Парфуми", "одеколон": "Одеколон",
}
SEASON_WORDS = [("зим", "зима"), ("весн", "весна"), ("весен", "весна"),
                ("літ", "літо"), ("летн", "літо"), ("осін", "осінь"), ("осен", "осінь")]
FORMAT_MAP = {
    "стандартный": "Флакон", "стандартний": "Флакон", "стандарный": "Флакон",
    "тестер": "Тестер", "пробник": "Пробник",
    "миниатюра": "Мініатюра", "мініатюра": "Мініатюра",
}

# ---------------- notes dictionary (RU -> UA) --------------------------
NOTES_MAP = {
    "жасмин":"жасмин","мускус":"мускус","пачули":"пачулі","бергамот":"бергамот",
    "ваниль":"ваніль","сандал":"сандал","амбра":"амбра","роза":"троянда",
    "ветивер":"ветивер","мандарин":"мандарин","бобы тонка":"боби тонка",
    "лимон":"лимон","лаванда":"лаванда","апельсиновый цвет":"апельсиновий цвіт",
    "белый кедр":"білий кедр","древесные ноты":"деревні ноти","грейпфрут":"грейпфрут",
    "белый мускус":"білий мускус","кедр":"кедр","ирис":"ірис",
    "розовый перец":"рожевий перець","кардамон":"кардамон","кожа":"шкіра",
    "ландыш":"конвалія","герань":"герань","персик":"персик","груша":"груша",
    "апельсин":"апельсин","черная смородина":"чорна смородина","тубероза":"тубероза",
    "фиалка":"фіалка","нероли":"неролі","дубовый мох":"дубовий мох",
    "иланг-иланг":"іланг-іланг","бензоин":"бензоїн","ладан":"ладан",
    "мускатный орех":"мускатний горіх","пион":"півонія","жасмин самбак":"жасмин самбак",
    "малина":"малина","имбирь":"імбир","яблоко":"яблуко","корица":"кориця",
    "белая фрезия":"біла фрезія","орхидея":"орхідея","перец":"перець",
    "лабданум":"лабданум","морские ноты":"морські ноти","гелиотроп":"геліотроп",
    "гвоздика":"гвоздика","розмарин":"розмарин","шалфей":"шавлія",
    "лист фиалки":"лист фіалки","магнолия":"магнолія","зеленые ноты":"зелені ноти",
    "мускатный шалфей":"мускатна шавлія","амброксан":"амброксан","мята":"м'ята",
    "шафран":"шафран","слива":"слива","кориандр":"коріандр","серая амбра":"сіра амбра",
    "ананас":"ананас","османтус":"османтус","мед":"мед","гардения":"гарденія",
    "корень ириса":"корінь ірису","базилик":"базилік","кипарис":"кипарис",
    "болгарская роза":"болгарська троянда","молекула кашмеран":"кашмеран",
    "лист черной смородины":"лист чорної смородини","табак":"тютюн","кокос":"кокос",
    "водные ноты":"водні ноти","цветочные ноты":"квіткові ноти","цитрус":"цитрус",
    "кофе":"кава","фрезия":"фрезія","личи":"лічі","черный перец":"чорний перець",
    "нарцисс":"нарцис","цветок апельсина":"квітка апельсина","лайм":"лайм",
    "альдегиды":"альдегіди","петитгрейн":"петитгрейн",
    "вирджинийский кедр":"вірджинський кедр","вирджинский кедр":"вірджинський кедр",
    "лилия":"лілія","миндаль":"мигдаль","специи":"спеції","лотос":"лотос",
    "ежевика":"ожина","какао":"какао","абрикос":"абрикос","карамель":"карамель",
    "кашемировое дерево":"кашемірове дерево","мох":"мох","амбретта":"амбрета",
    "зеленый мандарин":"зелений мандарин","розовое дерево":"рожеве дерево",
    "белые цветы":"білі квіти","чай":"чай","красный апельсин":"червоний апельсин",
    "соль":"сіль","ягоды можжевельника":"ягоди ялівцю","мимоза":"мімоза",
    "дамасская роза из турции":"дамаська троянда","дамасская роза":"дамаська троянда",
    "зеленое яблоко":"зелене яблуко","дерево уд":"дерево уд","пралине":"праліне",
    "гуаяк":"гваяк","гваяк":"гваяк","цикламен":"цикламен","дыня":"диня",
    "морская соль":"морська сіль","лесной орех":"лісовий горіх","уд":"уд",
    "олибанум":"олібанум","арбуз":"кавун","бурбонская ваниль":"бурбонська ваніль",
    "можжевельник":"ялівець","тмин":"кмин","тиаре":"тіаре","ревень":"ревінь",
    "гиацинт":"гіацинт","жимолость":"жимолость","клубника":"полуниця",
    "красное яблоко":"червоне яблуко","гранат":"гранат","горький апельсин":"гіркий апельсин",
    "красные ягоды":"червоні ягоди","калабрийский бергамот":"калабрійський бергамот",
    "замша":"замша","гальбанум":"гальбанум","вишня":"вишня","артемизия":"полин",
    "ром":"ром","сахар":"цукор","ambroxan":"амброксан","iso e super":"iso e super",
    "маракуйя":"маракуя","водяная лилия":"водяна лілія","франжипани":"франжипані",
    "сандаловое дерево":"сандалове дерево","лакричник":"локриця",
    "сицилийский лимон":"сицилійський лимон","фруктовые ноты":"фруктові ноти",
    "турецкая роза":"турецька троянда","сосна":"сосна","юзу":"юзу","янтарь":"бурштин",
    "инжир":"інжир","чабрец":"чебрець","клементин":"клементин","кашмеран":"кашмеран",
    "майская роза":"травнева троянда","морская вода":"морська вода","кремень":"кремінь",
    "молоко":"молоко","палисандр":"палісандр","коньяк":"коньяк","анис":"аніс",
    "береза":"береза","нагармота":"нагармота","зеленый чай":"зелений чай",
    "махагони":"махагоні","анис звездчатый":"бадьян","календула":"календула",
    "cetalox":"cetalox","абсолют ванили":"абсолют ванілі","абсолют кумарина":"абсолют кумарину",
    "белый перец":"білий перець","морские водоросли":"морські водорості","элеми":"елемі",
    "красная смородина":"червона смородина","стиракс":"стиракс","тархун":"тархун",
    "грасская роза":"граська троянда","манго":"манго","шоколад":"шоколад","мате":"мате",
    "пудровая нота":"пудрова нота","пудровые ноты":"пудрові ноти",
    "солнечные ноты":"сонячні ноти","akigalawood":"akigalawood",
    "атласский кедр":"атласький кедр","белый мед":"білий мед","мирра":"мирра",
    "пеларгония":"пеларгонія","элеми и бергамот":"елемі, бергамот",
    "фиалковый корень":"фіалковий корінь","бузина":"бузина","ирис паллида":"ірис паліда",
    "сандаловый мускус":"сандаловий мускус","цветы апельсина":"квіти апельсина",
    "флердоранж":"флердоранж","гальбан":"гальбанум","ветивер из гаити":"гаїтянський ветивер",
    "пачули из индонезии":"індонезійські пачулі","дубовый мох и пачули":"дубовий мох, пачулі",
    "ваниль из мадагаскара":"мадагаскарська ваніль","мадагаскарская ваниль":"мадагаскарська ваніль",
    # UA passthrough for feeds that already contain Ukrainian
    "ваніль":"ваніль","троянда":"троянда","мускусу":"мускус","бергамоту":"бергамот",
    # round 2: frequent terms found in the real feed
    "цитрусы":"цитруси","гвоздика (пряность)":"гвоздика","гвоздика (цветок)":"гвоздика",
    "танжерин":"танжерин","светлое дерево":"світле дерево",
    "африканский апельсиновый цвет":"африканський апельсиновий цвіт","дуб":"дуб",
    "опопонакс":"опопонакс","давана":"давана","папирус":"папірус","цитрон":"цитрон",
    "кумарин":"кумарин","гедион":"гедіон","итальянский лимон":"італійський лимон",
    "семена моркови":"насіння моркви","пихтовый бальзам":"ялицевий бальзам",
    "египетский жасмин":"єгипетський жасмин","ангелика":"ангеліка","ромашка":"ромашка",
    "австралийский сандал":"австралійський сандал","взбитые сливки":"збиті вершки",
    "звездчатый анис":"бадьян","бамбук":"бамбук","сирень":"бузок",
    "горький миндаль":"гіркий мигдаль","розовый грейпфрут":"рожевий грейпфрут",
    "ель":"ялина","сычуанский перец":"сичуанський перець","кумин":"кумін","лавр":"лавр",
    "айва":"айва","мирт":"мирт","белый персик":"білий персик","цибетин":"цибетин",
    "пряности":"прянощі","черный чай":"чорний чай","красный перец":"червоний перець",
    "озон":"озон","лист инжира":"лист інжиру","калон":"калон","белая амбра":"біла амбра",
    "дым":"дим","полынь":"полин","маршмеллоу":"маршмелоу","конопля":"коноплі",
    "толу бальзам":"толуанський бальзам","индийская тубероза":"індійська тубероза",
    "фисташки":"фісташки","сицилийский бергамот":"сицилійський бергамот",
    "розовая вода":"трояндова вода","итальянский мандарин":"італійський мандарин",
    "минеральные ноты":"мінеральні ноти","ванильная орхидея":"ванільна орхідея",
    "каштан":"каштан","вербена лимонная":"лимонна вербена","цедра лимона":"цедра лимона",
    "сицилийский мандарин":"сицилійський мандарин","дерево агар (уд)":"дерево агар (уд)",
    "мастиковое дерево":"мастикове дерево","боярышник":"глід","сорбет":"сорбет",
    "яблоко \"granny smith\"":"яблуко granny smith","пудра":"пудра","ветиверия":"ветиверія",
    "гваяковое дерево":"гваякове дерево","красный мандарин":"червоний мандарин",
    "мандариновый лист":"мандариновий лист","зеленые листья":"зелене листя",
    "белая лилия":"біла лілія","водяной гиацинт":"водяний гіацинт","фрукты":"фрукти",
    "экзотические фрукты":"екзотичні фрукти","сливки":"вершки","мускатный цвет":"мускатний цвіт",
}

UA_VALUES = set(NOTES_MAP.values())
LATIN_RE = re.compile(r"[a-z0-9][a-z0-9 .\-'&()]*", re.I)
UA_CHARS = re.compile(r"[іїєґ]")
RU_CHARS = re.compile(r"[ыэъё]")

SECTION_LABELS = [
    (re.compile(r"(начальн\w+ нот\w+|верхн\w+ нот\w+|верхні ноти)\s*:", re.I), "Верхні"),
    (re.compile(r"(нот\w+ сердца|средн\w+ нот\w+|ноти серця|серцев\w+ нот\w+)\s*:", re.I), "Серце"),
    (re.compile(r"(конечн\w+ нот\w+|базов\w+ нот\w+|базові ноти)\s*:", re.I), "База"),
]

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")

def clean_text(s):
    if not s: return ""
    s = html.unescape(html.unescape(s))
    s = TAG_RE.sub(" ", s).replace("\u00a0", " ")
    return WS_RE.sub(" ", s).strip()

def norm_aroma(raw):
    out, seen = [], set()
    for part in re.split(r"[|,]", raw or ""):
        p = part.strip().lower()
        ua = AROMA_MAP.get(p)
        if ua and ua not in seen:
            seen.add(ua); out.append(ua)
    return out[:4]

def norm_season(raw):
    found, low = [], (raw or "").lower()
    for stem, ua in SEASON_WORDS:
        if stem in low and ua not in found: found.append(ua)
    if len(found) >= 4: return "універсальний"
    return " / ".join(found)

def norm_format(raw, name, vol):
    f = FORMAT_MAP.get((raw or "").strip().lower())
    if f: return f
    if "тестер" in (name or "").lower(): return "Тестер"
    m = re.search(r"([\d.,]+)\s*мл", vol or "")
    if m:
        try:
            if float(m.group(1).replace(",", ".")) <= 3: return "Пробник"
        except ValueError: pass
    return "Флакон"

def tr_token(t):
    """Ukrainian form of a note token, or None if untranslatable."""
    if t in NOTES_MAP: return NOTES_MAP[t]
    if t in UA_VALUES: return t
    if LATIN_RE.fullmatch(t): return t                       # amberwood, hedione…
    if UA_CHARS.search(t) and not RU_CHARS.search(t): return t  # already Ukrainian
    return None

# ---------------- machine translation layer ---------------------------
# Unknown tokens are translated RU->UK via an external service and cached
# in notes_cache.json (commit it to the repo). The curated NOTES_MAP above
# always wins over the API — it's the quality override for perfume jargon.
# Provider is picked automatically:
#   1. GOOGLE_TRANSLATE_API_KEY  (official Cloud Translation v2, paid tier)
#   2. DEEPL_API_KEY             (DeepL API Free/Pro)
#   3. deep_translator package   (free Google web endpoint, NO key needed)
#      pip install deep-translator
import os, json as _json, time, urllib.request, urllib.parse

CACHE_FILE = None   # set in main() next to the output dir

def _load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f: return _json.load(f)
    except (FileNotFoundError, ValueError): return {}

def _save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        _json.dump(cache, f, ensure_ascii=False, indent=0, sort_keys=True)

def _translate_free(tokens):
    """Keyless fallback via deep_translator (Google web endpoint)."""
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        print("  [info] deep-translator not installed "
              "(pip install deep-translator) — skipping free translation",
              file=sys.stderr)
        return {}
    out = {}
    tr = GoogleTranslator(source="ru", target="uk")
    for i in range(0, len(tokens), 50):
        batch = tokens[i:i+50]
        try:
            res = tr.translate_batch(batch)
            for src, dst in zip(batch, res):
                if dst: out[src] = dst.strip().lower()
        except Exception as e:
            print(f"  [warn] free translation batch failed: {e}", file=sys.stderr)
            time.sleep(2)
        time.sleep(0.5)          # be gentle with the free endpoint
    return out

def _api_translate(tokens):
    """Translate a list of RU tokens to UK. Returns dict token->translation."""
    if not tokens: return {}
    gkey = os.environ.get("GOOGLE_TRANSLATE_API_KEY")
    dkey = os.environ.get("DEEPL_API_KEY")
    if not (gkey or dkey):
        return _translate_free(tokens)
    out = {}
    for i in range(0, len(tokens), 100):                     # batches of 100
        batch = tokens[i:i+100]
        try:
            if gkey:
                body = urllib.parse.urlencode(
                    [("q", t) for t in batch] +
                    [("source", "ru"), ("target", "uk"), ("format", "text"), ("key", gkey)]
                ).encode()
                req = urllib.request.Request(
                    "https://translation.googleapis.com/language/translate/v2",
                    data=body, method="POST")
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = _json.load(r)
                tr = [x["translatedText"] for x in data["data"]["translations"]]
            else:
                body = _json.dumps({"text": batch, "source_lang": "RU",
                                    "target_lang": "UK"}).encode()
                req = urllib.request.Request(
                    "https://api-free.deepl.com/v2/translate", data=body,
                    headers={"Authorization": f"DeepL-Auth-Key {dkey}",
                             "Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = _json.load(r)
                tr = [x["text"] for x in data["translations"]]
            for src, dst in zip(batch, tr):
                out[src] = dst.strip().lower()
        except Exception as e:
            print(f"  [warn] translation API batch failed: {e}", file=sys.stderr)
    return out

PENDING = set()   # tokens seen this run that need API translation

def resolve_token(t, cache):
    ua = tr_token(t)
    if ua is not None: return ua
    if t in cache: return cache[t]
    PENDING.add(t)
    return None      # resolved on second pass after the API call

def translate_notes(raw, cache):
    """Return Ukrainian notes string, or '' if any token is untranslatable."""
    s = clean_text(raw)
    if not s: return ""
    # split into labeled sections
    marks = []
    for rx, label in SECTION_LABELS:
        for m in rx.finditer(s):
            marks.append((m.start(), m.end(), label))
    marks.sort()
    sections = []
    if marks:
        for i, (a, b, label) in enumerate(marks):
            end = marks[i+1][0] if i+1 < len(marks) else len(s)
            sections.append((label, s[b:end]))
    else:
        sections = [("", s)]

    out_sections = []
    for label, body in sections:
        tokens = re.split(r"[|,.;]| и | та ", body)
        ua_tokens = []
        for t in tokens:
            t = t.strip().strip(",.;:").lower()
            if not t: continue
            ua = resolve_token(t, cache)
            if ua is None or RU_CHARS.search(ua):
                return ""   # not translated (yet) or API output still Russian
            if ua not in ua_tokens:
                ua_tokens.append(ua)
        if ua_tokens:
            prefix = f"{label}: " if label else ""
            out_sections.append(prefix + ", ".join(ua_tokens))
    return " · ".join(out_sections)

def clean_description(raw):
    d = clean_text(raw)
    if d.startswith(TESTER_BOILERPLATE):
        return ""                    # generic tester template, not a real description
    return d

def main(feed_path, out_dir):
    global CACHE_FILE
    CACHE_FILE = f"{out_dir}/notes_cache.json"
    cache = _load_cache()

    excluded_ids = set()
    for ev, el in ET.iterparse(feed_path, events=("end",)):
        if el.tag == "category" and (el.text or "").strip() in EXCLUDED_CATEGORY_NAMES:
            excluded_ids.add(el.attrib.get("id"))
        if el.tag == "offers": break

    products, skipped = [], 0
    for ev, el in ET.iterparse(feed_path, events=("end",)):
        if el.tag != "offer": continue
        try:
            if (el.findtext("categoryId") or "") in excluded_ids:
                skipped += 1; continue
            params = {p.attrib.get("name"): (p.text or "").strip() for p in el.iter("param")}
            name = clean_text(el.findtext("name_ua") or el.findtext("name") or "")
            if not name: continue

            vol = params.get("Объем", "")
            notes_raw = params.get("Ноты", "")
            price = float(el.findtext("price") or 0)
            pictures = [(p.text or "").strip() for p in el.findall("picture") if (p.text or "").strip()]

            products.append({
                "id": el.attrib.get("id", ""),
                "sku": re.sub(r"[\s\-–—]+$", "", params.get("Артикул", "")).strip(),
                "brand": clean_text(el.findtext("vendor") or ""),
                "name": name,
                "vol": vol,
                "type": TYPE_MAP.get(params.get("Тип", "").strip().lower(),
                                     clean_text(params.get("Тип", "")).replace("-", "")),
                "form": norm_format(params.get("Формат"), name, vol),
                "price": int(price) if price == int(price) else price,
                "qty": int(float(el.findtext("stock_quantity") or 0)),
                "photo": pictures[0] if pictures else "",
                "notes": notes_raw,   # raw for now; translated in pass 2
                "aroma": norm_aroma(params.get("Аромат") or params.get("Семейство аромата") or ""),
                "season": norm_season(params.get("Сезонность", "")),
                "desc": clean_description(el.findtext("description_ua")),  # UA only, full text
            })
        finally:
            el.clear()

    # ---- pass 1: collect ALL unknown tokens across all products -------
    for p in products:
        s = clean_text(p["notes"])
        for rx, _ in SECTION_LABELS: s = rx.sub("|", s)
        for t in re.split(r"[|,.;]| и | та ", s):
            t = t.strip().strip(",.;:").lower()
            if t: resolve_token(t, cache)

    # ---- translate unknown tokens once, extend the cache --------------
    if PENDING:
        newly = _api_translate(sorted(PENDING))
        if newly:
            cache.update(newly)
            _save_cache(cache)
            print(f"  API-translated {len(newly)} new tokens (cache: {len(cache)} total)")
        else:
            print(f"  [info] {len(PENDING)} unknown tokens could not be translated — "
                  f"their products will have notes dropped")

    # ---- pass 2: final notes -------------------------------------------
    notes_kept = notes_dropped = 0
    for p in products:
        raw = p["notes"]
        p["notes"] = translate_notes(raw, cache)
        if raw.strip():
            notes_kept += bool(p["notes"]); notes_dropped += not p["notes"]

    products.sort(key=lambda p: (p["qty"] <= 0, p["brand"].lower(), p["name"].lower()))

    def dump(items, fname, varname):
        js = f"window.{varname}=" + json.dumps(items, ensure_ascii=False, separators=(",", ":")) + ";"
        with open(f"{out_dir}/{fname}", "w", encoding="utf-8") as f:
            f.write(js)
        return len(js.encode()) / 1e6

    instock = [p for p in products if p["qty"] > 0]
    s1 = dump(instock, "products.js", "PRODUCTS")
    s2 = dump(products, "products-all.js", "PRODUCTS_ALL")

    print(f"OK: {len(products)} products total, {skipped} skipped (deleted)")
    print(f"  notes translated: {notes_kept}, dropped (untranslatable): {notes_dropped}")
    print(f"  products.js     (в наявності): {len(instock)} items, {s1:.1f} MB")
    print(f"  products-all.js (усі товари):  {len(products)} items, {s2:.1f} MB")
    np = [p["id"] for p in products if not p["photo"]]
    print(f"  without photo in catalog: {len(np)} -> {', '.join(np)}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
