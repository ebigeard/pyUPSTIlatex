@echo off
cls
"%~dp0..\..\..\pyUPSTIlatex_venv\Scripts\python.exe" -m pyupstilatex.cli compile --mode deep %*
pause