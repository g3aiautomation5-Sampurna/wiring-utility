@echo off
:: Launches PowerShell script with Administrator privileges
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0rename_camera.ps1\"' -Verb RunAs"
