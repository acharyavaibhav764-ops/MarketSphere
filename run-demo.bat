@echo off
REM MarketSphere one-click hackathon demo launcher.
REM Seeds the local database (first run only) and serves the UI at http://localhost:8000/
cd /d "%~dp0"
set DATABASE_URL=sqlite+aiosqlite:///./marketsphere.db
echo Seeding demo data...
python scripts\seed_demo.py
echo.
echo Starting MarketSphere at http://localhost:8000/ ...
start http://localhost:8000/
python -m uvicorn main:app --host 127.0.0.1 --port 8000
