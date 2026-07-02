#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envio diário dos deals pros Cash Buyers — roda NA NUVEM (GitHub Actions),
independente do Mac. Lê deals.json (deste repo), monta um e-mail COMPACTO
(evita o corte do Gmail em ~102KB) e envia TRANSACIONAL via Brevo pra lista #3.
Requer env BREVO_API_KEY (secret do repo).
"""
import os, json, urllib.request

API   = os.environ.get("BREVO_API_KEY", "").strip()
LIST  = os.environ.get("BREVO_LIST_ID", "3")
SENDER= os.environ.get("BREVO_SENDER_EMAIL", "info@propertycashrelief.net")
NAME  = os.environ.get("BREVO_SENDER_NAME", "Property Cash Relief")
PAGE  = "https://investmentbico.github.io/pcr-deals/"
LOGO  = "https://investmentbico.github.io/pcr-deals/images/logo.png"
WA    = "https://wa.me/19546434831?text=Hi%21%20I%20saw%20the%20South%20Florida%20deals%20on%20Property%20Cash%20Relief%20and%20I%27d%20like%20to%20know%20more."
NAVY, GREEN, MUTED = "#0a3d5e", "#15803d", "#5b6b73"
TOP_N = 12  # quantos deals mostrar no e-mail (o resto fica na página)

def usd(n): return "${:,}".format(int(round(n or 0)))

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
    return f"""<tr><td style="padding:12px 0;border-bottom:1px solid #e3e8ea;">
      <table role="presentation" width="100%"><tr>
        <td width="120" valign="top">{img}</td>
        <td valign="top" style="padding-left:12px;font-family:Arial,sans-serif;">
          <div style="font-weight:bold;color:{NAVY};font-size:15px;">{d.get("addr","")}</div>
          <div style="color:#22343d;font-size:13px;margin:3px 0;">{specs}{arv}</div>
          <div style="font-weight:bold;color:{GREEN};font-size:17px;">Asking {usd(d.get("ask"))}</div>
          <a href="tel:+19546434831" style="color:{GREEN};font-weight:bold;font-size:13px;text-decoration:none;">Text / Call 954-643-4831</a>
        </td></tr></table></td></tr>"""

def build(deals):
    counties={}
    for d in deals: counties[d.get("county","Other")]=counties.get(d.get("county","Other"),0)+1
    summ=" · ".join(f"{c} ({n})" for c,n in list(counties.items())[:6])
    top=sorted(deals, key=lambda d:-(d.get("ask") or 0))[:TOP_N]
    rows="".join(deal_row(d) for d in top)
    n=len(deals)
    return f"""<!DOCTYPE html><html><body style="margin:0;background:#f4f6f7;font-family:Arial,sans-serif;">
<table role="presentation" width="100%" bgcolor="#f4f6f7"><tr><td align="center" style="padding:16px;">
<table role="presentation" width="600" bgcolor="#ffffff" style="max-width:600px;">
  <tr><td bgcolor="{NAVY}" style="height:8px;"></td></tr>
  <tr><td align="center" style="padding:22px 24px 8px;border-bottom:3px solid {NAVY};">
    <img src="{LOGO}" width="250" alt="Property Cash Relief" style="display:block;margin:0 auto;">
    <div style="font-style:italic;color:{NAVY};font-size:15px;margin-top:8px;">Off-Market Deals. Cash Fast. No Hassle.</div>
    <a href="{WA}" style="display:inline-block;margin-top:12px;background:#25D366;color:#053b1e;font-weight:bold;text-decoration:none;padding:10px 22px;border-radius:22px;font-size:15px;">&#128172; Chat on WhatsApp</a>
  </td></tr>
  <tr><td bgcolor="{NAVY}" align="center" style="padding:12px;color:#fff;font-weight:bold;letter-spacing:1px;">SOUTH FLORIDA WHOLESALE DEALS &middot; {n} AVAILABLE</td></tr>
  <tr><td style="padding:8px 24px;color:{MUTED};font-size:13px;">{summ}</td></tr>
  <tr><td style="padding:0 24px;"><table role="presentation" width="100%">{rows}</table></td></tr>
  <tr><td align="center" style="padding:22px 24px;">
    <a href="{PAGE}" style="background:{GREEN};color:#fff;text-decoration:none;font-weight:bold;font-size:17px;padding:14px 30px;border-radius:8px;">View all {n} deals &rarr;</a>
  </td></tr>
  <tr><td style="padding:18px 24px;border-top:3px solid {NAVY};color:#9aa6ab;font-size:11px;line-height:1.5;">
    Property Cash Relief &middot; 8240 Exchange Dr Suite G4, Orlando, FL 32809 &middot; <a href="{PAGE}" style="color:{NAVY};">propertycashrelief.net</a><br>
    You're on our investor list. All properties are sold AS-IS; figures (ARV, sqft, price) are estimates to be independently verified; nothing here is brokerage/legal/investment advice; deals offered by assignment of our contractual interest; prices/availability subject to change.
    <a href="mailto:info@propertycashrelief.net?subject=Unsubscribe" style="color:{MUTED};">Unsubscribe</a>
  </td></tr>
</table></td></tr></table></body></html>"""

def main():
    if not API: print("BREVO_API_KEY ausente"); return
    here=os.path.dirname(os.path.abspath(__file__))
    deals=json.load(open(os.path.join(here,"deals.json"), encoding="utf-8"))
    emails=contacts()
    if not emails: print("Lista vazia — nada enviado."); return
    html=build(deals); subject="South Florida Wholesale Deals — Property Cash Relief"
    ok=0
    for em in emails:
        try:
            brevo("smtp/email", {"sender":{"name":NAME,"email":SENDER},"to":[{"email":em}],
                                 "subject":subject,"htmlContent":html,"tags":["cash-buyers-daily"],
                                 "headers":{"List-Unsubscribe":"<mailto:info@propertycashrelief.net?subject=Unsubscribe>"}}, "POST"); ok+=1
        except Exception as e: print("falhou",em,e)
    print(f"Enviado {ok}/{len(emails)} cash buyers | {len(deals)} deals | email {len(html)} bytes")

if __name__ == "__main__":
    main()
