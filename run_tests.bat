@echo off
REM Run the AeroDrift test suite (Windows)

call venv\Scripts\activate.bat
pytest -v
