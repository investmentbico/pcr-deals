#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alerta de CASAS NOVAS pros Cash Buyers — roda NA NUVEM (GitHub Actions) sempre
que o deals.json muda (o coletor adicionou imoveis). Compara o deals.json atual
com sent_keys.json (o que ja foi avisado) e manda um e-mail SO das casas novas.
Depois grava as novas em sent_keys.json (o workflow faz o commit de volta).

- Nao manda nada se nao houver casa nova.
- Usa envio TRANSACIONAL (entrega confiavel) pra lista de Cash Buyers.
Requer env BREVO_API_KEY (secret do repo).
"""
import os, re, json, urllib.request

API   = os.environ.get("BREVO_API_KEY", "").strip()
LIST  = os.environ.get("BREVO_LIST_ID", "3")
SENDER= os.environ.get("BREVO_SENDER_EMAIL", "info@propertycashrelief.net")
NAME  = os.environ.get("BREVO_SENDER_NAME", "Property Cash Relief")
PAGE  = "https://investmentbico.github.io/pcr-deals/"
LOGO  = "https://investmentbico.github.io/pcr-deals/images/logo.png"
WA    = "https://wa.me/19546434831?text=Hi%21%20I%20saw%20the%20new%20South%20Florida%20deals%20on%20Property%20Cash%20Relief%20and%20I%27d%20like%20to%20know%20more."
NAVY, GREEN, MUTED = "#0a3d5e", "#15803d", "#5b6b73"
HERE  = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "sent_keys.json")
MAX_IN_EMAIL = 30  # se vier um lote gigante, mostra os 30 mais caros e o resto na pagina

def usd(n): return "${:,}".format(int(round(n or 0)))

# MESMA normalizacao do coletor (coletor_deals.py norm_key) — chave estavel por endereco
def norm_key(addr):
    a = (addr or "").lower().strip()
    a = re.sub(r',?\s*fl\.?\s*\d*.*$', '', a)
    repl = {r'\b(st|street)\b':'st', r'\b(ave|avenue)\b':'ave', r'\b(ter|terr|terrace)\b':'ter',
            r'\b(dr|drive)\b':'dr', r'\b(rd|road)\b':'rd', r'\b(ct|court)\b':'ct',
            r'\b(pl|place)\b':'pl', r'\b(blvd|boulevard)\b':'blvd', r'\b(ln|lane)\b':'ln'}
    for k,v in repl.items(): a = re.sub(k, v, a)
    return re.sub(r'[^a-z0-9]+', ' ', a).strip()

def brevo(path, payload=None, method="GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request("https://api.brevo.com/v3/"+path, data=data,
        headers={"api-key": API, "content-type": "application/json", "accept": "application/json"}, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=30).read() or b"{}")

def contacts():
    out=[]; off=0
    while True:
        d=brevo(f"contacts/lists/{LIST}/contacts?limit=50&offset={off}")
        cs=d.get("contacts",[]); out+=[c["email"] for c in cs if not c.get("emailBlacklisted")]
        if len(cs)<50: break
        off+=50
    return out

def deal_row(d):
    specs=" · ".join((d.get("specs") or [])[:2])
    arv=f" · ARV ${d['arv']}" if d.get("arv") else ""
    img=f'<img src="{d["img"]}" width="120" style="border-radius:6px;display:block" alt="">' if d.get("img") else ""
    county=f'<span style="color:{MUTED};font-size:12px;"> · {d.get("county","")} County</span>' if d.get("county") else ""
    return f"""<tr><td style="padding:12px 0;border-bottom:1px solid #e3e8ea;">
      <table role="presentation" width="100%"><tr>
        <td width="120" valign="top">{img}</td>
        <td valign="top" style="padding-left:12px;font-family:Arial,sans-serif;">
          <div style="font-weight:bold;color:{NAVY};font-size:15px;">{d.get("addr","")}{county}</div>
          <div style="color:#22343d;font-size:13px;margin:3px 0;">{specs}{arv}</div>
          <div style="font-weight:bold;color:{GREEN};font-size:17px;">Asking {usd(d.get("ask"))}</div>
          <a href="tel:+19546434831" style="color:{GREEN};font-weight:bold;font-size:13px;text-decoration:none;">Text / Call 954-643-4831</a>
        </td></tr></table></td></tr>"""

def build(new_deals, total_new):
    top=sorted(new_deals, key=lambda d:-(d.get("ask") or 0))[:MAX_IN_EMAIL]
    rows="".join(deal_row(d) for d in top)
    more = f'<div style="text-align:center;color:{MUTED};font-size:13px;padding:6px 0;">+ {total_new-len(top)} more just added — see them all on the page</div>' if total_new>len(top) else ""
    label = "NEW DEAL JUST ADDED" if total_new==1 else f"{total_new} NEW DEALS JUST ADDED"
    return f"""<!DOCTYPE html><html><body style="margin:0;background:#f4f6f7;font-family:Arial,sans-serif;">
<table role="presentation" width="100%" bgcolor="#f4f6f7"><tr><td align="center" style="padding:16px;">
<table role="presentation" width="600" bgcolor="#ffffff" style="max-width:600px;">
  <tr><td bgcolor="{NAVY}" style="height:8px;"></td></tr>
  <tr><td align="center" style="padding:22px 24px 8px;border-bottom:3px solid {NAVY};">
    <img src="{LOGO}" width="250" alt="Property Cash Relief" style="display:block;margin:0 auto;">
    <div style="font-style:italic;color:{NAVY};font-size:15px;margin-top:8px;">Off-Market Deals. Cash Fast. No Hassle.</div>
    <a href="{WA}" style="display:inline-block;margin-top:12px;background:#25D366;color:#053b1e;font-weight:bold;text-decoration:none;padding:10px 22px;border-radius:22px;font-size:15px;">&#128172; Chat on WhatsApp</a>
  </td></tr>
  <tr><td bgcolor="{GREEN}" align="center" style="padding:12px;color:#fff;font-weight:bold;letter-spacing:1px;">&#128293; {label}</td></tr>
  <tr><td style="padding:10px 24px 0;color:{MUTED};font-size:13px;">Fresh off-market properties just added to our list. First come, first served — call fast.</td></tr>
  <tr><td style="padding:0 24px;"><table role="presentation" width="100%">{rows}</table>{more}</td></tr>
  <tr><td align="center" style="padding:22px 24px;">
    <a href="{PAGE}" style="background:{GREEN};color:#fff;text-decoration:none;font-weight:bold;font-size:17px;padding:14px 30px;border-radius:8px;">See all deals &rarr;</a>
  </td></tr>
  <tr><td style="padding:18px 24px;border-top:3px solid {NAVY};color:#9aa6ab;font-size:11px;line-height:1.5;">
    Property Cash Relief &middot; 8240 Exchange Dr Suite G4, Orlando, FL 32809 &middot; <a href="{PAGE}" style="color:{NAVY};">propertycashrelief.net</a><br>
    You're on our investor list. All properties are sold AS-IS; figures (ARV, sqft, price) are estimates to be independently verified; nothing here is brokerage/legal/investment advice; deals offered by assignment of our contractual interest; prices/availability subject to change.
    <a href="mailto:info@propertycashrelief.net?subject=Unsubscribe" style="color:{MUTED};">Unsubscribe</a>
  </td></tr>
</table></td></tr></table></body></html>"""

def main():
    if not API: print("BREVO_API_KEY ausente"); return
    deals = json.load(open(os.path.join(HERE, "deals.json"), encoding="utf-8"))
    cur_keys = {norm_key(d.get("addr","")) for d in deals if d.get("addr")}

    # estado do que ja foi avisado
    if os.path.exists(STATE):
        try: sent = set(json.load(open(STATE, encoding="utf-8")))
        except Exception: sent = set()
    else:
        # PRIMEIRA VEZ: semeia com tudo que ja esta no ar (nao avisa retroativo)
        json.dump(sorted(cur_keys), open(STATE, "w"), ensure_ascii=False, indent=0)
        print(f"seed inicial: {len(cur_keys)} casas marcadas como ja conhecidas — nenhum e-mail enviado.")
        return

    new_deals = [d for d in deals if norm_key(d.get("addr","")) not in sent]
    if not new_deals:
        print("Nenhuma casa nova — nada enviado."); return

    emails = contacts()
    if not emails:
        print("Lista Cash Buyers vazia — nada enviado.");
    else:
        n = len(new_deals)
        html = build(new_deals, n)
        subject = ("New off-market deal in South Florida" if n==1
                   else f"{n} new off-market deals in South Florida")
        ok=0
        for em in emails:
            try:
                brevo("smtp/email", {"sender":{"name":NAME,"email":SENDER},"to":[{"email":em}],
                                     "subject":subject,"htmlContent":html,"tags":["new-listings-alert"],
                                     "headers":{"List-Unsubscribe":"<mailto:info@propertycashrelief.net?subject=Unsubscribe>"}}, "POST"); ok+=1
            except Exception as e: print("falhou", em, e)
        print(f"Alerta de {n} casa(s) nova(s) enviado a {ok}/{len(emails)} cash buyers.")

    # marca as novas como avisadas (mesmo que a lista esteja vazia, evita reenvio futuro)
    sent |= cur_keys
    json.dump(sorted(sent), open(STATE, "w"), ensure_ascii=False, indent=0)

if __name__ == "__main__":
    main()
