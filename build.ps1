# build.ps1 – Build Convert-to-MP4 GUI as a single EXE with optional local ffmpeg/ffprobe
# Requires: Python + PyInstaller installed in PATH (or your venv is activated)

param(
  [string]$ScriptName          = "convert_any_to_mp4_gui.py",
  [string]$ExeName             = "ConvertToMP4",
  [string]$IconFile            = "app_icon.ico",
  [string]$VersionFile         = "version.txt",
  [string]$FfmpegBinary        = "ffmpeg.exe",
  [string]$FfprobeBinary       = "ffprobe.exe",

  [switch]$Console,              # build console app (omit --windowed)
  [switch]$Clean,                # remove build/, dist/, *.spec before build
  [switch]$NoEmbedFFmpeg,        # don't embed ffmpeg/ffprobe into the package
  [switch]$NoCopyFFmpeg          # don't copy ffmpeg/ffprobe next to the final EXE
)

function Info($msg){ Write-Host "[*] $msg" -ForegroundColor Cyan }
function Warn($msg){ Write-Warning $msg }
function Die($msg){ Write-Host "[x] $msg" -ForegroundColor Red; exit 1 }

# 0) Basic checks
if (-not (Test-Path $ScriptName)) { Die "Script '$ScriptName' not found." }
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
  Die "PyInstaller not found in PATH. Activate your venv or 'pip install pyinstaller'."
}

# 1) Optional clean
if ($Clean) {
  Info "Cleaning build/, dist/, *.spec..."
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
  Get-ChildItem -Filter "*.spec" | Remove-Item -Force -ErrorAction SilentlyContinue
}

# 2) Optional assets
$haveIcon = $false
if (Test-Path $IconFile) { $haveIcon = $true } else { Warn "Icon '$IconFile' not found; building without custom icon." }

$haveVersion = $false
if (Test-Path $VersionFile) { $haveVersion = $true } else { Warn "Version file '$VersionFile' not found; building without version metadata." }

$haveFFmpeg   = Test-Path $FfmpegBinary
$haveFFprobe  = Test-Path $FfprobeBinary

if (-not $haveFFmpeg)  { Warn "FFmpeg binary '$FfmpegBinary' not found. App can still run if ffmpeg is on PATH or bundled via imageio-ffmpeg." }
if (-not $haveFFprobe) { Warn "ffprobe binary '$FfprobeBinary' not found. App will fall back to parsing 'ffmpeg -i' output." }

# 3) Build command
$buildCmd = "pyinstaller --noconfirm --onefile"
if (-not $Console) { $buildCmd += " --windowed" }

$buildCmd += " --name `"$ExeName`""

if ($haveIcon)    { $buildCmd += " --icon=`"$IconFile`"" }
if ($haveVersion) { $buildCmd += " --version-file=`"$VersionFile`"" }

# Embed ffmpeg/ffprobe inside the package (they will extract to a temp dir at runtime).
# NOTE: Your app also looks for ffmpeg/ffprobe NEXT TO THE EXE. We'll optionally copy them there after build.
if (-not $NoEmbedFFmpeg) {
  if ($haveFFmpeg)  { $buildCmd += " --add-binary `"$FfmpegBinary;.`"" }
  if ($haveFFprobe) { $buildCmd += " --add-binary `"$FfprobeBinary;.`"" }
}

# Always include the icon file as data so it's accessible at runtime if you need it
if ($haveIcon) { $buildCmd += " --add-data `"$IconFile;.`"" }

# Entry script
$buildCmd += " `"$ScriptName`""

Write-Host "Running build command:"
Write-Host $buildCmd -ForegroundColor Yellow
Invoke-Expression $buildCmd

# 4) Post-build: copy ffmpeg/ffprobe NEXT TO the final EXE (so your runtime lookup finds them)
#    Only for --onefile builds, dist\ExeName.exe is the output.
$exePath = Join-Path "dist" ($ExeName + ".exe")
if (-not (Test-Path $exePath)) {
  Die "Build finished but '$exePath' not found. Check PyInstaller output above."
}

if (-not $NoCopyFFmpeg) {
  if ($haveFFmpeg) {
    Info "Copying $FfmpegBinary -> dist\"
    Copy-Item -Force $FfmpegBinary -Destination (Join-Path "dist" (Split-Path $FfmpegBinary -Leaf))
  }
  if ($haveFFprobe) {
    Info "Copying $FfprobeBinary -> dist\"
    Copy-Item -Force $FfprobeBinary -Destination (Join-Path "dist" (Split-Path $FfprobeBinary -Leaf))
  }
}

# 5) Final info
Info "Done. Output:"
Write-Host (" - " + (Resolve-Path $exePath))
if ($haveFFmpeg -and -not $NoCopyFFmpeg)  { Write-Host (" - " + (Resolve-Path (Join-Path "dist" (Split-Path $FfmpegBinary -Leaf)))) }
if ($haveFFprobe -and -not $NoCopyFFmpeg) { Write-Host (" - " + (Resolve-Path (Join-Path "dist" (Split-Path $FfprobeBinary -Leaf)))) }

Write-Host ""
Write-Host "Tip:"
Write-Host " - If you plan to redistribute, remember FFmpeg's license obligations (GPL/LGPL depending on your build)." -ForegroundColor DarkYellow
Write-Host " - To verify runtime: run the EXE from 'dist\' directly; the app will detect ffmpeg/ffprobe next to it." -ForegroundColor DarkYellow
