# Privacy Policy — reddit-collector

Last updated: 2026-10-29

## What this tool collects
This is a personal, read-only research collector. It reads the weekly top-post
listings of three public subreddits (r/quant, r/algotrading, r/MachineLearning)
through Reddit's official API. For each post it stores: title, permalink,
author username, creation time, score, comment count, and the body text of
self-posts. Nothing else is collected: no private messages, no email addresses,
no location data, no user profiles.

## How data is stored
Data is stored in a private local SQLite database on a personal server. It is
not shared with any third party, not sold, not published, and not used for
advertising or profiling of any Reddit user.

## Retention and deletion
- Raw API responses are purged within 48 hours of collection.
- Long-term records are limited to short derived research summaries
  (<=120 characters) and topic tags, kept for personal reading notes.
- Content that is deleted on Reddit is deleted from this archive.
- The entire archive can be deleted on request at any time.

## What this tool never does
It never posts, comments, votes, saves, follows, or sends messages. It performs
GET requests on public listing endpoints only.

## Contact
cowhello163@gmail.com
