@echo off
REM Prepares the pack for a GitHub Release.  Edit the tag and the repository first.
cd /d "%~dp0.."
py tools\pack_publish.py --tag pack-2026.11.13 --repo OWNER/REPO
pause
