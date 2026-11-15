@echo off
setlocal
REM Makes the phone version of the law pack and uploads it to Hugging Face (folder "mobile" of Xdnh00p/sanad-lawpack).
cd /d "%~dp0.."
set REPO=Xdnh00p/sanad-lawpack

set PY=py
if exist "%~dp0..\..\env\Scripts\python.exe" set PY="%~dp0..\..\env\Scripts\python.exe"
if exist "%~dp0..\env\Scripts\python.exe" set PY="%~dp0..\env\Scripts\python.exe"

set HF=hf
where hf >nul 2>nul
if errorlevel 1 (
  if exist "%USERPROFILE%\.local\bin\hf.exe" (
    set HF="%USERPROFILE%\.local\bin\hf.exe"
  ) else (
    echo The Hugging Face tool "hf" was not found. Install it first:
    echo   powershell -ExecutionPolicy ByPass -c "irm https://hf.co/cli/install.ps1 | iex"
    pause
    exit /b 1
  )
)

echo === 1/2  Making the mobile pack (a few minutes) ===
%PY% tools\make_mobile_pack.py --out mobile_out
if errorlevel 1 (
  echo Making the mobile pack failed. Nothing was uploaded.
  pause
  exit /b 1
)

echo.
echo === 2/2  Uploading to Hugging Face (folder mobile) ===
%HF% upload %REPO% mobile_out\sanad_mobile.db mobile/sanad_mobile.db --repo-type=dataset
if errorlevel 1 goto fail
%HF% upload %REPO% mobile_out\sanad_mobile.vec mobile/sanad_mobile.vec --repo-type=dataset
if errorlevel 1 goto fail
%HF% upload %REPO% mobile_out\manifest.json mobile/manifest.json --repo-type=dataset
if errorlevel 1 goto fail
echo.
echo DONE. The app downloads it from https://huggingface.co/datasets/%REPO%/tree/main/mobile
pause
exit /b 0

:fail
echo Upload failed. If it is about login or permission run:  %HF% auth login --force  then run this file again.
pause
exit /b 1
