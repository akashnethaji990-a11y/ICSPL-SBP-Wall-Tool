# ============================================================
#  ICSPL SBP Wall Tool - One-click Installer
#  ------------------------------------------------------------
#  What this does:
#    1. Checks if pyRevit is installed - installs it if missing
#    2. Downloads the latest SBP Wall Tool from GitHub
#    3. Puts it in pyRevit's extensions folder (no Settings needed)
#    4. Tells the drafter to reload pyRevit
#
#  Drafter runs this by pasting ONE line into PowerShell:
#    irm https://raw.githubusercontent.com/akashnethaji990-a11y/ICSPL-SBP-Wall-Tool/main/install.ps1 | iex
#
#  Owner: IC Singapore  |  Tool: SBP Wall pyRevit extension
# ============================================================

# --- settings you can change ---
$RepoOwner = "akashnethaji990-a11y"
$RepoName  = "ICSPL-SBP-Wall-Tool"
$Branch    = "main"
$ExtName   = "SBP.extension"
# -------------------------------

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Say($msg, $color = "White") { Write-Host $msg -ForegroundColor $color }

Say "`n========================================" "Cyan"
Say "  ICSPL SBP Wall Tool - Installer" "Cyan"
Say "========================================`n" "Cyan"

# ---------- STEP 1: make sure pyRevit is installed ----------
$pyrevitData = Join-Path $env:APPDATA "pyRevit"
$hasCli      = [bool](Get-Command pyrevit -ErrorAction SilentlyContinue)
$hasAddin    = [bool](Get-ChildItem "$env:APPDATA\Autodesk\Revit\Addins" -Recurse -Filter "pyRevit.addin" -ErrorAction SilentlyContinue)
$pyrevitFound = (Test-Path $pyrevitData) -or $hasCli -or $hasAddin

if ($pyrevitFound) {
    Say "[1/3] pyRevit is already installed. Good." "Green"
}
else {
    Say "[1/3] pyRevit not found - installing it now..." "Yellow"
    Say "      Please CLOSE Revit if it is open, then wait." "Yellow"

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            winget install --id pyRevit.pyRevit --exact --silent `
                --accept-source-agreements --accept-package-agreements
            Say "      pyRevit installed." "Green"
        }
        catch {
            Say "      Automatic pyRevit install failed." "Red"
            Say "      Please install pyRevit manually from:" "Yellow"
            Say "      https://github.com/pyrevitlabs/pyRevit/releases" "Yellow"
            Say "      Then run this installer again." "Yellow"
            return
        }
    }
    else {
        Say "      'winget' is not available on this PC." "Red"
        Say "      Please install pyRevit manually from:" "Yellow"
        Say "      https://github.com/pyrevitlabs/pyRevit/releases" "Yellow"
        Say "      Then run this installer again." "Yellow"
        return
    }
}

# ---------- STEP 2: download the tool from GitHub ----------
Say "`n[2/3] Downloading the SBP Wall Tool..." "Cyan"

$zipUrl  = "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$Branch.zip"
$tmpZip  = Join-Path $env:TEMP "sbp_tool.zip"
$tmpDir  = Join-Path $env:TEMP "sbp_tool_extract"

if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
Invoke-WebRequest -Uri $zipUrl -OutFile $tmpZip
Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force

# find the SBP.extension folder inside the download
$srcExt = Get-ChildItem $tmpDir -Recurse -Directory -Filter $ExtName |
          Select-Object -First 1
if (-not $srcExt) {
    Say "      Could not find $ExtName in the download. Contact the tool owner." "Red"
    return
}
Say "      Downloaded." "Green"

# ---------- STEP 3: install into pyRevit's extensions folder ----------
Say "`n[3/3] Installing into pyRevit..." "Cyan"

# pyRevit ALWAYS scans this folder, so no Settings change is needed
$extRoot = Join-Path $env:APPDATA "pyRevit\Extensions"
New-Item -ItemType Directory -Force -Path $extRoot | Out-Null

$dest = Join-Path $extRoot $ExtName
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }   # remove old version
Copy-Item $srcExt.FullName -Destination $extRoot -Recurse -Force

Say "      Installed to: $dest" "Green"

# ---------- cleanup ----------
Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue

# ---------- done ----------
Say "`n========================================" "Cyan"
Say "  DONE!" "Green"
Say "========================================" "Cyan"
Say "Next steps:" "White"
Say "  1. Open Revit (or restart it if it was open)." "White"
Say "  2. On the pyRevit tab, click Reload." "White"
Say "  3. The SBP tab will appear on the ribbon.`n" "White"
