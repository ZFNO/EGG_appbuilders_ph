#!/usr/bin/env python3
"""
github_scraper.py - scrape GitHub profiles via ONE GraphQL request per user.

INPUT : participants_flat.json   (flattened AppBuilders rows; one row per person)
OUTPUT: participants_github.json (single file, keyed by username; auto-created)

One GraphQL query per user returns EVERYTHING:
  profile  : username, name, about, company, location, blog, twitter_username,
             created_at, updated_at, avatar_url, html_url
  socials  : followers[full], follower_count, following[full], following_count
  aggregate: public_repos, repo_count, total_stars, total_forks,
             languages{}, most_recent_push, account_age_days
  repos[]  : reponame, repo_link, repo_description, stars, commits (COUNT),
             language, forks_count, open_issues_count, topics[], license,
             created_at, updated_at, pushed_at, default_branch,
             is_fork, is_archived, size
  _scraped_at
  (+ participant_index / participant_name back-links)

RESUME: usernames already present in participants_github.json are skipped, so
you can Ctrl-C any time and re-run to continue. Written after EVERY user.

SAFETY: single-threaded, jittered delay, GraphQL point pre-check via rate_limit,
exponential backoff on 403/429 honoring retry-after / x-ratelimit-reset.

USAGE:
  python github_scraper.py                 # scrape all not-yet-done users
  python github_scraper.py --limit 5       # first 5 pending
  python github_scraper.py --only someuser # a single username
  python github_scraper.py --refresh       # re-scrape even if already done
  python github_scraper.py --dry-run       # list targets only
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
OUT = os.path.join(HERE, "participants_github.json")

# ---- safety knobs ---------------------------------------------------------
DELAY_MIN, DELAY_MAX = 1.0, 3.0      # jittered seconds between users
BACKOFF_BASE = 5.0
MAX_RETRIES = 5
POINTS_LOW = 100                     # pause if GraphQL points remaining <= this
POINTS_PAUSE = 90
PAGE = 100                           # GraphQL page size

_START = time.time()


# ---------------------------------------------------------------------------
# live logging
# ---------------------------------------------------------------------------
def _stamp():
    el = time.time() - _START
    return f"{int(el)//3600:02d}:{(int(el)%3600)//60:02d}:{int(el)%60:02d}"


def log(msg="", indent=0):
    print(f"[{_stamp()}] {'  ' * indent}{msg}", flush=True)


# ---------------------------------------------------------------------------
# gh graphql
# ---------------------------------------------------------------------------
def gh_graphql(query: str, variables: dict) -> dict | None:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        cmd += ["-f", f"{k}={v}"]
    attempt = 0
    while True:
        attempt += 1
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        except FileNotFoundError:
            raise SystemExit("ERROR: `gh` CLI not found on PATH.")

        text = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()

        if proc.returncode == 0 and text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
            if data is not None and "errors" not in data:
                return data
            # GraphQL-level errors
            if data is not None:
                msgs = "; ".join(e.get("message", "?") for e in data["errors"])
                # "Could not resolve to a User" => 404, don't retry
                if "Could not resolve" in msgs:
                    return {"_notfound": True}
                log(f"    ! graphql errors: {msgs[:160]}", indent=1)
                return None

        low = (err + " " + text).lower()
        retry_after = _retry_after(err + " " + text)
        if ("rate limit" in low or "403" in low or "429" in low
                or "abuse" in low or "secondary" in low or "points" in low):
            if attempt > MAX_RETRIES:
                log(f"    ! giving up after {attempt-1} retries: {err[:120]}", indent=1)
                return None
            wait = retry_after if retry_after else BACKOFF_BASE * (2 ** (attempt - 1))
            log(f"    ~ rate limit, sleeping {wait:.0f}s (attempt {attempt})", indent=1)
            time.sleep(wait)
            continue

        if attempt > MAX_RETRIES:
            log(f"    ! gh error: {(err or text)[:160]}", indent=1)
            return None
        wait = BACKOFF_BASE * (2 ** (attempt - 1))
        log(f"    ~ transient error, retry in {wait:.0f}s: {(err or text)[:100]}", indent=1)
        time.sleep(wait)


def _retry_after(s: str):
    m = re.search(r"retry-after:\s*(\d+)", s, re.I)
    if m:
        return float(m.group(1)) + 1
    m = re.search(r"x-ratelimit-reset:\s*(\d+)", s, re.I)
    if m:
        d = int(m.group(1)) - int(time.time())
        if 0 < d < 3600:
            return d + 2
    return None


def points_remaining():
    """Return remaining GraphQL points (approx via core remaining) or None."""
    try:
        proc = subprocess.run(["gh", "api", "rate_limit"],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        d = json.loads(proc.stdout)["resources"]
        return d.get("graphql", d.get("core", {})).get("remaining")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# query build
# ---------------------------------------------------------------------------
QUERY = """
query($login:String!, $fp:String, $gp:String, $rp:String){
  user(login:$login){
    login name bio company location websiteUrl twitterUsername
    createdAt updatedAt avatarUrl url
    followers(first:100, after:$fp){ totalCount nodes{login} pageInfo{hasNextPage endCursor} }
    following(first:100, after:$gp){ totalCount nodes{login} pageInfo{hasNextPage endCursor} }
    repositories(first:100, after:$rp, privacy:PUBLIC, ownerAffiliations:OWNER,
                 orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{
        name description url stargazerCount forkCount
        issues(states:OPEN){totalCount}
        repositoryTopics(first:100){nodes{topic{name}}}
        licenseInfo{spdxId}
        createdAt updatedAt pushedAt isFork isArchived diskUsage
        primaryLanguage{name}
        defaultBranchRef{name target{... on Commit{history{totalCount}}}}
      }
      pageInfo{hasNextPage endCursor}
    }
  }
}
"""


def glogin(url):
    if not url:
        return None
    m = re.search(r"github\.com/([A-Za-z0-9-]+)", url, re.I)
    if not m:
        return None
    u = m.group(1)
    if u.lower() in {"orgs", "topics", "features", "about", "apps"}:
        return None
    return u


def page_connection(fetch_fn, conn):
    """Collect all nodes of a connection by following pageInfo cursors."""
    nodes = list(conn.get("nodes", []))
    info = conn.get("pageInfo", {})
    while info.get("hasNextPage"):
        conn = fetch_fn(info["endCursor"])
        if not conn:
            break
        nodes.extend(conn.get("nodes", []))
        info = conn.get("pageInfo", {})
    return nodes


def fetch_user(login: str) -> dict | None:
    data = gh_graphql(QUERY, {"login": login})
    if data is None:
        return None
    if data.get("_notfound") or not data.get("data", {}).get("user"):
        return {"_notfound": True}
    u = data["data"]["user"]

    # ---- followers (full) ----
    followers = page_connection(
        lambda cur: _page(login, "followers", "fp", cur),
        u.get("followers", {}),
    )
    following = page_connection(
        lambda cur: _page(login, "following", "gp", cur),
        u.get("following", {}),
    )
    repos_raw = page_connection(
        lambda cur: _page(login, "repositories", "rp", cur),
        u.get("repositories", {}),
    )

    repos = []
    langs = {}
    total_stars = total_forks = 0
    recent = None
    for r in repos_raw:
        lang = (r.get("primaryLanguage") or {}).get("name")
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
        stars = r.get("stargazerCount") or 0
        forks = r.get("forkCount") or 0
        total_stars += stars
        total_forks += forks
        pushed = r.get("pushedAt")
        if pushed and (recent is None or pushed > recent):
            recent = pushed
        db = r.get("defaultBranchRef") or {}
        hist = (((db.get("target") or {}).get("history")) or {}).get("totalCount")
        lic = r.get("licenseInfo") or {}
        repos.append({
            "reponame": r.get("name"),
            "repo_link": r.get("url"),
            "repo_description": r.get("description"),
            "stars": stars,
            "commits": hist,
            "language": lang,
            "forks_count": forks,
            "watchers_count": r.get("stargazerCount"),
            "open_issues_count": (r.get("issues") or {}).get("totalCount"),
            "topics": [t["topic"]["name"] for t in (r.get("repositoryTopics") or {}).get("nodes", [])],
            "license": lic.get("spdxId"),
            "created_at": r.get("createdAt"),
            "updated_at": r.get("updatedAt"),
            "pushed_at": r.get("pushedAt"),
            "default_branch": db.get("name"),
            "is_fork": r.get("isFork"),
            "is_archived": r.get("isArchived"),
            "size": r.get("diskUsage"),
        })

    age = None
    if u.get("createdAt"):
        try:
            c = datetime.strptime(u["createdAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - c).days
        except Exception:
            pass

    return {
        "username": u.get("login", login),
        "name": u.get("name"),
        "about": u.get("bio"),
        "company": u.get("company"),
        "location": u.get("location"),
        "blog": u.get("websiteUrl"),
        "twitter_username": u.get("twitterUsername"),
        "hireable": None,
        "created_at": u.get("createdAt"),
        "updated_at": u.get("updatedAt"),
        "avatar_url": u.get("avatarUrl"),
        "html_url": u.get("url"),
        "followers": [f.get("login") for f in followers],
        "follower_count": (u.get("followers") or {}).get("totalCount", len(followers)),
        "following": [f.get("login") for f in following],
        "following_count": (u.get("following") or {}).get("totalCount", len(following)),
        "public_repos": u.get("repositories", {}).get("totalCount"),
        "repo_count": len(repos),
        "total_stars": total_stars,
        "total_forks": total_forks,
        "languages": langs,
        "most_recent_push": recent,
        "account_age_days": age,
        "repos": repos,
        "_scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def _page(login, field, var, cursor):
    """Fetch one extra page of a connection (followers/following/repositories)."""
    sub = {
        "followers": "followers(first:100, after:$%s){ nodes{login} pageInfo{hasNextPage endCursor} }" % var,
        "following": "following(first:100, after:$%s){ nodes{login} pageInfo{hasNextPage endCursor} }" % var,
        "repositories": ("repositories(first:100, after:$%s, privacy:PUBLIC, ownerAffiliations:OWNER,"
                         " orderBy:{field:PUSHED_AT,direction:DESC}){ nodes{ name description url "
                         "stargazerCount forkCount issues(states:OPEN){totalCount} "
                         "repositoryTopics(first:100){nodes{topic{name}}} licenseInfo{spdxId} "
                         "createdAt updatedAt pushedAt isFork isArchived diskUsage "
                         "primaryLanguage{name} defaultBranchRef{name target{... on Commit{history{totalCount}}}} }"
                         " pageInfo{hasNextPage endCursor} }") % var,
    }[field]
    q = f"query($login:String!, ${var}:String){{ user(login:$login){{ {sub} }} }}"
    data = gh_graphql(q, {"login": login, var: cursor})
    if not data or not data.get("data", {}).get("user"):
        return None
    return data["data"]["user"][field]


# ---------------------------------------------------------------------------
# io
# ---------------------------------------------------------------------------
def load_targets():
    with open(FLAT, "r", encoding="utf-8") as f:
        rows = json.load(f)
    out, seen = [], set()
    for row in rows:
        u = glogin(row.get("github"))
        if not u or u.lower() in seen:
            continue
        seen.add(u.lower())
        out.append({"username": u, "participant_index": row.get("index"),
                    "participant_name": row.get("name")})
    return out


def load_out():
    if not os.path.exists(OUT):
        return {}
    try:
        with open(OUT, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_out(d):
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, OUT)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    targets = load_targets()
    store = load_out()
    done = {k.lower() for k in store if not k.startswith("_")}

    log(f"targets with github: {len(targets)}   already saved: {len(done)}")

    if args.only:
        targets = [t for t in targets if t["username"].lower() == args.only.lower()]
        if not targets:
            log(f"--only {args.only} not found")
            return 1

    pending = targets if args.refresh else [t for t in targets if t["username"].lower() not in done]
    if args.limit is not None:
        pending = pending[:args.limit]

    log(f"to scrape this run: {len(pending)}")

    if args.dry_run:
        for t in pending[:50]:
            log(f"  {t['username']}  <- {t['participant_name']} (row {t['participant_index']})")
        if len(pending) > 50:
            log(f"  ... +{len(pending)-50} more")
        return 0
    if not pending:
        log("nothing to do.")
        return 0

    log("=" * 60)
    ok = fail = 0
    total = len(pending)
    run_t0 = time.time()
    for i, t in enumerate(pending, 1):
        u = t["username"]

        pts = points_remaining()
        if pts is not None and pts <= POINTS_LOW:
            log(f"~ points low ({pts}); pausing {POINTS_PAUSE}s")
            time.sleep(POINTS_PAUSE)

        el = time.time() - run_t0
        avg = el / max(i - 1, 1)
        eta = avg * (total - i)
        log("")
        log(f"+--- [{i}/{total}]  {100*i/total:5.1f}%   "
            f"ok:{ok} fail:{fail}   pts:{pts}   ETA {int(eta)//60}m{int(eta)%60:02d}s")
        log(f"|  user : {u}")
        log(f"+--- participant: {t['participant_name']} (row {t['participant_index']})")

        rec = fetch_user(u)
        if rec is None:
            fail += 1
            store.setdefault("_failed", [])
            if u not in store["_failed"]:
                store["_failed"].append(u)
            log(f"   ERR  FAILED {u}", indent=1)
        elif rec.get("_notfound"):
            fail += 1
            store.setdefault("_missing", [])
            if u not in store["_missing"]:
                store["_missing"].append(u)
            log(f"   ERR  not found on GitHub: {u}", indent=1)
        else:
            rec["participant_index"] = t["participant_index"]
            rec["participant_name"] = t["participant_name"]
            store[u] = rec
            ok += 1
            log(f"   OK   {rec['name']!r}  repos:{rec['repo_count']}  "
                f"stars:{rec['total_stars']}  followers:{rec['follower_count']}  "
                f"following:{rec['following_count']}", indent=1)
            for r in rec["repos"][:5]:
                log(f"      *  {r['reponame'][:38]:<38} *{r['stars']:<4} commits:{r['commits']}", indent=1)
            if len(rec["repos"]) > 5:
                log(f"      ... +{len(rec['repos'])-5} more repos", indent=1)

        save_out(store)
        log(f"   [saved] {os.path.basename(OUT)}", indent=1)

        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    log("=" * 60)
    log(f"DONE. +{ok} saved, {fail} failed.  file: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
