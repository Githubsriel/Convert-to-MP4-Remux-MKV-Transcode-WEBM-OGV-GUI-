# Convert to MP4 — Remux MKV, Transcode WEBM/OGV (GUI)

A small Windows-friendly tool to batch convert videos into MP4:

* **MKV → MP4 (remux)**: copies video, copies AAC/MP3 audio, otherwise converts audio to AAC.
* **WEBM / OGV → MP4 (transcode)**: converts video to H.264 (x264) and audio to AAC.
* Designed for **drag-and-drop** usage with a simple **Tkinter GUI**.
* Safe logging, **resume support** via `progress.json`, and optional **original file cleanup**.

---

## Features

* ✅ **Remux** `.mkv` without re-encoding video (fast, lossless video).
* ✅ **Transcode** `.webm` / `.ogv` → H.264 + AAC (quality-focused defaults).
* ✅ **Skips already converted** files across runs (`progress.json` tracks size + mtime).
* ✅ **Live log** view + `log.txt`, `failed.txt`.
* ✅ Optional **delete originals** after success (`.mkv`, `.webm`, `.ogv`, or all).
* ✅ **Cleanup from progress** button to remove previously converted sources.
* ✅ Handles emoji/umlauts in paths; no pipe deadlocks.
* ✅ Works with **portable FFmpeg** in the app folder; no system install required.

---

## What’s included

* `convert_any_to_mp4_gui.py` — the GUI application.
* `build.ps1` — PowerShell build script (PyInstaller).
* Generated at runtime:

  * `progress.json` — conversion status DB (used to skip/cleanup).
  * `log.txt` — session logs and ffmpeg output.
  * `failed.txt` — files that failed or crashed.

---

## Requirements

* **Python 3.9+** (Windows; works on other OSes with a matching FFmpeg binary).
* **FFmpeg** runtime:

  * Easiest: put `ffmpeg.exe` (and optionally `ffprobe.exe`) **next to the script/EXE**.
  * Or install FFmpeg on PATH.
  * If `ffprobe.exe` is missing, the app **falls back** to parsing `ffmpeg -i` output.
* (Optional) `send2trash` for Recycle Bin deletes:

  ```bash
  pip install send2trash
  ```
### Get FFmpeg
Download a portable FFmpeg build from:
➡️ [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/)

Place `ffmpeg.exe` and (optionally) `ffprobe.exe` next to the program executable.

> Tip: The app automatically searches for FFmpeg next to itself first.

---

## Usage

### Run from source (recommended during setup)

1. Ensure Python is installed.
2. Put `ffmpeg.exe` (and optionally `ffprobe.exe`) next to `convert_any_to_mp4_gui.py`.
3. Run:

   ```bash
   python convert_any_to_mp4_gui.py
   ```

### Using the GUI

* **Add Files / Add Folder** to queue videos (supports `.mkv`, `.webm`, `.ogv`).
* For `.webm`/`.ogv`, set **CRF** (default 18), **Preset** (default slow), optional **Tune** (`film`/`animation`/`grain`) or **Lossless** (x264 `-crf 0`, huge files).
* (Optional) Check **Delete originals** for `.mkv` / `.webm` / `.ogv` to remove sources **after successful conversion**.
* **Dry-run deletions** shows what would be removed without touching files.
* **Permanent delete** skips Recycle Bin (be careful).
* Click **Start**. Progress and logs stream into the window and `log.txt`.
* **Cleanup from progress.json** removes previously converted originals recorded in `progress.json` (respects delete checkboxes and dry-run/permanent flags).

### What happens under the hood

* For **MKV**:

  * Video: `copy`
  * Audio: `copy` if AAC/MP3, else `aac -b:a 192k` (fixes Opus-in-MP4 playback issues)
  * Subtitles: not preserved by default (MKV text subs can be mapped to `mov_text` if needed)
* For **WEBM/OGV**:

  * Video: `libx264 -crf <CRF> -preset <Preset> -pix_fmt yuv420p`
  * Audio: `aac -b:a 192k`
* Common flags: `-fflags +genpts+discardcorrupt -err_detect ignore_err -movflags +faststart -avoid_negative_ts make_zero`
* All ffmpeg output is streamed to `log.txt` to avoid deadlocks.

---

## Building a single EXE (Windows)

We provide a **PowerShell** build script using **PyInstaller**.

### 1) Install dependencies

```powershell
python -m pip install pyinstaller send2trash
```

### 2) (Optional) Place portable FFmpeg next to the project

* Download a portable build of `ffmpeg.exe` (and optionally `ffprobe.exe`) and place them beside the script.
* The app will bundle them and also copy them next to the final EXE for reliable discovery.

### 3) Build

```powershell
# Default (windowed, onefile), outputs dist\ConvertToMP4.exe
.\build.ps1
```

**Options:**

```powershell
.\build.ps1 -Clean                  # clean build/, dist/, *.spec
.\build.ps1 -ExeName "Converter" -IconFile "app_icon.ico"
.\build.ps1 -Console                # console app (for debugging)
.\build.ps1 -NoEmbedFFmpeg         # don't embed ffmpeg/ffprobe in the EXE
.\build.ps1 -NoCopyFFmpeg          # don't copy ffmpeg/ffprobe next to the EXE
```

The script will:

* Build with `--onefile` and `--windowed` (unless `-Console`).
* Use your `icon` and `version.txt` (if present).
* **Embed** `ffmpeg.exe`/`ffprobe.exe` into the EXE (unless `-NoEmbedFFmpeg`).
* **Copy** them next to the EXE in `dist\` (unless `-NoCopyFFmpeg`).

> **License note:** Many FFmpeg builds (with x264) are **GPL**. If you redistribute the EXE with FFmpeg inside, make sure you comply with the license terms (include license text, provide source offer, etc.).

---

## Repo layout (suggested)

```
/
├─ convert_any_to_mp4_gui.py
├─ build.ps1
├─ app_icon.ico                (optional)
├─ version.txt                 (optional)
├─ ffmpeg.exe                  (optional portable)
├─ ffprobe.exe                 (optional portable)
└─ (generated at runtime)
   ├─ progress.json
   ├─ log.txt
   └─ failed.txt
```

---

## Troubleshooting

* **“FFmpeg not available”**
  Put a portable `ffmpeg.exe` next to the script or the final EXE. The app checks that location first.
  You can also install FFmpeg on PATH.

* **No `ffprobe.exe`**
  That’s OK. The app falls back to parsing `ffmpeg -i` output for audio codec detection (used for MKV remux decisions).

* **Opus/WEBM audio plays silent in MP4**
  Use this tool — it automatically converts non-AAC/MP3 audio to **AAC** when creating MP4s.

* **Re-running converts the same files**
  The app **skips** files already converted with the same size/mtime (tracked in `progress.json`).
  If needed, check **Force reprocess**.

* **Deleting originals**
  Use **Dry-run deletions** first to see what would be removed. If `send2trash` is installed, deletes go to the **Recycle Bin** (unless **Permanent delete** is checked).

---

## Development notes

* GUI built with **Tkinter** (standard library).
* Designed for Windows; should run on macOS/Linux if you provide appropriate FFmpeg binaries and have Tkinter working.
* If you need a pure CLI version, you can strip the GUI layer and wire the same functions behind an argparse interface.

---

## License




---

## Credits

* FFmpeg (the real MVP)
* x264 project
* Tkinter & Python standard library

---

If you want a **drag-and-drop** target on Windows (shell integration) or **GPU-accelerated** transcoding (NVENC/AMF/QuickSync) presets, open an issue — happy to help!
