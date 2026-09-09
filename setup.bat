@echo off
REM AeroDrift setup script (Windows)

python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt

echo.
echo Setup complete. Run "run.bat" to start, or "run_tests.bat" for tests.
