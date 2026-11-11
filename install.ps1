# battery-bar installer: makes a venv, installs dependencies, adds a Start-with-Windows shortcut, starts it.
# Run from the repo folder:  powershell -ExecutionPolicy Bypass -File install.ps1
# Remove autostart later:    del "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\battery-bar.lnk"
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$py = (Get-Command py -ErrorAction SilentlyContinue)
if ($py) { & py -3 -m venv "$here\.venv" } else { & python -m venv "$here\.venv" }
& "$here\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$here\.venv\Scripts\python.exe" -m pip install --quiet -r "$here\requirements.txt"

$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\battery-bar.lnk"
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = "$here\.venv\Scripts\pythonw.exe"
$s.Arguments = "`"$here\run.pyw`""
$s.WorkingDirectory = $here
$s.Save()

Start-Process "$here\.venv\Scripts\pythonw.exe" -ArgumentList "`"$here\run.pyw`"" -WorkingDirectory $here
Write-Host "battery-bar installed and started. Config: $env:APPDATA\BatteryBar\config.toml"
