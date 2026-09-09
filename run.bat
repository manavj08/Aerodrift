@echo off
REM Run the AeroDrift CLI (Windows)

call venv\Scripts\activate.bat
python -m aerodrift.cli.main %*
