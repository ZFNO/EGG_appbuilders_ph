# Mark Ong - EGG AppBuilders PH 2026 Build Log

A scroll-triggered, JSON-driven build log. Every commit becomes an **episode**:
a timestamp, the commit, the files it touched, and any media captured around it.
Episodes hang off a central trunk, alternating **left / right**.

Frontend: Vite + vanilla JS + brutalist yellow theme.
Backend: `watcher.py` (auto every 10 min) + `gui.py` (PySide6 manual controls).

## The flow

```
             ┌─ new commit on ZFNO/EGG_appbuilders_ph ─┐
 every 10min │  (gh cli, authenticated as ZFNO)        │
 ───────────►┤                                          ├─► public/timeline.json  ──► Vercel
             │  media dump/**  (images -> ImgBB,        │        (episodes[])
             └─ videos -> Google Drive folder) ─────────┘
```

Each cycle:
1. **scan for new commits** on the tracked branch
2. record each new commit as an **episode** (`{timestamp: {hash, message, files}}`)
3. **scan `media dump/`** for files not yet uploaded
4. upload **images -> ImgBB**, **videos -> Google Drive**
5. attach each media link to the episode it was captured in (newest episode older than the file)
6. write `public/timeline.json`

## Run

Requires [Bun](https://bun.sh) for the frontend and Python 3 + the libs in
`requirements.txt` for the watcher/GUI.

```bash
bun install
bun run dev            # http://localhost:5180
bun run build          # static output in dist/
```

### Watcher (the 10-minute auto loop)
```bash
python watcher.py                 # run forever, polls every config.poll_seconds
python watcher.py --once          # single cycle (used by commit.bat)
python watcher.py --media-only    # just scan/upload media
python watcher.py --dry-run       # show what would happen, write nothing
start_watcher.bat                 # run it in a minimised background window
```

### GUI
```bash
python gui.py
```
Manual controls: add a note/entry to the latest episode (or start a new one),
pick media files and upload them through the same pipeline, **Sync Now**, and
**Commit & Push**.

### Commit snapshot
```bat
commit.bat
```
Runs one sync cycle, then `git add -A`, commits and pushes. Use it whenever you
want to snapshot progress; it exits quietly if there is nothing to commit.

## Config (`config.json`)
```jsonc
{
  "github": { "user": "ZFNO", "repo": "EGG_appbuilders_ph", "branch": "main" },
  "poll_seconds": 600,
  "media_dir": "media dump",
  "data_file": "public/timeline.json",
  "state_file": "data/state.json",
  "timezone": "Asia/Manila",
  "drive_folder": "https://drive.google.com/drive/folders/1dI1ixawompk3wwe4S5GY1D_FTMGJQITN",
  "drive_public": true,
  "imgbb_env": "IMGBB_API_KEY"
}
```
- `drive_public: true` makes every uploaded video "anyone with the link = viewer"
  so the public site can play it. Set `false` to keep Drive uploads private
  (links then require sign-in and won't play on the site).
- Secrets stay in env: `IMGBB_API_KEY` (required for images), optional `GITHUB_TOKEN`.

## Media
Drop images/videos anywhere under `media dump/` (subfolders are fine). The
watcher picks them up by creation time and files each one under the right
episode. Raw media is **gitignored** - only the hosted link goes into the JSON.

## Data shape
```jsonc
{
  "author": "Mark Ong",
  "github": { "user": "ZFNO", "repo": "EGG_appbuilders_ph", "branch": "main" },
  "updated_at": "2026-10-09T15:00:00+08:00",
  "episodes": [
    {
      "id": "ep-2026-10-09T09-14-00",
      "timestamp": "2026-10-09T09:14:00+08:00",
      "name": "Oct 09 - 09:14",
      "summary": "chore: init repo",
      "media": [ { "name": "setup.png", "type": "image", "url": "https://i.ibb.co/...", "at": "..." } ],
      "commits": [
        {
          "sha": "a1b2c3d...", "date": "2026-10-09", "time": "09:14",
          "branch": "main", "side": "left",
          "title": "chore: init repo", "body": "notes...",
          "tags": ["setup"],
          "images": ["https://i.ibb.co/..."],
          "media": [ { "name": "setup.png", "type": "image", "url": "https://..." } ],
          "files": [ { "path": "watcher.py", "status": "added", "additions": 260, "deletions": 0 } ],
          "stats": { "additions": 260, "deletions": 0 },
          "link": "https://github.com/ZFNO/EGG_appbuilders_ph/commit/a1b2c3d"
        }
      ]
    }
  ]
}
```

## Views
- **Timeline** - branch tree, alternating left/right, scroll-triggered reveal.
- **Graph** - compact `git log`-style list.

Filter by episode (chips), search, toggle media, click any image for the lightbox.
