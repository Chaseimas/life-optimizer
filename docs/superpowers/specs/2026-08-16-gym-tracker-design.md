# Gym Tracker — Design

Date: 2026-08-16
Status: built autonomously; Kase reviews the running app rather than pre-approving this doc (session was unattended — assumptions listed at the bottom)

## Purpose

Phone app for Kase to track gym progress: weekly/monthly progress pictures, body-comp ("BMI") scans, and a compare view organized by months — pick August and December, see the picture from both side by side.

## Approaches considered

1. **Static offline-first PWA in `gym-tracker/`, all data on-device in IndexedDB** ← chosen.
   Matches the existing pattern exactly (LifeOpt at repo root, BuildBudget at `build-budget/`), deploys to the phone via GitHub Pages (`https://chaseimas.github.io/life-optimizer/gym-tracker/` → Add to Home Screen). Photos never leave the phone — important because the repo is public. Works offline at the gym.
2. **Server-backed app on the PC (supra-tracker pattern).** Rejected: phone would need the PC on and the same Wi-Fi; useless at the gym; body photos stored on the PC instead of where they're taken.
3. **Cloud-deployed app with hosted storage (polysignal/Vercel pattern + backend).** Rejected: shipping body photos to cloud storage needs auth and a backend; overkill and worse privacy.

Trade-off accepted with (1): data lives only on the phone. Mitigated by one-tap **Export backup** (single JSON file with images embedded) + **Import**, and `navigator.storage.persist()` to stop the browser evicting the data.

## App structure

Single self-contained `gym-tracker/index.html` (no external libraries, works offline), plus `manifest.json`, `sw.js` (cache-first shell), `icon-192.png` / `icon-512.png`.

Bottom tab bar (thumb reach): **PHOTOS · SCANS · COMPARE · TRENDS**, settings gear in the header.

### Photos
- FAB → camera or gallery (multi-select), photos downscaled client-side (≤1600px JPEG) with a ~360px thumbnail, both stored as Blobs.
- Each photo: date (defaults to today, editable), pose tag (Front / Side / Back / Flex / Other), optional note.
- Feed grouped by month, newest first; 3-column thumb grid; tap → fullscreen viewer (swipe within month, edit date/pose, delete).

### Scans
- Entry form: date, weight, body fat %, muscle mass, visceral fat, water %, optional note, optional photo of the scan printout. BMI auto-computed from height (settings) + weight.
- List of scan cards, newest first, each showing deltas vs the previous scan.

### Compare (the headline feature)
- Two month pickers (A / B) listing only months that have data.
- **Side-by-side** photo panes; each pane pages through that month's photos; when both months have the same pose, changing one side snaps the other to the matching pose.
- **Slider** mode: both photos overlaid with a draggable divider.
- Below the photos: stat deltas between the months' latest scans (weight, body fat, muscle, BMI) — neutral coloring, since "weight down" isn't universally good.

### Trends
- Stat tiles: current weight, body fat %, BMI, photo count.
- Three single-series SVG line charts (weight, body fat %, muscle) — separate charts, never a dual axis. Touch crosshair tooltip; range chips 3M / 6M / 1Y / ALL.

### Settings
- Height (ft/in), lb↔kg unit toggle, storage usage readout, Export backup / Import backup, wipe-all (double confirm).

## Data model (IndexedDB `gymtrack` v1)

- `photos`: `{id, ts, month "YYYY-MM", pose, note, img: Blob, thumb: Blob}` — indexes on `month`, `ts`.
- `scans`: `{id, ts, month, weightLb, bodyFat, muscleLb, bmi, visceral, waterPct, note, img?, thumb?}` — index on `ts`.
- Canonical units: lb / inches; display converts.
- Settings in `localStorage` (`gymtrack-settings`).
- Backup: `{app:"gymtrack", version:1, exported, settings, photos:[…img as dataURL…], scans:[…]}`; import merges, deduping on `(ts, pose)` for photos and `ts` for scans.

## Aesthetic

Industrial gym-plate: near-black iron surfaces, gunmetal cards, safety-amber accent, chalk text; condensed DIN-style type (Bahnschrift on Windows, Roboto Condensed on Android). Chart colors validated with the dataviz palette validator against the dark surface.

## Error handling

- Image decode/resize failures: skip file, toast the filename.
- IndexedDB quota errors: toast + point at settings storage readout.
- Import: validates `app`/`version` before touching the DB; malformed file → error toast, DB untouched.
- SW cache name versioned (`gymtrack-vN`) so deploys refresh cleanly.

## Testing

- Browser-pane verification on the mobile preset with JS-seeded photos (generated canvas images) across multiple months + scans; exercise every flow; console must be clean.
- Ultracode adversarial review workflow over the finished file (data integrity, mobile UX, compare correctness, PWA/offline, backup) with verification votes before fixes.

## Deploy

`git switch master` → commit `gym-tracker/` + this doc → push → GitHub Pages serves it → open URL on phone → Add to Home Screen. **Not done without Kase's go-ahead** (publishing).

## v2 additions (same day, on Kase's "add all")

- **Backup nag**: banner when data exists and no export in 30+ days; export stamps `settings.lastExport`.
- **Goal lines**: `goalWeightLb`/`goalBf` in settings, dashed reference lines on the weight/body-fat charts.
- **FFMI tile**: lean mass (from latest scan with body fat) ÷ height²; tiles grid is now 3×2 with Muscle added.
- **Lifts tab** (5th tab): `lifts` store, exercise picker (big 4 + row + custom), Epley e1RM, PR badges/toast, best-e1RM tiles, per-exercise e1RM trend chart.
- **Tape measurements**: `measures` store, Scans tab gains a SCANS|TAPE toggle; neck/chest/arms/waist/thighs with per-entry deltas; Compare stats table gains tape rows; Trends gains a waist chart (validated rose `#d4688a`).
- **Timelapse**: canvas + `captureStream(0)`/MediaRecorder webm of any pose's photos oldest→newest, ~0.7s/frame, month captions; downloads + inline preview.
- **Cycle marks**: `settings.marks` (label/date/start|stop) managed in settings; dashed vertical lines on weight/body-fat charts.
- IndexedDB bumped to v2 (new stores); backup format v2 (adds `lifts`/`measures`; v1 backups still import).

## Assumptions to confirm with Kase

- GitHub Pages (same as LifeOpt/BuildBudget) is the desired way to get it on the phone.
- US units default (lb, ft/in).
- "BMI scans" = body-comp scanner readouts (InBody-style), so the scan form carries body fat / muscle / visceral / water, not just BMI.
- No lift/PR logging in v1 (easy to add later if "all my gym related stuff" meant that too).
