#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coleta dos deals NA NUVEM (GitHub Actions) — independente do Mac.
IMAP (investmentbico@gmail.com) baixa os e-mails dos wholesalers dos ultimos N dias
-> converte cada um pro formato JSON que o collector.py espera -> roda o collector
(reconstroi deals.json + baixa/hospeda as fotos em images/listings) no proprio repo.
O workflow commita deals.json + images/ (o que dispara o alerta de casas novas).

Credenciais via env (secrets do repo): EMAIL_USER, EMAIL_APP_PASSWORD.
TRAVA: nao sobrescreve se 0 e-mails ou se a lista cair abaixo do piso.
"""
import os, re, sys, json, imaplib, email, datetime, subprocess, tempfile
from email.header import decode_header

HERE  = os.path.dirname(os.path.abspath(__file__))
COLLECTOR = os.path.join(HERE, "collector.py")
DEALS = os.path.join(HERE, "deals.json")
PY = sys.executable or "python3"

SENDERS = ["sharkinvestorproperties", "howtofliphousesinmiami", "jefinancial",
           "investorlift", "beau.roberts"]
DAYS = int(os.environ.get("COLLECT_DAYS", "21"))
MIN_DEALS = 25

def dec(s):
    if not s: return ""
    out = ""
    for part, enc in decode_header(s):
        out += part.decode(enc or "utf-8", "ignore") if isinstance(part, bytes) else part
    return out

def bodies(msg):
    html = plain = ""
    if msg.is_multipart():
        for p in msg.walk():
            ct = p.get_content_type()
            if ct == "text/html":
                try: html += p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
                except Exception: pass
            elif ct == "text/plain":
                try: plain += p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
                except Exception: pass
    else:
        try:
            payload = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "ignore")
            if msg.get_content_type() == "text/html": html = payload
            else: plain = payload
        except Exception: pass
    return html, plain

def fetch(days):
    user = os.environ.get("EMAIL_USER", "").strip()
    pw   = os.environ.get("EMAIL_APP_PASSWORD", "").strip()
    host = os.environ.get("EMAIL_IMAP_HOST", "imap.gmail.com")
    if not user or not pw:
        print("ERRO: faltam secrets EMAIL_USER / EMAIL_APP_PASSWORD"); sys.exit(1)
    since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%d-%b-%Y")
    M = imaplib.IMAP4_SSL(host); M.login(user, pw); M.select("INBOX")
    ids = set()
    for frm in SENDERS:
        typ, data = M.search(None, f'(SINCE {since} FROM "{frm}")')
        if data and data[0]: ids.update(data[0].split())
    msgs = []
    for i in sorted(ids, key=lambda x: int(x)):
        typ, d = M.fetch(i, "(RFC822)")
        m = email.message_from_bytes(d[0][1])
        html, plain = bodies(m)
        msgs.append({"sender": dec(m.get("From", "")), "subject": dec(m.get("Subject", "")),
                     "htmlBody": html, "plaintextBody": plain})
    M.logout()
    return msgs

def main():
    prev = 0
    if os.path.exists(DEALS):
        try: prev = len(json.load(open(DEALS)))
        except Exception: prev = 0

    msgs = fetch(DAYS)
    print(f"IMAP: {len(msgs)} e-mail(s) de wholesalers nos ultimos {DAYS} dia(s).")
    if not msgs:
        print("ABORTADO: 0 e-mails — mantem a lista atual."); return

    tmp = tempfile.mkdtemp(prefix="cloud_")
    files = []
    for n, m in enumerate(msgs):
        fp = os.path.join(tmp, f"mail_{n:03d}.json")
        json.dump({"messages": [m]}, open(fp, "w"), ensure_ascii=False)
        files.append(fp)

    r = subprocess.run([PY, COLLECTOR, *files], capture_output=True, text=True)
    print(r.stdout.strip()[-1500:] or r.stderr.strip()[-500:])

    new = 0
    if os.path.exists(DEALS):
        try: new = len(json.load(open(DEALS)))
        except Exception: new = 0
    floor = max(MIN_DEALS, int(prev * 0.40)) if prev else MIN_DEALS
    if new < floor:
        print(f"TRAVA: coletor gerou {new} deals (< piso {floor}, anterior {prev}). Revertendo.")
        subprocess.run(["git", "checkout", "--", "deals.json"], cwd=HERE)
        sys.exit(0)
    print(f"OK: deals.json {prev} -> {new} deals (piso {floor}).")

if __name__ == "__main__":
    main()
