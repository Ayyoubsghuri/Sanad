@echo off
REM The 2024 tax code is installed as a NEW text next to your old one. This ends the old one on 2024-01-01
REM (questions dated before 2024 still use it). Stop the backend first.
REM   RETIRE_OLD_CGI.bat          shows which text would be ended (check the title!)
REM   RETIRE_OLD_CGI.bat apply    does it
cd /d "%~dp0.."
if "%1"=="apply" (
  py -m legalrag.builder.retire ORDER_1309.77 --until 2024-01-01 --note "replaced by the 2024 edition of the CGI" --apply
) else (
  py -m legalrag.builder.retire ORDER_1309.77 --until 2024-01-01
)
pause
