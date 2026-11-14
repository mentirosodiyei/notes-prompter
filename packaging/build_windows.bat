@echo off
setlocal
rem Genera dist\notes-prompter.exe desde cualquier directorio.
rem Opcional: build_windows.bat "C:\ruta\a\python.exe"
pushd "%~dp0.." || exit /b 1
if not "%~1"=="" (
  set "NP_PYTHON=%~1"
) else if exist ".venv\Scripts\python.exe" (
  set "NP_PYTHON=%CD%\.venv\Scripts\python.exe"
) else (
  where py >nul 2>&1
  if errorlevel 1 (set "NP_PYTHON=python") else (set "NP_PYTHON=py")
)
"%NP_PYTHON%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || goto :error
"%NP_PYTHON%" -m pip install -e ".[build]" || goto :error
"%NP_PYTHON%" -m PyInstaller --noconfirm --clean notes-prompter.spec || goto :error
echo.
echo Listo: dist\notes-prompter.exe
popd
exit /b 0
:error
echo.
echo La construccion ha fallado. Comprueba Python 3.11+, pip y las dependencias.
popd
exit /b 1
