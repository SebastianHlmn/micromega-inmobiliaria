@echo off
cd /d %~dp0\..
echo Levantando PostgreSQL con Docker...
docker compose up -d postgres
echo.
echo Edita .env y cambia DATABASE_URL a:
echo postgresql+psycopg://micromega:micromega@localhost:5432/micromega
echo Luego reinicia la API y ejecuta: python -m app.seed
pause
