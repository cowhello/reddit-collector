#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Forum collector (r/quant, r/algotrading, r/MachineLearning).

- Primary channel: official Reddit OAuth API (credentials in
  .proxy/reddit_oauth.json: {"client_id","client_secret","username","password"})
- OAuth endpoint: oauth.reddit.com/r/<sub>/top?t=week&limit=25
  (returns score / num_comments)
- Fallback channel: public RSS weekly top (/r/<sub>/top/.rss?t=week);
  no score available, entries are tagged score=null for later backfill
- Ingest rule: only posts with score >= 50 (skipped in RSS mode)
- r/MachineLearning: keep only [R]/[D] prefixed posts; [P] project posts
  get the "Tools" tag downstream
- Rate limits: OAuth <= 60 req/min (be conservative, use 30);
  RSS spacing >= 45s to avoid 429
Usage: python3 tools/collect_reddit.py [--rss-only]
"""
import base64
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

# Root of the local knowledge-base workspace (adjust to your own path)
ROOT = "/root/quant_intel"
STAGING = os.path.join(ROOT, "staging")
RAW = os.path.join(ROOT, "raw")
CREDS = os.path.join(ROOT, ".proxy", "reddit_oauth.json")
CA = os.path.join(ROOT, ".certs", "ca-bundle.crt")
PROXY = "http://127.0.0.1:7890"
UA_OAUTH = "quant-intel-bot/0.1 (research aggregator; contact: local)"  # honest UA for official API
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"  # browser UA for RSS/HTML to avoid 429
SUBS = [("r/quant", "quant"), ("r/algotrading", "quant"), ("r/MachineLearning", "ai")]

import ssl
ctx = ssl.create_default_context(cafile=CA)


class TextExtract(HTMLParser):
    SKIP = {"script", "style"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in ("p", "br", "li", "div"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(s):
    s = s.replace("<![CDATA[", "").replace("]]>", "")
    p = TextExtract()
    try:
        p.feed(s)
    except Exception:
        pass
    t = re.sub(r"[ \t]+", " ", "".join(p.parts))
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def load_creds():
    if not os.path.exists(CREDS):
        return None
    return json.load(open(CREDS, encoding="utf-8"))


def get_token(c):
    """Password grant (script app)."""
    data = urllib.parse.urlencode({
        "grant_type": "password", "username": c["username"], "password": c["password"]}).encode()
    basic = base64.b64encode(f"{c['client_id']}:{c['client_secret']}".encode()).decode()
    req = urllib.request.Request("https://www.reddit.com/api/v1/access_token", data=data,
                                 headers={"Authorization": f"Basic {basic}", "User-Agent": UA_OAUTH})
    op = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
        urllib.request.HTTPSHandler(context=ctx))
    try:
        with op.open(req, timeout=30) as r:
            return json.loads(r.read()).get("access_token")
    except Exception as e:
        print(f"Failed to obtain token: {e}")
        return None


def api_get(url, token, timeout=30):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "User-Agent": UA_OAUTH,
        "Accept": "application/json"})
    op = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
        urllib.request.HTTPSHandler(context=ctx))
    try:
        with op.open(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return {}, e.code
    except Exception:
        return {}, 0


def save_raw(sub, kind, url, body):
    d = os.path.join(RAW, sub.replace("/", "_"), datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{abs(hash(url)) % 10**10}.{kind}")
    with open(p, "wb") as f:
        f.write(body)
    return p


def make_item(sub, side, url, title, score, num_comments, author, created_utc,
              text, raw_path, lang="en", extra=None):
    return {
        "source_name": sub, "source_type": "forum", "side": side,
        "url": url, "title": title, "author": author,
        "published_at": datetime.fromtimestamp(created_utc, timezone.utc).isoformat()
        if created_utc else "",
        "lang": lang, "popularity": score, "raw_path": raw_path,
        "text": text[:60000], "text_len": len(text),
        "content_hash": hashlib.sha256(text.encode()).hexdigest() if text else "",
        "extra": {"num_comments": num_comments, **(extra or {})},
    }


def collect_oauth(token):
    rows = []
    for sub, side in SUBS:
        url = f"https://oauth.reddit.com/{sub}/top?t=week&limit=25"
        data, code = api_get(url, token)
        if code != 200:
            print(f"[{sub}] OAuth failed, code={code}")
            time.sleep(5)
            continue
        save_raw(sub, "json", url, json.dumps(data).encode())
        for child in (data.get("data", {}).get("children") or []):
            d = child.get("data", {})
            title = d.get("title", "")
            if sub == "r/MachineLearning":
                m = re.match(r"\s*\[([RPD])\]", title)
                if not m:
                    continue
                prefix = m.group(1)
            else:
                prefix = ""
            if (d.get("score") or 0) < 50:
                continue
            is_self = d.get("is_self")
            text = html_to_text(d.get("selftext_html") or "") if is_self else \
                f"[link post] target URL: {d.get('url')}\n{html_to_text(d.get('selftext_html') or '')}"
            rows.append(make_item(
                sub, side, f"https://www.reddit.com{d.get('permalink','')}",
                title, d.get("score"), d.get("num_comments"),
                d.get("author", ""), d.get("created_utc"),
                text, "", extra={"post_hint": "self" if is_self else "link",
                                 "outbound_url": d.get("url") if not is_self else "",
                                 "flair_prefix": prefix}))
        print(f"[{sub}] OAuth staged {sum(1 for r in rows if r['source_name']==sub)} items")
        time.sleep(2)
    return rows


def collect_rss():
    rows = []
    for sub, side in SUBS:
        url = f"https://www.reddit.com/{sub}/top/.rss?t=week"
        body, code, _ = b"", 0, ""
        op = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
            urllib.request.HTTPSHandler(context=ctx))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with op.open(req, timeout=30) as r:
                body, code = r.read(), r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:
            code = 0
        if code != 200:
            print(f"[{sub}] RSS failed, code={code}")
            time.sleep(120)
            continue
        raw_path = save_raw(sub, "xml", url, body)
        x = body.decode("utf-8", "ignore")
        for m in re.finditer(r"<entry>(.*?)</entry>", x, re.S):
            e = m.group(1)

            def f(tag):
                mm = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", e, re.S)
                return html.unescape(mm.group(1)).strip() if mm else ""
            title = f("title")
            if sub == "r/MachineLearning" and not re.match(r"\s*\[([RPD])\]", title):
                continue
            link = f("link")
            if not link:
                lm = re.search(r'<link[^>]+href="([^"]+)"', e)
                link = lm.group(1) if lm else ""
            updated = f("updated") or f("published")
            try:
                dt = parsedate_to_datetime(updated) if "," in updated else datetime.fromisoformat(updated)
                created = dt.timestamp()
            except Exception:
                created = 0
            content = f("content")
            rows.append(make_item(
                sub, side, link, title, None, None, f("author") or f("name"),
                created, html_to_text(content), raw_path,
                extra={"score": None, "note": "RSS fallback: no score/comment counts; score>=50 filter not applied"}))
        print(f"[{sub}] RSS staged {sum(1 for r in rows if r['source_name']==sub)} items")
        time.sleep(120)
    return rows


def main():
    rss_only = "--rss-only" in sys.argv
    creds = load_creds()
    rows = []
    if creds and not rss_only:
        token = get_token(creds)
        if token:
            print("OAuth token obtained")
            rows = collect_oauth(token)
        else:
            print("OAuth failed -> falling back to RSS")
    if not rows:
        rows = collect_rss()
    os.makedirs(STAGING, exist_ok=True)
    out = os.path.join(STAGING, "Reddit_forums.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nTotal {len(rows)} items -> {out}")


if __name__ == "__main__":
    main()