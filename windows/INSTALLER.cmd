@echo off
title Recalbox RFID Launcher
echo.
echo ==============================================
echo  Recalbox RFID Launcher - installation
echo ==============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
