# reddit-collector

A minimal, **read-only** Reddit research collector for a personal quant/AI knowledge base.

## What it does (complete behavior)

Once per week it requests the weekly top posts of three public subreddits:

https://oauth.reddit.com/r/quant/top?t=week&limit=25 
https://oauth.reddit.com/r/algotrading/top?t=week&limit=25 https://oauth.reddit.com/r/MachineLearning/top?t=week&limit=25

From each response it stores: post title, permalink, author name, creation time,
score, comment count, and (for text posts) the post body — into a private local
SQLite database. It may open an individual post's comment JSON for a handful of
posts per week (`GET /r/<sub>/comments/<id>`) to read discussion context.

## What it NEVER does

- No submissions, comments, edits, votes, saves, follows
- No chat or direct messages, no user interaction of any kind
- No moderator actions; no access to private/quarantined subreddits
- No data resale, no redistribution of Reddit content

## Operational details

- OAuth2 password grant for a single script app on one account (read-only use)
- Descriptive User-Agent in Reddit's documented format:
  `platform:app:version (by /u/<username>)`
- ≤10 requests/week (free tier allows 100 req/min); exponential backoff on 429
- Fallback channel: public RSS (`/r/<sub>/top/.rss?t=week`) with 120s spacing
  and browser-style headers, used only while OAuth approval is pending
- Data retention: only short derived research summaries are kept long-term;
  raw API/RSS snapshots are purged within 48 hours (Data API Terms deletion
  recommendations); deleted-on-Reddit content is deleted from the archive

## Scope

Three public subreddits only: r/quant, r/algotrading, r/MachineLearning.
Purpose: personal, non-commercial research — archiving high-signal quantitative
finance / AI research discussions into a searchable private knowledge base.
No monetization, no ads, no third-party data sharing.

## Files

- `collect_reddit.py` — the collector (OAuth with RSS fallback), stdlib-only Python
