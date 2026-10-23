@echo off
title Dual-View Wiring Inspection Web Application
echo ======================================================================
echo Starting Dual-View Wiring Inspection Web Application...
echo Running at http://127.0.0.1:7860/
echo Opening in your default web browser automatically...
echo [Keep this window open while using the app. Close it to stop.]
echo ======================================================================

if exist "%~dp0web_wiring.exe" (
    "%~dp0web_wiring.exe"
) else if exist "%~dp0dist\web_wiring.exe" (
    "%~dp0dist\web_wiring.exe"
) else (
    python "%~dp0web_wiring.py"
)
pause

