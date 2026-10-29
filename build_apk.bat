@echo off
echo =========================================
echo       Building FramePlayer APK
echo =========================================
echo.
echo Setting UTF-8 encoding to prevent Flet packaging errors...
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo Running: flet build apk...
flet build apk

echo.
echo =========================================
echo Build finished! 
echo If successful, your APK is in the build\apk folder.
echo =========================================
pause
