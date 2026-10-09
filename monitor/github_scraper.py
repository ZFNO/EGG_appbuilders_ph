#!/usr/bin/env python3
"""
github_scraper.py - scrape GitHub profiles (via the `gh` CLI) for participants.

INPUT : participants_flat.json  (flattened AppBuilders rows; one row per person)
OUTPUT: github_scraped.json     (single file, keyed by username)

Per user we collect:
  profile  : username, name, about, company, location, blog, twitter_username,
             hireable, created_at, updated_at, avatar_url, html_url
  socials  : followers[full], follower_count, following[full], following_count
  aggregate: public_repos, public_gists, repo_count, total_stars, total_forks,
             languages{}, most_recent_push, account_age_days
  repos[]  : reponame, repo_link, repo_description, stars, commits (COUNT),
             language, forks_count, watchers_count, open_issues_count, topics[],
             license, created_at, updated_at, pushed_at, default_branch,
             is_fork, is_archived, size
  _scraped_at

SAFETY (anti-botting):
  - single-threaded
  - jittered delay between calls
  - exponential backoff on 403/429 honoring X-RateLimit-Reset / Retry-After
  - /rate_limit pre-check; pause when core remaining is low
  - checkpoint/resume: re-running skips already-scraped usernames

USAGE:
  python github_scraper.py                 # scrape all not-yet-done users
  python github_scraper.py --limit 5       # only first 5 pending
  python github_scraper.py --only someuser # a single username
  python github_scraper.py --refresh       # re-scrape even if already done
  python github_scraper.py --dry-run       # list targets, do nothing
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FLAT = os.path.join(HERE, "participants_flat.json")
OUT = os.path.join(HERE, "github_scraped.json")

# ---- safety knobs ---------------------------------------------------------
DELAY_MIN, DELAY_MAX = 1.5, 4.0      # jittered seconds between API calls
BACKOFF_BASE = 5.0                   # seconds, doubles each retry
MAX_RETRIES = 4
RATELIMIT_LOW = 30                   # pause if core remaining <= this
RATELIMIT_PAUSE = 90                 # seconds to wait when low/near-reset
PER_PAGE = 100

_START = time.time()


# ---------------------------------------------------------------------------
# live logging helpers
# ---------------------------------------------------------------------------
def _stamp():
    el = time.time() - _START
    return f"[{int(el)//3600:02d}:{(int(el)%3600)//60:02d}:{int(el)%60:02d}]"


def log(*a):
    print(f"{_stamp()} {' '.join(str(x) for x in a)}", flush=True)


# ---------------------------------------------------------------------------
# gh wrappers
# ---------------------------------------------------------------------------
def gh_api(path: str, *, paginate=False):
    """Call `gh api <path>` and return parsed JSON (or list of pages)."""
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if paginate:
        cmd = ["gh", "api", "--paginate", "-H",
               "Accept: application/vnd.github+json", path]
    attempt = 0
    while True:
        attempt += 1
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        except FileNotFoundError:
            raise SystemExit("ERROR: `gh` CLI not found on PATH.")

        if proc.returncode == 0:
            text = (proc.stdout or "").strip()
            if not text:
                return None
            if paginate:
                return _parse_paginated(text)
            return json.loads(text)

        err = (proc.stderr or proc.stdout or "").strip()
        low = err.lower()

        retry_after = _header_retry_after(err)
        if ("rate limit" in low or "403" in err or "429" in err
                or "abuse" in low or "secondary" in low):
            if attempt > MAX_RETRIES:
                log(f"    ! giving up after {attempt-1} retries: {err[:120]}")
                return None
            wait = retry_after if retry_after else BACKOFF_BASE * (2 ** (attempt - 1))
            log(f"    ~ rate/abuse limit, sleeping {wait:.0f}s (attempt {attempt})")
            time.sleep(wait)
            continue

        if "404" in err or "not found" in low:
            return None

        if attempt > MAX_RETRIES:
            log(f"    ! gh error: {err[:160]}")
            return None
        wait = BACKOFF_BASE * (2 ** (attempt - 1))
        log(f"    ~ transient error, retrying in {wait:.0f}s: {err[:100]}")
        time.sleep(wait)


def _header_retry_after(err: str):
    m = re.search(r"retry-after:\s*(\d+)", err, re.I)
    if m:
        return float(m.group(1)) + 1
    m = re.search(r"x-ratelimit-reset:\s*(\d+)", err, re.I)
    if m:
        reset = int(m.group(1))
        delta = reset - int(time.time())
        if 0 < delta < 3600:
            return delta + 2
    return None


def _parse_paginated(text: str):
    """gh --paginate can emit ']\\n[' between pages. Rejoin into one list."""
    text = re.sub(r"\]\s*\[", ",", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        out = []
        dec = json.JSONDecoder()
        idx = 0
        text = text.strip()
        while idx < len(text):
            ch = text[idx]
            if ch in "[],":
                idx += 1
                continue
            obj, end = dec.raw_decode(text, idx)
            if isinstance(obj, list):
                out.extend(obj)
            else:
                out.append(obj)
            idx = end
        return out


def graphql(query: str, variables: dict):
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        cmd += ["-f", f"{k}={v}"]
    attempt = 0
    while True:
        attempt += 1
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                return None
        err = (proc.stderr or proc.stdout or "").strip()
        if attempt > MAX_RETRIES:
            log(f"    ! graphql error: {err[:160]}")
            return None
        wait = BACKOFF_BASE * (2 ** (attempt - 1))
        time.sleep(wait)


def rate_limit_remaining():
    data = gh_api("rate_limit")
    try:
        core = data["resources"]["core"]
        return core["remaining"], core["reset"]
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# parsers
# ---------------------------------------------------------------------------
USER_RE = re.compile(r"github\.com/([A-Za-z0-9-]+)", re.I)


def extract_username(url: str):
    if not url:
        return None
    m = USER_RE.search(url)
    if not m:
        return None
    u = m.group(1)
    if u.lower() in {"orgs", "topics", "features", "about", "apps"}:
        return None
    return u


def scrape_commits_count(username: str, reponame: str):
    q = """
    query($owner:String!,$name:String!){
      repository(owner:$owner,name:$name){
        defaultBranchRef{ target{ ... on Commit { history{ totalCount } } } }
      }
    }
    """
    data = graphql(q, {"owner": username, "name": reponame})
    try:
        return data["data"]["repository"]["defaultBranchRef"]["target"]["history"]["totalCount"]
    except (TypeError, KeyError):
        return None


def scrape_user(username: str, idx_label: str = "") -> dict | None:
    log(f"  >> {username} {idx_label}")

    prof = gh_api(f"users/{username}")
    if not prof:
        log(f"    ! no profile (404?)")
        return None
    log(f"     profile ok  (name={prof.get('name')!r} repos={prof.get('public_repos')} "
        f"followers={prof.get('followers')} following={prof.get('following')})")

    followers = gh_api(f"users/{username}/followers?per_page={PER_PAGE}", paginate=True) or []
    log(f"     followers: {len(followers)}")
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    following = gh_api(f"users/{username}/following?per_page={PER_PAGE}", paginate=True) or []
    log(f"     following: {len(following)}")
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    repos_raw = gh_api(f"users/{username}/repos?per_page={PER_PAGE}&sort=updated", paginate=True) or []
    log(f"     repos: {len(repos_raw)}  -> counting commits...")
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    repos = []
    lang_counts = {}
    total_stars = 0
    total_forks = 0
    most_recent_push = None
    n = len(repos_raw)
    for i, r in enumerate(repos_raw, 1):
        lang = r.get("language")
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        stars = r.get("stargazers_count", 0) or 0
        forks = r.get("forks_count", 0) or 0
        total_stars += stars
        total_forks += forks
        pushed = r.get("pushed_at") or r.get("updated_at")
        if pushed and (most_recent_push is None or pushed > most_recent_push):
            most_recent_push = pushed

        lic = r.get("license") or {}
        commits = scrape_commits_count(username, r["name"])
        log(f"       [{i:>3}/{n}] {r['name']:<40.40} stars={stars:<4} commits={commits}")

        repos.append({
            "reponame": r["name"],
            "repo_link": r.get("html_url"),
            "repo_description": r.get("description"),
            "stars": stars,
            "commits": commits,
            "language": lang,
            "forks_count": forks,
            "watchers_count": r.get("watchers_count"),
            "open_issues_count": r.get("open_issues_count"),
            "topics": r.get("topics", []),
            "license": (lic.get("spdx_id") if lic else None),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "pushed_at": r.get("pushed_at"),
            "default_branch": r.get("default_branch"),
            "is_fork": r.get("fork", False),
            "is_archived": r.get("archived", False),
            "size": r.get("size"),
        })
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    age_days = None
    if prof.get("created_at"):
        try:
            created = datetime.strptime(prof["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - created).days
        except Exception:
            pass

    rec = {
        "username": prof.get("login", username),
        "name": prof.get("name"),
        "about": prof.get("bio"),
        "company": prof.get("company"),
        "location": prof.get("location"),
        "blog": prof.get("blog"),
        "twitter_username": prof.get("twitter_username"),
        "hireable": prof.get("hireable"),
        "created_at": prof.get("created_at"),
        "updated_at": prof.get("updated_at"),
        "avatar_url": prof.get("avatar_url"),
        "html_url": prof.get("html_url"),
        "followers": [f.get("login") for f in followers],
        "follower_count": prof.get("followers", len(followers)),
        "following": [f.get("login") for f in following],
        "following_count": prof.get("following", len(following)),
        "public_repos": prof.get("public_repos"),
        "public_gists": prof.get("public_gists"),
        "repo_count": len(repos),
        "total_stars": total_stars,
        "total_forks": total_forks,
        "languages": lang_counts,
        "most_recent_push": most_recent_push,
        "account_age_days": age_days,
        "repos": repos,
        "_scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    log(f"     DONE {username}: {len(repos)} repos, {total_stars} stars, "
        f"{follower_count_safe(rec)} followers")
    return rec


def follower_count_safe(rec):
    return rec.get("follower_count")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def load_targets(flat_path=FLAT):
    with open(flat_path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    targets = []
    seen = set()
    for row in rows:
        u = extract_username(row.get("github") or "")
        if not u:
            continue
        key = u.lower()
        if key in seen:
            continue
        seen.add(key)
        targets.append({
            "username": u,
            "participant_index": row.get("index"),
            "participant_name": row.get("name"),
            "github": row.get("github"),
        })
    return targets


def load_done(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(out, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    targets = load_targets(FLAT)
    log(f"flat rows with a github link: {len(targets)}")

    results = load_done(OUT)
    done_set = {k.lower() for k in results if not k.startswith("_")}
    log(f"already scraped: {len(done_set)}")

    if args.only:
        targets = [t for t in targets if t["username"].lower() == args.only.lower()]
        if not targets:
            log(f"  --only {args.only} not found among targets")
            return 1

    pending = targets if args.refresh else [
        t for t in targets if t["username"].lower() not in done_set
    ]

    if args.limit is not None:
        pending = pending[:args.limit]

    log(f"to scrape this run: {len(pending)}")
    if args.dry_run:
        for t in pending[:50]:
            log(f"   {t['username']}  <- {t['participant_name']} (row {t['participant_index']})")
        if len(pending) > 50:
            log(f"   ... +{len(pending)-50} more")
        return 0

    if not pending:
        log("nothing to do.")
        return 0

    done = 0
    failed = 0
    total = len(pending)
    run_start = time.time()
    for t in pending:
        u = t["username"]

        remaining, _ = rate_limit_remaining()
        if remaining is not None:
            log(f"  (rate limit remaining: {remaining})")
            if remaining <= RATELIMIT_LOW:
                log(f"  ~ core rate limit low ({remaining}); pausing {RATELIMIT_PAUSE}s")
                time.sleep(RATELIMIT_PAUSE)

        i = done + failed + 1
        pct = 100.0 * i / total
        rate = (time.time() - run_start) / max(i, 1)
        eta = (total - i) * rate
        log(f"[{i}/{total} {pct:4.1f}%] ETA {int(eta)//60}m{int(eta)%60:02d}s  "
            f"<{t['participant_name']}>")

        rec = scrape_user(u, idx_label=f"(row {t['participant_index']})")
        if rec:
            rec["participant_index"] = t["participant_index"]
            rec["participant_name"] = t["participant_name"]
            results[u] = rec
            done += 1
        else:
            results.setdefault("_failed", [])
            if u not in results["_failed"]:
                results["_failed"].append(u)
            failed += 1
        save(results, OUT)
        log(f"     [saved] {OUT}  (ok={done} failed={failed})")

        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    log(f"\ndone. +{done} scraped, {failed} failed. total records: {len(done_set) + done}")
    log(f"[written] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
