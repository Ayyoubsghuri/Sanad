@echo off
setlocal
REM Publishes your law pack to Hugging Face (dataset Xdnh00p/sanad-lawpack).  Double-click it, or run it from the backend folder.
cd /d "%~dp0.."
set REPO=Xdnh00p/sanad-lawpack

where hf >nul 2>nul
if errorlevel 1 (
  echo The Hugging Face tool "hf" was not found. Install it, then CLOSE this window and run this file again:
  echo   powershell -ExecutionPolicy ByPass -c "irm https://hf.co/cli/install.ps1 | iex"
  pause
  exit /b 1
)

hf auth whoami >nul 2>nul
if errorlevel 1 (
  echo You are not logged in. Create a token with WRITE access at https://huggingface.co/settings/tokens
  echo and paste it below when asked. Do not share it with anyone.
  hf auth login
  hf auth whoami >nul 2>nul
  if errorlevel 1 (
    echo Login failed. Nothing was uploaded.
    pause
    exit /b 1
  )
)

echo.
echo === 1/3  Preparing the pack (copy, check the signature, write pack_release.json) ===
py tools\pack_publish.py --tag x --host hf --repo %REPO%
if errorlevel 1 (
  echo Preparing failed. Nothing was uploaded.
  pause
  exit /b 1
)

echo.
echo === 2/3  Uploading current.db (about 2 GB, this takes a while; if it stops, run this file again) ===
hf upload %REPO% release_out\current.db current.db --repo-type=dataset
if errorlevel 1 (
  echo Upload of current.db failed. Run this file again.
  pause
  exit /b 1
)

echo.
echo === 3/3  Uploading current.db.sig ===
hf upload %REPO% release_out\current.db.sig current.db.sig --repo-type=dataset
if errorlevel 1 (
  echo Upload of the signature failed. Run this file again.
  pause
  exit /b 1
)

echo.
echo DONE. Check https://huggingface.co/datasets/%REPO%  (both files must be there, and the dataset must be PUBLIC).
echo Then commit pack_release.json to GitHub.
pause
