@echo off
setlocal
cd /d "%~dp0"
py -3 deployment\build_static_site.py
if errorlevel 1 (
  echo Static web build failed.
  exit /b 1
)
echo Static web build completed: dist\web-static
endlocal
