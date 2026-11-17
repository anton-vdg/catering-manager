@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$o = (Get-Location).Path;" ^
  "$d = [Environment]::GetFolderPath('Desktop');" ^
  "$l = (New-Object -ComObject WScript.Shell).CreateShortcut(\"$d\Catering Manager.lnk\");" ^
  "$l.TargetPath = \"$env:SystemRoot\System32\cmd.exe\";" ^
  "$l.Arguments = '/c \"' + $o + '\start.bat\"';" ^
  "$l.WorkingDirectory = $o;" ^
  "$l.WindowStyle = 7;" ^
  "if (Test-Path \"$o\icon.ico\") { $l.IconLocation = \"$o\icon.ico\" };" ^
  "$l.Save()"
echo Verknuepfung "Catering Manager" wurde auf dem Desktop angelegt.
pause