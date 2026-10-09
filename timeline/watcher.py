"""
watcher.py - Hackathon build-log sync engine for Mark Ong (ZFNO).

Every cycle:
  1. ask GitHub for new commits on the tracked branch (via the authenticated `gh` CLI)
  2. record each new commit as an "episode" (timestamp + hash + message + files)
  3. scan the media dump folder, upload anything new
        - images -> ImgBB
        - videos -> Google Drive (module.apis.google.drive)
  4. attach each media link to the episode it belongs to (newest episode older than the file)
  5. write public/timeline.json (the live JSON the site reads)

Usage:
    python watcher.py                 # run forever, poll every config.poll_seconds
    python watcher.py --once          # one cycle, then exit
    python watcher.py --media-only    # skip GitHub, just scan/upload media
    python watcher.py --dry-run       # show what would happen, change nothing
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
CFG_PATH = PROJECT / "config.json"

IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "avif", "tiff"}
VIDEO_EXT = {"mp4", "mov", "webm", "mkv", "avi", "m4v", "mpg", "mpeg", "wmv"}


# --------------------------------------------------------------------------- utils
def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_cfg() -> dict:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    cfg.setdefault("poll_seconds", 600)
    cfg.setdefault("media_dir", "media dump")
    cfg.setdefault("data_file", "public/timeline.json")
    cfg.setdefault("state_file", "data/state.json")
    cfg.setdefault("timezone", "Asia/Manila")
    cfg.setdefault("drive_public", True)
    cfg.setdefault("imgbb_env", "IMGBB_API_KEY")
    return cfg


def tz_offset(cfg: dict) -> timezone:
    """Fixed-offset tz for the configured zone (PH = +08:00)."""
    name = (cfg.get("timezone") or "Asia/Manila").lower()
    if "manila" in name or "ph" == name or "singapore" in name:
        return timezone(timedelta(hours=8))
    return timezone(timedelta(hours=8))


def load_state(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"last_poll": None, "seen_commits": [], "media": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def add_src_to_path() -> None:
    """Make `module.apis.google.drive` importable by walking up to the src root."""
    here = PROJECT
    for parent in [here, *here.parents]:
        if (parent / "module" / "apis" / "google" / "drive.py").is_file():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return


# --------------------------------------------------------------------------- github
def gh_api(endpoint: str) -> object:
    """Call `gh api <endpoint>` and return parsed JSON (or None on empty repo)."""
    proc = subprocess.run(
        ["gh", "api", endpoint, "-H", "Accept: application/vnd.github+json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        if "empty" in err.lower() or "409" in err or "422" in err:
            return None
        raise RuntimeError(f"gh api {endpoint} failed: {err}")
    out = (proc.stdout or "").strip()
    return json.loads(out) if out else None


def list_commits(cfg: dict) -> list[dict]:
    g = cfg["github"]
    ep = f"repos/{g['user']}/{g['repo']}/commits?sha={g.get('branch','main')}&per_page=100"
    data = gh_api(ep)
    return data if isinstance(data, list) else []


def commit_detail(cfg: dict, sha: str) -> dict:
    g = cfg["github"]
    data = gh_api(f"repos/{g['user']}/{g['repo']}/commits/{sha}")
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------- uploads
def upload_imgbb(cfg: dict, path: Path) -> str:
    import requests  # local import so --dry-run works without deps
    key = None
    for name in (cfg.get("imgbb_env") or "IMGBB_API_KEY", "IMGBB_API_KEY", "IMGBB_API_KEY_old"):
        import os
        key = os.environ.get(name)
        if key:
            break
    if not key:
        raise RuntimeError("no ImgBB key in env (IMGBB_API_KEY)")
    b64 = base64.b64encode(path.read_bytes()).decode()
    r = requests.post(
        f"https://api.imgbb.com/1/upload?key={key}",
        data={"image": b64, "name": path.stem},
        timeout=120,
    )
    j = r.json()
    if not j.get("success"):
        raise RuntimeError(f"imgbb failed: {j}")
    return j["data"].get("display_url") or j["data"]["url"]


def drive_service(cfg: dict):
    add_src_to_path()
    from module.apis.google.drive import get_service
    return get_service()


def upload_drive(cfg: dict, path: Path, service=None) -> str:
    add_src_to_path()
    from module.apis.google.drive import upload_file, extract_folder_id
    service = service or drive_service(cfg)
    info = upload_file(path, folder_id=cfg["drive_folder"], service=service)
    if cfg.get("drive_public", True):
        try:
            service.permissions().create(
                fileId=info["id"],
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True,
            ).execute()
        except Exception as e:  # non-fatal
            log(f"  ! could not set public permission: {e}")
    return info.get("webViewLink") or f"https://drive.google.com/file/d/{info['id']}/view"


def classify(path: Path) -> str | None:
    ext = path.suffix.lower().lstrip(".")
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    return None


def upload_media(cfg: dict, path: Path, service=None) -> tuple[str, str]:
    kind = classify(path)
    if kind == "image":
        return kind, upload_imgbb(cfg, path)
    if kind == "video":
        return kind, upload_drive(cfg, path, service=service)
    raise ValueError(f"unsupported media type: {path.name}")


# --------------------------------------------------------------------------- episodes
def slug(ts: datetime) -> str:
    return "ep-" + ts.strftime("%Y-%m-%dT%H-%M-%S")


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def episode_for(data: dict, when: datetime) -> dict | None:
    """Newest episode whose timestamp is <= `when`."""
    best = None
    for ep in data.get("episodes", []):
        try:
            t = parse_ts(ep["timestamp"])
        except Exception:
            continue
        if t <= when and (best is None or t > parse_ts(best["timestamp"])):
            best = ep
    return best


def new_episode(cfg: dict, commit: dict, detail: dict, tz: timezone, side: str) -> dict:
    raw = commit.get("commit", {})
    iso = raw.get("author", {}).get("date") or raw.get("committer", {}).get("date")
    ts = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(tz)
    msg = raw.get("message", "")
    lines = msg.splitlines()
    title = lines[0] if lines else "(no message)"
    body = "\n".join(lines[1:]).strip()
    files = [
        {
            "path": f.get("filename"),
            "status": f.get("status"),
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
        }
        for f in (detail.get("files") or [])
    ]
    stats = detail.get("stats") or {}
    eid = slug(ts)
    return {
        "id": eid,
        "timestamp": ts.isoformat(),
        "name": ts.strftime("%b %d - %H:%M"),
        "summary": title,
        "media": [],
        "commits": [{
            "sha": commit.get("sha"),
            "date": ts.strftime("%Y-%m-%d"),
            "time": ts.strftime("%H:%M"),
            "branch": cfg["github"].get("branch", "main"),
            "side": side,
            "title": title,
            "body": body,
            "tags": [],
            "images": [],
            "media": [],
            "files": files,
            "stats": {
                "additions": stats.get("additions", sum(f["additions"] for f in files)),
                "deletions": stats.get("deletions", sum(f["deletions"] for f in files)),
            },
            "link": commit.get("html_url", ""),
        }],
    }


def blank_data(cfg: dict) -> dict:
    return {
        "author": cfg.get("author", "Mark Ong"),
        "event": cfg.get("event", "Hackathon 2026"),
        "github": dict(cfg["github"]),
        "episodes": [],
    }


def load_data(cfg: dict) -> dict:
    p = PROJECT / cfg["data_file"]
    if p.is_file():
        d = json.loads(p.read_text(encoding="utf-8"))
        d.setdefault("episodes", [])
        d["author"] = cfg.get("author", d.get("author", "Mark Ong"))
        d["event"] = cfg.get("event", d.get("event", "Hackathon 2026"))
        d["github"] = dict(cfg["github"])
        return d
    return blank_data(cfg)


def write_data(cfg: dict, data: dict, tz: timezone) -> None:
    data["episodes"] = sorted(data.get("episodes", []), key=lambda e: e.get("timestamp", ""))
    data["updated_at"] = datetime.now(tz).isoformat()
    p = PROJECT / cfg["data_file"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- cycle
def scan_media(cfg: dict, state: dict) -> list[Path]:
    root = PROJECT / cfg["media_dir"]
    if not root.is_dir():
        return []
    seen = set(state.get("media", {}).keys())
    out = []
    for p in root.rglob("*"):
        if p.is_file() and classify(p) and p.relative_to(PROJECT).as_posix() not in seen:
            out.append(p)
    return sorted(out, key=lambda p: p.stat().st_mtime)


def ingest_commits(cfg: dict, state: dict, data: dict, tz: timezone, dry: bool) -> int:
    commits = list_commits(cfg)
    if not commits:
        log("github: no commits yet (empty repo?)")
        return 0
    seen = set(state.get("seen_commits", []))
    fresh = [c for c in reversed(commits) if c["sha"] not in seen]  # oldest -> newest
    if not fresh:
        return 0
    n = len(data.get("episodes", []))
    for c in fresh:
        detail = commit_detail(cfg, c["sha"])
        side = "left" if n % 2 == 0 else "right"
        ep = new_episode(cfg, c, detail, tz, side)
        if dry:
            log(f"  + episode {ep['id']}  {c['sha'][:7]}  {ep['summary']}")
        else:
            data["episodes"].append(ep)
            state.setdefault("seen_commits", []).append(c["sha"])
        n += 1
    return len(fresh)


def ingest_media(cfg: dict, state: dict, data: dict, tz: timezone, dry: bool) -> int:
    files = scan_media(cfg, state)
    if not files:
        return 0
    service = None
    if any(classify(f) == "video" for f in files) and not dry:
        try:
            service = drive_service(cfg)
        except Exception as e:
            log(f"  ! drive unavailable, videos skipped: {e}")
    done = 0
    for f in files:
        kind = classify(f)
        rel = f.relative_to(PROJECT).as_posix()
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz)
        try:
            if dry:
                ep_hit = episode_for(data, mtime)
                log(f"  ~ media {rel} ({kind}) -> episode {ep_hit['id'] if ep_hit else 'NONE'}")
                continue
            if kind == "video" and service is None:
                continue
            _, link = upload_media(cfg, f, service=service)
        except Exception as e:
            log(f"  ! upload failed for {rel}: {e}")
            continue

        ep = episode_for(data, mtime)
        entry = {"name": f.name, "type": kind, "url": link, "at": mtime.isoformat()}
        if ep is not None:
            ep.setdefault("media", []).append(entry)
            if ep.get("commits"):
                ep["commits"][0].setdefault("media", []).append(entry)
                if kind == "image":
                    ep["commits"][0].setdefault("images", []).append(link)
        else:
            log(f"  ! {rel} created before any episode - stored in state only")
        state.setdefault("media", {})[rel] = {"link": link, "type": kind, "at": mtime.isoformat()}
        log(f"  + {kind} {rel} -> {link}")
        done += 1
    return done


def sync_once(cfg: dict, dry: bool = False, media_only: bool = False) -> dict:
    tz = tz_offset(cfg)
    sp = PROJECT / cfg["state_file"]
    state = load_state(sp)
    data = load_data(cfg)
    stats = {"commits": 0, "media": 0}
    if not media_only:
        try:
            stats["commits"] = ingest_commits(cfg, state, data, tz, dry)
        except Exception as e:
            log(f"! github step failed: {e}")
    try:
        stats["media"] = ingest_media(cfg, state, data, tz, dry)
    except Exception as e:
        log(f"! media step failed: {e}")
    state["last_poll"] = datetime.now(tz).isoformat()
    if not dry:
        write_data(cfg, data, tz)
        save_state(sp, state)
    log(f"cycle done - {stats['commits']} new commit(s), {stats['media']} new media file(s)")
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build-log sync")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    ap.add_argument("--media-only", action="store_true", help="skip GitHub, scan media only")
    ap.add_argument("--dry-run", action="store_true", help="show, do not write")
    args = ap.parse_args(argv)

    cfg = load_cfg()
    if args.once or args.media_only or args.dry_run:
        sync_once(cfg, dry=args.dry_run, media_only=args.media_only)
        return 0

    log(f"watching {cfg['github']['user']}/{cfg['github']['repo']} every {cfg['poll_seconds']}s")
    while True:
        try:
            sync_once(cfg)
            subprocess.run(["vercel", "deploy", "--prod", "--yes"], cwd=PROJECT)
        except KeyboardInterrupt:
            log("stopped")
            return 0
        except Exception:
            traceback.print_exc()
        time.sleep(int(cfg["poll_seconds"]))


if __name__ == "__main__":
    raise SystemExit(main())
