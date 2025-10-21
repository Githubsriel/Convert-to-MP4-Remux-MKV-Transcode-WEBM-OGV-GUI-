import os
import sys
import json
import subprocess
import datetime
import traceback
import threading
import queue
import re
import shutil
import importlib
from shutil import which

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ========= Global Config / Defaults =========
LOG_NAME = "log.txt"
PROGRESS_DB_NAME = "progress.json"
FAILED_LIST_NAME = "failed.txt"

# Supported inputs
INPUT_EXTS = {".mkv", ".webm", ".ogv"}

# MKV policy: remux; audio copy if AAC/MP3 else AAC transcode
AUDIO_OK_FOR_MP4 = {"aac", "mp3"}

# WEBM/OGV defaults (quality-first)
DEFAULT_CRF = "18"         # lower = higher quality (18 ≈ visually lossless)
DEFAULT_PRESET = "slow"    # slower = better compression at same quality
DEFAULT_TUNE = ""          # "film", "animation", "grain" (empty = none)
AUDIO_BITRATE = "192k"     # AAC bitrate
# ===========================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, LOG_NAME)
PROGRESS_DB_FILE = os.path.join(SCRIPT_DIR, PROGRESS_DB_NAME)
FAILED_LIST_FILE = os.path.join(SCRIPT_DIR, FAILED_LIST_NAME)

# ---------- FFmpeg/ffprobe resolution (no system install required) ----------
FFMPEG_BIN = None
FFPROBE_BIN = None

def resolve_media_bins():
    """
    Prefer local ffmpeg/ffprobe beside the script, then imageio-ffmpeg (ffmpeg only),
    then system PATH. Returns (ffmpeg_path, ffprobe_path_or_None).
    """
    script_dir = SCRIPT_DIR
    ffmpeg_candidates = [
        os.path.join(script_dir, "ffmpeg.exe"),
        os.path.join(script_dir, "ffmpeg"),  # non-Windows
    ]
    ffprobe_candidates = [
        os.path.join(script_dir, "ffprobe.exe"),
        os.path.join(script_dir, "ffprobe"),
    ]

    ffmpeg_path = None
    for c in ffmpeg_candidates:
        if os.path.exists(c):
            ffmpeg_path = c
            break
    if not ffmpeg_path:
        # Try imageio-ffmpeg bundled binary
        try:
            iio = importlib.import_module("imageio_ffmpeg")
            ffmpeg_path = iio.get_ffmpeg_exe()
        except Exception:
            ffmpeg_path = None
    if not ffmpeg_path:
        ffmpeg_path = shutil.which("ffmpeg")

    ffprobe_path = None
    for c in ffprobe_candidates:
        if os.path.exists(c):
            ffprobe_path = c
            break
    if not ffprobe_path:
        ffprobe_path = shutil.which("ffprobe")

    return ffmpeg_path, ffprobe_path

FFMPEG_BIN, FFPROBE_BIN = resolve_media_bins()

# ---------- Resource helper (works in PyInstaller one-file) ----------
def resource_path(rel_path: str) -> str:
    """Return absolute path to resource, works for dev and PyInstaller one-file."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)

# ------------- Utilities -------------
def nowstamp():
    return datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def ui_safe_log(ui_queue, msg, also_file=True):
    ui_queue.put(("log", msg))
    if also_file:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{nowstamp()} {msg}\n")

def ui_safe_log_raw(ui_queue, raw):
    # raw already includes newlines; no timestamp here
    ui_queue.put(("lograw", raw))
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(raw)

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read() or "{}")
    except Exception:
        return {}

def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def append_failed(path):
    with open(FAILED_LIST_FILE, "a", encoding="utf-8") as f:
        f.write(path + "\n")

def file_sig(path):
    st = os.stat(path)
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}

def already_done(db, src, dst):
    rec = db.get(src)
    if not rec:
        return False
    if not os.path.exists(dst):
        return False
    try:
        sig = file_sig(src)
    except FileNotFoundError:
        return False
    return rec.get("success") and rec.get("sig") == sig

def mark_progress(db, src, dst, success):
    try:
        sig = file_sig(src) if os.path.exists(src) else None
    except Exception:
        sig = None
    db[src] = {
        "dst": dst,
        "success": bool(success),
        "sig": sig,
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds")
    }

# ---------- Probing (ffprobe preferred, ffmpeg stderr fallback) ----------
AUDIO_CODEC_RE = re.compile(r"Audio:\s*([A-Za-z0-9_]+)", re.IGNORECASE)

def ffprobe(filter_type, path):
    """
    Return stream list filtered by 'audio' or 'video'.
    Prefer ffprobe (JSON). If ffprobe missing, fall back to parsing `ffmpeg -i` stderr.
    """
    # Try ffprobe JSON first
    if FFPROBE_BIN:
        try:
            res = subprocess.run(
                [FFPROBE_BIN, "-v", "error", "-print_format", "json",
                 "-show_streams", "-show_format", path],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=False
            )
            data = json.loads(res.stdout.decode("utf-8", "replace") or "{}")
            streams = data.get("streams", [])
            return [s for s in streams if s.get("codec_type") == filter_type]
        except Exception:
            pass

    # Fallback: use ffmpeg -i (stderr text), parse codec lines
    try:
        # ffmpeg prints stream info to stderr
        res = subprocess.run(
            [FFMPEG_BIN, "-hide_banner", "-v", "error", "-i", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False  # will "fail" because no output option; we only need stderr
        )
        # Build a minimal structure for audio streams
        streams = []
        if filter_type == "audio":
            for line in (res.stderr or "").splitlines():
                m = AUDIO_CODEC_RE.search(line)
                if m:
                    streams.append({"codec_type": "audio", "codec_name": m.group(1).lower()})
        elif filter_type == "video":
            # For our current logic we only need audio probing; provide empty or basic info
            pass
        return streams
    except Exception:
        return []

def run_ffmpeg_with_streaming(cmd, ui_queue):
    """Run ffmpeg and stream stderr into UI/log (avoid deadlocks)."""
    pretty = " ".join(cmd)
    ui_safe_log(ui_queue, f"   ffmpeg: {pretty}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    for line in proc.stderr:
        ui_safe_log_raw(ui_queue, f"      {line}")
    proc.stderr.close()
    return proc.wait()

def dest_path(src):
    return os.path.splitext(src)[0] + ".mp4"

def collect_inputs(paths):
    found = []
    for p in paths:
        if os.path.isfile(p) and os.path.splitext(p)[1].lower() in INPUT_EXTS:
            found.append(p)
        elif os.path.isdir(p):
            for root, _, files in os.walk(p):
                for n in files:
                    if os.path.splitext(n)[1].lower() in INPUT_EXTS:
                        found.append(os.path.join(root, n))
    # de-dupe preserving order
    seen = set(); out = []
    for f in found:
        if f not in seen:
            seen.add(f); out.append(f)
    return out

# ---------- Command builders ----------
def should_transcode_audio_for_mkv(src):
    streams = ffprobe("audio", src)
    if not streams:
        return False
    for s in streams:
        c = (s.get("codec_name") or "").lower()
        if c not in AUDIO_OK_FOR_MP4:
            return True
    return False

def build_ffmpeg_cmd_remux_mkv(src, dst, transcode_audio, keep_text_subs=False):
    cmd = [
        FFMPEG_BIN,
        "-loglevel", "warning",
        "-hide_banner",
        "-nostats",
        "-y",
        "-fflags", "+genpts+discardcorrupt",
        "-err_detect", "ignore_err",
        "-i", src,
        "-map", "0:v?",
        "-map", "0:a?",
        "-c:v", "copy",
    ]
    if transcode_audio:
        cmd += ["-c:a", "aac", "-b:a", AUDIO_BITRATE, "-af", "aresample=async=1:first_pts=0"]
    else:
        cmd += ["-c:a", "copy"]
    if keep_text_subs:
        cmd += ["-map", "0:s?", "-c:s", "mov_text"]
    cmd += ["-avoid_negative_ts", "make_zero", "-movflags", "+faststart", dst]
    return cmd

def build_ffmpeg_cmd_transcode(src, dst, crf, preset, tune, lossless):
    cmd = [
        FFMPEG_BIN,
        "-loglevel", "warning",
        "-hide_banner",
        "-nostats",
        "-y",
        "-fflags", "+genpts+discardcorrupt",
        "-err_detect", "ignore_err",
        "-i", src,
        "-map", "0:v:0?",
        "-map", "0:a:0?",
        "-c:v", "libx264",
    ]
    if lossless:
        cmd += ["-preset", preset or "veryslow", "-crf", "0", "-pix_fmt", "yuv420p"]
    else:
        cmd += ["-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p"]
    if tune:
        cmd += ["-tune", tune]
    cmd += ["-c:a", "aac", "-b:a", AUDIO_BITRATE]
    cmd += ["-avoid_negative_ts", "make_zero", "-movflags", "+faststart", dst]
    return cmd

# ---------- Deletion helpers ----------
def try_send2trash(path):
    try:
        from send2trash import send2trash  # type: ignore
        send2trash(path)
        return True
    except Exception:
        return False

def delete_file(path, permanent=False):
    if not permanent and try_send2trash(path):
        return "trashed"
    os.remove(path)
    return "deleted"

# ---------- Worker logic ----------
class ConverterWorker(threading.Thread):
    def __init__(self, ui_queue, tasks, opts):
        super().__init__(daemon=True)
        self.ui_queue = ui_queue
        self.tasks = tasks  # list of file paths
        self.opts = opts
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        # Start session header
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n=== Session started: {nowstamp()} ===\n")

        if not FFMPEG_BIN:
            ui_safe_log(self.ui_queue, "❌ FFmpeg not available. Put ffmpeg.exe beside the script or install it.")
            self.ui_queue.put(("done", None))
            return

        db = load_json(PROGRESS_DB_FILE)
        total = len(self.tasks)
        success = 0
        skipped = 0
        idx = 0

        for src in self.tasks:
            if self._stop.is_set():
                ui_safe_log(self.ui_queue, "🛑 Stopped by user.")
                break
            idx += 1
            try:
                ext = os.path.splitext(src)[1].lower()
                dst = dest_path(src)

                # Skip if already done & unchanged
                if not self.opts["force"] and already_done(db, src, dst):
                    ui_safe_log(self.ui_queue, f"[{idx}/{total}] ⏭️  Skipping (already converted & unchanged): {src}")
                    skipped += 1
                    self.ui_queue.put(("progress", (idx, total)))
                    continue

                # Process file
                if ext == ".mkv":
                    ok = self.process_mkv(src, idx, total)
                else:
                    ok = self.process_transcode(src, idx, total)

                mark_progress(db, src, dst, ok)
                save_json(PROGRESS_DB_FILE, db)

                if ok:
                    success += 1
                    # Optional delete-after
                    if self.opts["delete_after_policy"]:
                        self.maybe_delete_source(src)
            except Exception:
                ui_safe_log(self.ui_queue, f"❌ Crash while processing: {src}")
                ui_safe_log_raw(self.ui_queue, traceback.format_exc() + "\n")
                append_failed(src)
                dst = dest_path(src)
                mark_progress(db, src, dst, False)
                save_json(PROGRESS_DB_FILE, db)
            finally:
                self.ui_queue.put(("progress", (idx, total)))

        ui_safe_log(self.ui_queue, f"\n✅ Done! Converted {success}/{total} successfully. Skipped {skipped}.")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"=== Session ended: {nowstamp()} ===\n")
        self.ui_queue.put(("done", None))

    def process_mkv(self, src, idx, total):
        ui_safe_log(self.ui_queue, f"[{idx}/{total}] 🔄 Remux (MKV): {src}")
        transcode_audio = self.should_transcode_audio_for_mkv(src)
        cmd = build_ffmpeg_cmd_remux_mkv(src, dest_path(src), transcode_audio, keep_text_subs=False)
        rc = run_ffmpeg_with_streaming(cmd, self.ui_queue)
        if rc == 0 and os.path.exists(dest_path(src)) and os.path.getsize(dest_path(src)) > 0:
            ui_safe_log(self.ui_queue, f"✅ Success: {dest_path(src)}")
            return True
        ui_safe_log(self.ui_queue, "   ⚠️ Primary attempt failed. Trying fallback (force AAC, drop subs).")
        cmd2 = build_ffmpeg_cmd_remux_mkv(src, dest_path(src), True, False)
        rc2 = run_ffmpeg_with_streaming(cmd2, self.ui_queue)
        if rc2 == 0 and os.path.exists(dest_path(src)) and os.path.getsize(dest_path(src)) > 0:
            ui_safe_log(self.ui_queue, f"✅ Success (fallback): {dest_path(src)}")
            return True
        ui_safe_log(self.ui_queue, f"❌ Failed: {src}")
        append_failed(src)
        return False

    def process_transcode(self, src, idx, total):
        ui_safe_log(self.ui_queue, f"[{idx}/{total}] 🔄 Transcode: {src}")
        cmd = build_ffmpeg_cmd_transcode(
            src, dest_path(src),
            self.opts["crf"], self.opts["preset"],
            self.opts["tune"] if self.opts["tune"] else None,
            self.opts["lossless"]
        )
        rc = run_ffmpeg_with_streaming(cmd, self.ui_queue)
        if rc == 0 and os.path.exists(dest_path(src)) and os.path.getsize(dest_path(src)) > 0:
            ui_safe_log(self.ui_queue, f"✅ Success: {dest_path(src)}")
            return True
        ui_safe_log(self.ui_queue, f"❌ Failed: {src}")
        append_failed(src)
        return False

    def should_transcode_audio_for_mkv(self, src):
        return should_transcode_audio_for_mkv(src)

    def maybe_delete_source(self, src):
        ext = os.path.splitext(src)[1].lower()
        policy = self.opts["delete_after_policy"]
        allowed = policy == "all" or (isinstance(policy, set) and ext in policy)
        if not allowed:
            return
        if self.opts["dry_run"]:
            ui_safe_log(self.ui_queue, f"🧪 DRY-RUN: Would remove source: {src}")
            return
        method = delete_file(src, permanent=self.opts["permanent"])
        ui_safe_log(self.ui_queue, f"🧹 Removed source ({method}): {src}")

# ---------- Cleanup (from progress.json) ----------
def cleanup_from_progress(ui_queue, policy, scope_paths, permanent, dry_run):
    db = load_json(PROGRESS_DB_FILE)
    if not db:
        ui_safe_log(ui_queue, "⚠️ No progress.json found or empty; nothing to clean.")
        return

    def is_within(path, roots):
        if not roots:
            return True
        p_norm = os.path.normcase(os.path.abspath(path))
        for r in roots:
            r_norm = os.path.normcase(os.path.abspath(r))
            if p_norm == r_norm:
                return True
            if os.path.isdir(r_norm) and p_norm.startswith(r_norm + os.sep):
                return True
        return False

    total_candidates = removed = mismatched = missing_dst = missing_src = 0
    skipped_scope = skipped_not_success = skipped_ext = 0

    ui_safe_log(ui_queue, f"🧹 Cleanup using policy={policy}, dry_run={dry_run}, permanent={permanent}")
    for src, rec in db.items():
        try:
            ext = os.path.splitext(src)[1].lower()
            if policy != "all" and ext not in policy:
                skipped_ext += 1
                continue
            if scope_paths and not is_within(src, scope_paths):
                skipped_scope += 1
                continue
            total_candidates += 1

            if not rec.get("success"):
                skipped_not_success += 1
                ui_safe_log(ui_queue, f"⏭️  Skipping (not marked success): {src}")
                continue

            dst = rec.get("dst") or dest_path(src)
            if not os.path.exists(dst):
                missing_dst += 1
                ui_safe_log(ui_queue, f"⏭️  Skipping (converted file missing): {src}")
                continue
            if not os.path.exists(src):
                missing_src += 1
                ui_safe_log(ui_queue, f"ℹ️  Already gone: {src}")
                continue

            saved_sig = rec.get("sig")
            try:
                current_sig = file_sig(src)
            except FileNotFoundError:
                missing_src += 1
                ui_safe_log(ui_queue, f"ℹ️  Already gone: {src}")
                continue

            if not saved_sig or saved_sig != current_sig:
                mismatched += 1
                ui_safe_log(ui_queue, f"⏭️  Skipping (file changed since conversion): {src}")
                continue

            # Delete
            if dry_run:
                ui_safe_log(ui_queue, f"🧪 DRY-RUN: Would remove {src}")
            else:
                method = delete_file(src, permanent=permanent)
                removed += 1
                ui_safe_log(ui_queue, f"🧹 Removed ({method}): {src}")
        except Exception:
            ui_safe_log(ui_queue, f"❌ Error while removing: {src}")
            ui_safe_log_raw(ui_queue, traceback.format_exc() + "\n")

    ui_safe_log(ui_queue, "\n—— Cleanup Summary ——")
    ui_safe_log(ui_queue, f"Candidates (scoped): {total_candidates}")
    ui_safe_log(ui_queue, f"Removed:            {removed}")
    ui_safe_log(ui_queue, f"Missing source:     {missing_src}")
    ui_safe_log(ui_queue, f"Missing converted:  {missing_dst}")
    ui_safe_log(ui_queue, f"Changed since conv.:{mismatched}")
    ui_safe_log(ui_queue, f"Skipped by scope:   {skipped_scope}")
    ui_safe_log(ui_queue, f"Skipped not success:{skipped_not_success}")
    ui_safe_log(ui_queue, f"Skipped wrong ext.: {skipped_ext}")

# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Convert to MP4 (MKV remux, WEBM/OGV transcode)")
        self.geometry("980x640")

        # Window icon (works with PyInstaller one-file and normal runs)
        try:
            icon_path = resource_path("app_icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            # Safe to ignore on platforms or cases where icon can't be set
            pass

        # State
        self.ui_queue = queue.Queue()
        self.worker = None

        # Top controls (file list + buttons)
        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=(10,5))
        self.listbox = tk.Listbox(top, selectmode=tk.EXTENDED, height=8)
        self.listbox.pack(side="left", fill="x", expand=True)
        btns = ttk.Frame(top); btns.pack(side="left", padx=(8,0))
        ttk.Button(btns, text="Add Files", command=self.add_files).pack(fill="x", pady=2)
        ttk.Button(btns, text="Add Folder", command=self.add_folder).pack(fill="x", pady=2)
        ttk.Button(btns, text="Remove Selected", command=self.remove_selected).pack(fill="x", pady=2)
        ttk.Button(btns, text="Clear List", command=self.clear_list).pack(fill="x", pady=2)

        # Options
        opts = ttk.LabelFrame(self, text="Options"); opts.pack(fill="x", padx=10, pady=5)
        # WEBM/OGV quality opts
        qo = ttk.Frame(opts); qo.pack(fill="x", pady=2)
        ttk.Label(qo, text="CRF (WEBM/OGV):").pack(side="left")
        self.var_crf = tk.StringVar(value=DEFAULT_CRF)
        ttk.Entry(qo, width=6, textvariable=self.var_crf).pack(side="left", padx=(5,15))
        ttk.Label(qo, text="Preset:").pack(side="left")
        self.var_preset = tk.StringVar(value=DEFAULT_PRESET)
        ttk.Combobox(qo, width=10, textvariable=self.var_preset,
                     values=["ultrafast","superfast","veryfast","faster","fast","medium","slow","slower","veryslow"]).pack(side="left", padx=(5,15))
        ttk.Label(qo, text="Tune:").pack(side="left")
        self.var_tune = tk.StringVar(value=DEFAULT_TUNE)
        ttk.Combobox(qo, width=12, textvariable=self.var_tune,
                     values=["","film","animation","grain"]).pack(side="left", padx=(5,15))
        self.var_lossless = tk.BooleanVar(value=False)
        ttk.Checkbutton(qo, text="Lossless (x264)", variable=self.var_lossless).pack(side="left")

        # Behavior opts
        bo = ttk.Frame(opts); bo.pack(fill="x", pady=2)
        self.var_force = tk.BooleanVar(value=False)
        ttk.Checkbutton(bo, text="Force reprocess (ignore progress.json)", variable=self.var_force).pack(side="left", padx=(0,15))
        self.var_dryrun = tk.BooleanVar(value=False)
        ttk.Checkbutton(bo, text="Dry-run deletions", variable=self.var_dryrun).pack(side="left", padx=(0,15))
        self.var_perm = tk.BooleanVar(value=False)
        ttk.Checkbutton(bo, text="Permanent delete (skip Recycle Bin)", variable=self.var_perm).pack(side="left")

        # Delete-after policy
        delf = ttk.Frame(opts); delf.pack(fill="x", pady=2)
        ttk.Label(delf, text="Delete originals after success:").pack(side="left")
        self.var_del_mkv  = tk.BooleanVar(value=False)
        self.var_del_webm = tk.BooleanVar(value=False)
        self.var_del_ogv  = tk.BooleanVar(value=False)
        ttk.Checkbutton(delf, text="MKV",  variable=self.var_del_mkv).pack(side="left")
        ttk.Checkbutton(delf, text="WEBM", variable=self.var_del_webm).pack(side="left")
        ttk.Checkbutton(delf, text="OGV",  variable=self.var_del_ogv).pack(side="left")

        # Cleanup row
        cl = ttk.Frame(opts); cl.pack(fill="x", pady=2)
        ttk.Button(cl, text="Cleanup from progress.json (delete originals)", command=self.cleanup_from_progress_clicked).pack(side="left")
        ttk.Label(cl, text=" (uses selected delete checkboxes & selected paths as scope)").pack(side="left")

        # Progress
        pr = ttk.Frame(self); pr.pack(fill="x", padx=10, pady=5)
        self.progress = ttk.Progressbar(pr, mode="determinate")
        self.progress.pack(fill="x")
        self.progress_label = ttk.Label(pr, text="Idle")
        self.progress_label.pack(anchor="w")

        # Log
        lf = ttk.LabelFrame(self, text="Log"); lf.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.text = tk.Text(lf, height=16, wrap="none")
        self.text.pack(fill="both", expand=True)
        self.text.configure(state="disabled")
        # Buttons
        bf = ttk.Frame(self); bf.pack(fill="x", padx=10, pady=(0,10))
        self.btn_start = ttk.Button(bf, text="Start", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_stop  = ttk.Button(bf, text="Stop", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(10,0))

        # UI polling
        self.after(100, self.poll_queue)

    # ----- UI helpers -----
    def add_files(self):
        paths = filedialog.askopenfilenames(title="Select videos",
                                            filetypes=[("Video", "*.mkv *.webm *.ogv"),
                                                       ("All", "*.*")])
        for p in paths:
            self.listbox.insert("end", p)

    def add_folder(self):
        d = filedialog.askdirectory(title="Select folder")
        if not d:
            return
        # Just add the folder; actual file discovery happens before processing/cleanup
        self.listbox.insert("end", d)

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        sel.reverse()
        for i in sel:
            self.listbox.delete(i)

    def clear_list(self):
        self.listbox.delete(0, "end")

    # ----- Start/Stop processing -----
    def start(self):
        if not FFMPEG_BIN:
            messagebox.showerror("Error", "FFmpeg not available.\nPut ffmpeg.exe beside this script or install it.")
            return
        items = [self.listbox.get(i) for i in range(self.listbox.size())]
        if not items:
            messagebox.showinfo("Nothing to do", "Add files or folders first.")
            return

        # Build file list
        inputs = collect_inputs(items)
        if not inputs:
            messagebox.showinfo("Nothing to do", "No .mkv/.webm/.ogv files found.")
            return

        # Options
        delete_after_policy = set()
        if self.var_del_mkv.get():  delete_after_policy.add(".mkv")
        if self.var_del_webm.get(): delete_after_policy.add(".webm")
        if self.var_del_ogv.get():  delete_after_policy.add(".ogv")
        if not delete_after_policy:
            delete_after_policy = None

        opts = {
            "crf": self.var_crf.get().strip() or DEFAULT_CRF,
            "preset": self.var_preset.get().strip() or DEFAULT_PRESET,
            "tune": self.var_tune.get().strip(),
            "lossless": self.var_lossless.get(),
            "force": self.var_force.get(),
            "dry_run": self.var_dryrun.get(),
            "permanent": self.var_perm.get(),
            "delete_after_policy": "all" if delete_after_policy == {"all"} else delete_after_policy
        }

        # Reset progress UI
        self.progress["value"] = 0
        self.progress["maximum"] = len(inputs)
        self.progress_label.config(text=f"0 / {len(inputs)}")
        self.text_configure(lambda: self.text.delete("1.0", "end"))

        # Start worker
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.worker = ConverterWorker(self.ui_queue, inputs, opts)
        self.worker.start()

    def stop(self):
        if self.worker and self.worker.is_alive():
            self.worker.stop()
            ui_safe_log(self.ui_queue, "🛑 Stop requested...")

    # ----- Cleanup button -----
    def cleanup_from_progress_clicked(self):
        # Scope = whatever is listed in listbox (files/folders)
        scope = [self.listbox.get(i) for i in range(self.listbox.size())]

        # Policy from checkboxes
        policy = set()
        if self.var_del_mkv.get():  policy.add(".mkv")
        if self.var_del_webm.get(): policy.add(".webm")
        if self.var_del_ogv.get():  policy.add(".ogv")
        if not policy:
            if not messagebox.askyesno("No types selected", "No types checked. Delete ALL original types (.mkv/.webm/.ogv) that were converted?\n\nClick Yes to proceed with ALL; No to cancel."):
                return
            policy = "all"

        dry_run = self.var_dryrun.get()
        permanent = self.var_perm.get()

        # Run cleanup in a short worker to keep UI responsive
        def do_cleanup():
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n=== Cleanup session started: {nowstamp()} ===\n")
            cleanup_from_progress(self.ui_queue, policy, scope, permanent, dry_run)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"=== Cleanup session ended: {nowstamp()} ===\n")

        threading.Thread(target=do_cleanup, daemon=True).start()

    # ----- UI event loop -----
    def poll_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "log":
                    self.text_append(payload + "\n")
                elif kind == "lograw":
                    self.text_append(payload)
                elif kind == "progress":
                    i, total = payload
                    self.progress["value"] = i
                    self.progress_label.config(text=f"{i} / {total}")
                elif kind == "done":
                    self.btn_start.config(state="normal")
                    self.btn_stop.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)

    def text_configure(self, fn):
        self.text.configure(state="normal")
        fn()
        self.text.configure(state="disabled")

    def text_append(self, s):
        self.text.configure(state="normal")
        self.text.insert("end", s)
        self.text.see("end")
        self.text.configure(state="disabled")

if __name__ == "__main__":
    # Create log header once per app run
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n=== App launched: {nowstamp()} ===\n")

    app = App()
    app.mainloop()
