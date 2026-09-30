@echo off
REM Run the AeroDrift CLI (Windows). Examples:
REM   run.bat final-demo                     full self-heal loop + SQLite diff + PDF
REM   run.bat mid-review-demo                prove detection < 5 s after a manual SG change
REM   run.bat scan --scenario open-db        dashboard with an exposed database
REM   run.bat daemon --inject open-db --duration 10 --report report.pdf
REM   run.bat history                        stored snapshots and incidents
REM   run.bat diff baseline latest           topology diff between two snapshots/timestamps

call venv\Scripts\activate.bat
python -m aerodrift %*
