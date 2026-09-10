@echo off
cd /d %~dp0\..
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
python -m app.seed
echo.
echo Listo. Ahora ejecuta scripts\run_api.bat y, en otra terminal, scripts\run_panel.bat
pause
