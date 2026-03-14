@echo off
title Polymarket Bot Dashboard
cd /d "%~dp0"
echo.
echo  ==========================================
echo   Polymarket Bot Dashboard
echo   Opening in your browser...
echo  ==========================================
echo.
echo  Press Ctrl+C to stop the server.
echo.
streamlit run dashboard.py --server.port 8501
pause
