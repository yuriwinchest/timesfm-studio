@echo off
title TimesFM Studio - Local Launcher
cd /d %~dp0\backend

echo ===================================================
echo   TIMESFM STUDIO - GOOGLE RESEARCH FOUNDATION MODEL
echo ===================================================
echo.

if not exist ..\.venv (
    echo [1/3] Criando ambiente virtual Python (.venv)...
    python -m venv ..\.venv
)

echo [2/3] Ativando ambiente virtual e instalando dependencias...
call ..\.venv\Scripts\activate.bat
pip install -r requirements.txt

echo.
echo [3/3] Iniciando servidor FastAPI local...
echo Acesse a interface no seu navegador: http://localhost:8100
echo.
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
pause
