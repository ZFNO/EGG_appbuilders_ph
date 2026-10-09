# EGG_appbuildersph

Monorepo for the EGG AppBuilders PH hackathon build.

| Folder | What |
|---|---|
| `apk/` | Android app (Kotlin + Gradle) that hosts the web build in a WebView |
| `webcode/` | Vite frontends  -  `web/` (desktop) and `mobile/` (the bundle shipped in the APK) |
| `supabase/` | DB schema, migrations, edge functions |
| `cloudflare/` | Worker / Pages config |
| `py/` | Python tooling (build-log watcher, uploaders) |

## APK <-> web flow
`webcode/mobile/copy_to_apk.bat` builds the mobile bundle and copies `dist/`
into `apk/app/src/main/assets/`, which the WebView loads from
`file:///android_asset/index.html`.

## Quick start
```bat
REM mobile web -> apk assets
webcode\mobile\copy_to_apk.bat

REM desktop web
cd webcode\web && bun install && bun run dev

REM android
cd apk && gradlew.bat assembleDebug
```
