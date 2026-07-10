@echo off
setlocal EnableExtensions
cd /d %~dp0

set "PYTHON_EXE="
set "PYTHON_ARGS="

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
)

if not defined PYTHON_EXE (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
        set "PYTHON_ARGS="
    )
)

if not defined PYTHON_EXE (
    if exist "%USERPROFILE%\.pyenv\pyenv-win\versions\3.9.13\python.exe" (
        "%USERPROFILE%\.pyenv\pyenv-win\versions\3.9.13\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON_EXE=%USERPROFILE%\.pyenv\pyenv-win\versions\3.9.13\python.exe"
            set "PYTHON_ARGS="
        )
    )
)

if not defined PYTHON_EXE goto no_python

echo [1/4] Creating virtual environment...
"%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
if errorlevel 1 goto error

echo [2/4] Installing packages...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 goto error

echo [3/4] Building no-install EXE...
.venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --windowed --name IOLMasterParser --add-data "models\biometry_ood_age_stratified_v2.json;models" IOLMasterParser_app.py
if errorlevel 1 goto error

echo [4/4] Done.
echo EXE location: %cd%\dist\IOLMasterParser.exe
pause
exit /b 0

:no_python
echo.
echo Build failed. Python 3.9 or newer was not found.
echo Install Python from python.org, or set up pyenv-win with Python 3.9+.
pause
exit /b 1

:error
echo.
echo Build failed. Please copy the error message above.
pause
exit /b 1
