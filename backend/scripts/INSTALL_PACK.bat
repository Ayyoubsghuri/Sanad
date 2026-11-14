@echo off
REM Downloads and installs the law pack named in pack_release.json (stop the backend first, restart it after).
cd /d "%~dp0.."
py tools\install_pack.py
pause
