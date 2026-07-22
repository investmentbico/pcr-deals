#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coletor de deals — lê e-mails de wholesalers (threads do Gmail salvas em JSON),
extrai cada imóvel (endereço, specs, ARV, asking) + a FOTO REAL de cada um,
aplica o MARKUP da casa, separa por CONDADO, remove REPETIDOS, baixa/otimiza/
re-hospeda as fotos no GitHub Pages e gera deals.json.

Uso:
  python3 coletor_deals.py <thread1.json> [thread2.json ...]

Regras (dono, 2026-06-30):
  - Markup: +$25k; se preço do wholesaler > $750k -> +$30k; se > $1.2M -> +$50k.
  - Separar por condado (igual os wholesalers).
  - Não repetir o mesmo imóvel (mesmo endereço), inclusive entre wholesalers.
"""
import json, sys, re, os, io, urllib.request

HERE   = os.path.dirname(os.path.abspath(__file__))
# Na nuvem (GitHub Actions), o repo pcr-deals É o SITE. Caminhos relativos ao próprio repo.
SITE   = HERE
IMGDIR = os.path.join(SITE, "images", "listings")
OUTJSON= os.path.join(HERE, "deals.json")
PAGES  = "https://investmentbico.github.io/pcr-deals/"

COUNTY_ORDER = ["Miami-Dade", "Broward", "Palm Beach", "St. Lucie", "Martin", "Brevard",
                "Orange", "Lee", "Duval", "Pinellas", "Pasco", "Hillsborough", "Charlotte",
                "Alachua", "Polk", "Outros"]

CITY_COUNTY = {c.lower(): "Broward" for c in [
  "Fort Lauderdale","Ft Lauderdale","Hollywood","Pompano Beach","Coral Springs","Plantation",
  "Dania Beach","Hallandale Beach","Pembroke Pines","Deerfield Beach","Tamarac","Oakland Park",
  "North Lauderdale","Lauderdale By The Sea","Lauderhill","Lauderdale Lakes","Margate","Sunrise",
  "Davie","Miramar","Cooper City","Weston","Parkland","Wilton Manors","Lighthouse Point",
  "Coconut Creek","Pembroke Park","West Park","Southwest Ranches"]}
CITY_COUNTY.update({c.lower(): "Miami-Dade" for c in [
  "Miami","Miami Gardens","Homestead","Hialeah","North Miami","North Miami Beach","Cutler Bay",
  "El Portal","Miami Beach","Aventura","Doral","Kendall","Opa-locka","Opa Locka","Florida City",
  "Palmetto Bay","Pinecrest","Coral Gables","South Miami","Sweetwater","Hialeah Gardens",
  "Miami Lakes","Miami Springs","Sunny Isles Beach","Bay Harbor Islands","Surfside"]})
CITY_COUNTY.update({c.lower(): "Palm Beach" for c in [
  "West Palm Beach","Boca Raton","Boynton Beach","Delray Beach","Lake Worth","Palm Beach Gardens",
  "Jupiter","Wellington","Riviera Beach","Greenacres","Royal Palm Beach","Lantana","Palm Springs",
  "Belle Glade","Lake Park","Palm Beach"]})
CITY_COUNTY.update({c.lower(): "St. Lucie" for c in ["Port St Lucie","Port Saint Lucie","Fort Pierce","St Lucie"]})
CITY_COUNTY.update({c.lower(): "Martin" for c in ["Stuart","Hobe Sound","Palm City","Jensen Beach"]})
CITY_COUNTY.update({c.lower(): "Brevard" for c in ["Melbourne","Palm Bay","Titusville","Cocoa","Rockledge","Merritt Island","Viera"]})
CITY_COUNTY.update({c.lower(): "Orange" for c in ["Orlando","Apopka","Ocoee","Winter Garden","Winter Park","Maitland"]})
CITY_COUNTY.update({c.lower(): "Lee" for c in ["Cape Coral","Fort Myers","Lehigh Acres","Bonita Springs","Estero"]})
CITY_COUNTY.update({c.lower(): "Duval" for c in ["Jacksonville","Jacksonville Beach"]})
CITY_COUNTY.update({c.lower(): "Pinellas" for c in ["Dunedin","Clearwater","St Petersburg","Saint Petersburg","Largo","Pinellas Park"]})
CITY_COUNTY.update({c.lower(): "Pasco" for c in ["Port Richey","New Port Richey","Wesley Chapel","Hudson","Zephyrhills"]})
CITY_COUNTY.update({c.lower(): "Hillsborough" for c in ["Tampa","Brandon","Riverview","Plant City"]})
CITY_COUNTY.update({c.lower(): "Charlotte" for c in ["Port Charlotte","Punta Gorda"]})
CITY_COUNTY.update({c.lower(): "Alachua" for c in ["Gainesville","Micanopy"]})
CITY_COUNTY.update({c.lower(): "Polk" for c in ["Lakeland","Winter Haven","Davenport"]})
CITY_COUNTY.update({c.lower(): "Osceola" for c in ["Kissimmee","St Cloud"]})
CITY_COUNTY.update({c.lower(): "Volusia" for c in ["Daytona Beach","Deltona","Deland","Ormond Beach"]})

def county_of(city, zip5):
    c = CITY_COUNTY.get(city.strip().lower())
    if c: return c
    z = int(zip5) if zip5 and zip5.isdigit() else 0
    if 33001 <= z <= 33299: return "Miami-Dade"
    if 33300 <= z <= 33399: return "Broward"
    if 33400 <= z <= 33499: return "Palm Beach"
    if 34945 <= z <= 34988: return "St. Lucie"
    if 32900 <= z <= 32999: return "Brevard"
    return "Outros"

def markup(p, source=None):
    if source == "Beau Roberts": return 40_000   # regra fixa só pra ele
    if p > 3_000_000: return 110_000
    if p > 1_500_000: return 90_000
    if p > 1_200_000: return 50_000
    if p > 750_000:   return 30_000
    return 25_000

def our_price(p, source=None): return p + markup(p, source) if p else 0

def usd(n): return "${:,}".format(int(round(n or 0)))

def clean(s): return re.sub(r'[​﻿\xa0]', ' ', s).strip()

def is_photo(u):
    """True se a URL parece foto de imóvel (exclui gifs de template, ícones, pixels)."""
    if re.search(r'\.gif(\?|$)', u, re.I): return False
    if re.search(r'imgssl\.constantcontact|/templates/|app\.icontact|cdn\.mcauto-images|/wf/open|/open\?|spacer|tracking|1x1', u, re.I): return False
    return bool(re.search(r'googleusercontent\.com/meips|staticapp\.icpsc|files\.constantcontact|mcusercontent\.com|amazonaws\.com|sendlift|\.(jpe?g|png)(\?|$)', u, re.I))

ADDR_RE = re.compile(r'([0-9XxＸ]{1,6}[\w\.\-/ ]{1,40},\s*[A-Za-z\. ]+,?\s*(?:Fl|FL)\.?\s*(\d{5})?)')

def norm_key(addr):
    a = clean(addr).lower()
    a = re.sub(r',?\s*fl\.?\s*\d*.*$', '', a)
    repl = {r'\b(st|street)\b':'st', r'\b(ave|avenue)\b':'ave', r'\b(ter|terr|terrace)\b':'ter',
            r'\b(dr|drive)\b':'dr', r'\b(rd|road)\b':'rd', r'\b(ct|court)\b':'ct',
            r'\b(pl|place)\b':'pl', r'\b(blvd|boulevard)\b':'blvd', r'\b(ln|lane)\b':'ln'}
    for k,v in repl.items(): a = re.sub(k, v, a)
    return re.sub(r'[^a-z0-9]+', ' ', a).strip()

def extract_specs(text, bullets):
    if bullets:
        return [b for b in bullets if not re.match(r'(?i)\s*arv', b)]
    specs = []
    bb = re.search(r'(\d+)\s*Beds?\s*/\s*(\d+)\s*Baths?', text, re.I)
    sq = re.search(r'([\d,]+)\s*(?:Gross\s*)?Sq\.?\s*Ft\b(?!\s*Lot)', text, re.I)
    units = re.search(r'(\d+)\s*Units?', text, re.I)
    line = ""
    if bb: line = f"{bb.group(1)} Bed / {bb.group(2)} Bath"
    elif units: line = f"{units.group(1)} Units"
    if sq: line = (line + " · " if line else "") + f"{sq.group(1)} Sq Ft"
    if line: specs.append(line)
    lot = re.search(r'([\d,]+)\s*Sq\.?\s*Ft\s*Lot', text, re.I)
    if lot: specs.append(f"Lot {lot.group(1)} Sq Ft")
    built = re.search(r'Built:?\s*(\d{4})', text, re.I)
    if built: specs.append(f"Built {built.group(1)}")
    for kw in ["Tenant Occupied","Pool","No Hoa","Corner Lot","New Roof","Fix And Flip",
               "Full Rehab","Updated Kitchen","Impact Windows","Waterfront","Cbs Construction"]:
        if re.search(re.escape(kw), text, re.I) and len(specs) < 4:
            specs.append(kw)
    return specs

def source_of(sender):
    s = (sender or "").lower()
    if "sharkinvestorproperties" in s or "howtoflip" in s: return "Shark"
    if "jefinancial" in s or "ccsend" in s: return "Jonathan"
    if "investorlift" in s: return "Investorlift"
    if "beau.roberts" in s and "newwestern" in s: return "Beau Roberts"
    return None  # remetente não reconhecido (ex.: outro vendedor da New Western) -> ignora

def parse_investorlift(m):
    pt = clean(m.get("plaintextBody", "")); html = m.get("htmlBody", ""); subj = clean(m.get("subject", ""))
    cc = re.search(r'([A-Za-z\.\s]+?)\s+County,\s*([A-Za-z\.\s]+?),\s*FL\s*(\d{5})', pt)
    city = cc.group(2).strip() if cc else ""
    zip5 = cc.group(3) if cc else ""
    am = re.search(r'>\s*([0-9][^<]*?,\s*[A-Za-z\.\s]+,\s*FL\s*\d{5})\s*<', html)
    if am:
        addr = clean(am.group(1))
    else:
        sm = re.search(r'\bIN\s+(.+?),?\s*\(', subj)
        addr = clean(sm.group(1)) if sm else (f"{city}, FL {zip5}".strip())
    pm = re.search(r'\$\s*([\d.]+)\s*k\b', pt, re.I)
    ask = int(round(float(pm.group(1)) * 1000)) if pm else 0
    arvm = re.search(r'ARV\s*\$\s*([\d.]+)\s*k', pt, re.I)
    arv = f"{arvm.group(1).rstrip('.0') or arvm.group(1)}k" if arvm else ""
    bb = re.search(r'(\d+)\s*beds?\D+(\d+)\s*baths?\D+([\d,]+)\s*sqft', pt, re.I)
    specs = []
    if bb: specs.append(f"{bb.group(1)} Bed / {bb.group(2)} Bath · {bb.group(3)} Sq Ft")
    im = re.search(r'src="(https://s3[^"]+property-images/[^"]+)"', html)
    return [{"addr": addr, "city": city, "county": county_of(city, zip5), "wholesale": ask,
             "arv": arv, "specs": specs, "source": "Investorlift", "_srcphoto": im.group(1) if im else None}] if ask else []

def parse_newwestern(m):
    pt = clean(m.get("plaintextBody", "")); html = m.get("htmlBody", ""); subj = clean(m.get("subject", ""))
    cc = re.search(r'Delivered\s+([A-Za-z\.\s]+?),\s*FL,?\s*(\d{5})?', pt)
    city = cc.group(1).strip() if cc else ""
    zip5 = (cc.group(2) or "") if cc else ""
    pm = re.search(r'\$\s*([\d,]{4,})', subj) or re.search(r'(?:asking|price|for)\D{0,10}\$\s*([\d,]{4,})', pt, re.I)
    ask = int(pm.group(1).replace(",", "")) if pm else 0
    title = re.sub(r'^Available\s*-\s*', '', subj).strip()
    specs = []
    bb = re.search(r'(\d+)\s*bed[s/ ]*\s*(\d+)?\s*bath', pt + " " + subj, re.I)
    if bb:
        specs.append(f"{bb.group(1)} Bed" + (f" / {bb.group(2)} Bath" if bb.group(2) else ""))
    yb = re.search(r'\b(19|20)\d{2}\b\s*build', subj, re.I)
    if yb: specs.append(f"Built {yb.group(0).split()[0]}")
    im = re.search(r'src="(https?://[^"]+\.(?:jpe?g|png))"', html)
    addr = (f"{city}, FL {zip5}".strip().rstrip(",")) or title
    return [{"addr": addr, "city": city, "county": county_of(city, zip5), "wholesale": ask,
             "arv": "", "specs": specs or [title[:60]], "source": "Beau Roberts",
             "_srcphoto": im.group(1) if im else None}] if ask else []

def parse_email(path):
    data = json.load(open(path)); m = data["messages"][0]
    source = source_of(m.get("sender", ""))
    if source is None: return []
    if source == "Investorlift": return parse_investorlift(m)
    if source == "Beau Roberts": return parse_newwestern(m)
    return parse_listmail(m, source)

def parse_listmail(m, source):
    pt = clean(m.get("plaintextBody", "")); html = m["htmlBody"]
    matches = list(ADDR_RE.finditer(pt))
    deals = []
    for i, mm in enumerate(matches):
        addr = clean(mm.group(1)).rstrip(",")
        zip5 = mm.group(2) or ""
        # re-ancorar: tirar palavras de spec antes do número de rua (formato corrido do Jonathan)
        cands = list(re.finditer(r'(?:\d{1,6}|[Xx]{2,6})\s+(?:N\.?[WE]|S\.?[WE]|N|S|E|W|North|South|East|West|[A-Z][a-z]+)', addr))
        if cands:
            addr = addr[cands[-1].start():].strip()
        seg = pt[mm.end(): matches[i+1].start()] if i+1 < len(matches) else pt[mm.end(): mm.end()+600]
        # cidade
        parts = [p.strip() for p in re.split(r',', addr)]
        city = parts[1] if len(parts) >= 2 else ""
        city = re.sub(r'\s*(Fl|FL)\.?\s*\d*$', '', city).strip()
        # fallback: procurar uma cidade conhecida dentro do endereço (vírgula faltando etc.)
        if not city or city.lower() in ("fl", "fl."):
            for cc in CITY_COUNTY:
                if re.search(r'\b' + re.escape(cc) + r'\b', addr, re.I):
                    city = cc.title(); break
        # asking / reduced / arv
        redm = re.search(r'Reduced\s*\$\s*([\d,]+)', seg, re.I)
        askm = re.search(r'Asking\s*\$\s*([\d,]+)', seg, re.I)
        ask = int((redm or askm).group(1).replace(",", "")) if (redm or askm) else 0
        arvm = re.search(r'\bArv\b[:\s]*\$?\s*([\d,]+\+?(?:\s*[–-]\s*\$?[\d,]+)?)', seg, re.I)
        arv = clean(arvm.group(1)) if arvm else ""
        bullets = [clean(l.strip(" •\t")) for l in seg.splitlines() if l.strip().startswith("•")]
        specs = extract_specs(seg, bullets)
        if not ask:  # sem preço não é um deal de verdade
            continue
        deals.append({"addr": addr, "city": city, "county": county_of(city, zip5),
                      "wholesale": ask, "arv": arv, "specs": specs, "source": source,
                      "_pos": mm.start()})
    # mapear foto: primeira imagem de propriedade depois do endereço no HTML
    imgs = [(g.start(), g.group(1)) for g in re.finditer(r'<img[^>]+src="([^"]+)"', html, re.I)]
    imgs = [(p, u) for p, u in imgs if is_photo(u)]
    # posição de cada deal no HTML (tenta o endereço completo, depois pedaços)
    hpos = []
    for d in deals:
        street = re.sub(r'\s+(Unit|Apt|Suite|#).*$', '', d["addr"].split(",")[0].strip(), flags=re.I)
        toks = street.split()
        cands = [street] + ([" ".join(toks[:3])] if len(toks) >= 3 else []) + ([" ".join(toks[:2])] if len(toks) >= 2 else [])
        found = -1
        for c in cands:
            if len(c) < 4: continue
            h = re.search(re.escape(c).replace(r"\ ", r"\s*"), html)
            if h: found = h.start(); break
        hpos.append(found)
    used = [False] * len(imgs)
    def take(lo, hi):
        for idx, (pp, u) in enumerate(imgs):
            if not used[idx] and lo < pp < hi:
                used[idx] = True; return u
        return None
    # 1ª passada: por endereço encontrado
    for i, d in enumerate(deals):
        p = hpos[i]
        if p < 0:
            d["_srcphoto"] = None; continue
        nxt = next((hpos[j] for j in range(i+1, len(deals)) if hpos[j] > 0), 10**9)
        d["_srcphoto"] = take(p, nxt)
    # 2ª passada (plano B posicional): foto não usada na janela entre vizinhos conhecidos
    for i, d in enumerate(deals):
        if d.get("_srcphoto"): continue
        prev_p = max([hpos[j] for j in range(0, i) if hpos[j] > 0] or [0])
        nxt = min([hpos[j] for j in range(i+1, len(deals)) if hpos[j] > 0] or [10**9])
        d["_srcphoto"] = take(prev_p, nxt)
    for d in deals:
        d.pop("_pos", None)
    return deals

def dedupe(deals):
    seen = {}
    for d in deals:
        k = norm_key(d["addr"])
        if k not in seen:
            seen[k] = d
        else:
            # manter o que tem foto / mais specs
            cur = seen[k]
            if (d.get("_srcphoto") and not cur.get("_srcphoto")) or len(d["specs"]) > len(cur["specs"]):
                d.setdefault("source", cur["source"])
                seen[k] = d
    return list(seen.values())

def host_photos(deals):
    try:
        from PIL import Image; have_pil = True
    except Exception:
        have_pil = False
    os.makedirs(IMGDIR, exist_ok=True)
    for d in deals:
        u = d.pop("_srcphoto", None); d["img"] = ""
        if not u: continue
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=25).read()
            if len(raw) < 8000: continue
            fname = re.sub(r'[^a-z0-9]+', '-', d["addr"].lower()).strip('-')[:60] + ".jpg"
            path = os.path.join(IMGDIR, fname)
            if have_pil:
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                if im.width > 800: im = im.resize((800, int(im.height*800/im.width)))
                im.save(path, "JPEG", quality=78)
            else:
                open(path, "wb").write(raw)
            d["img"] = PAGES + "images/listings/" + fname
        except Exception as e:
            print("  foto falhou:", d["addr"][:30], e)
    return deals

if __name__ == "__main__":
    files = sys.argv[1:]
    all_deals = []
    for f in files:
        ds = parse_email(f)
        src = ds[0]["source"] if ds else "?"
        print(f"{os.path.basename(f)[:20]}: {len(ds)} deals ({src})")
        all_deals += ds
    before = len(all_deals)
    all_deals = dedupe(all_deals)
    print(f"dedup: {before} -> {len(all_deals)} (removidos {before-len(all_deals)} repetidos)")
    # markup (por fonte: Beau Roberts tem regra fixa)
    for d in all_deals:
        d["ask"] = our_price(d["wholesale"], d.get("source"))
    # ordenar por condado e preço
    all_deals.sort(key=lambda d: (COUNTY_ORDER.index(d["county"]) if d["county"] in COUNTY_ORDER else 99, -d["ask"]))
    all_deals = host_photos(all_deals)
    # contagem por condado
    from collections import Counter
    cc = Counter(d["county"] for d in all_deals)
    print("por condado:", dict(cc))
    json.dump(all_deals, open(OUTJSON, "w"), ensure_ascii=False, indent=1)
    print(f"total {len(all_deals)} -> {OUTJSON} ({sum(1 for d in all_deals if d.get('img'))} com foto)")
