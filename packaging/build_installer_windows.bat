@echo off
setlocal
rem Genera dist\Notes-Prompter-Setup-0.5.0.exe con Inno Setup 7 de 64 bits.
rem Uso: build_installer_windows.bat "C:\ruta\ISCC.exe" ["C:\ruta\python.exe"]
pushd "%~dp0.." || exit /b 1
if not "%~1"=="" set "NP_ISCC=%~1"
if not defined NP_ISCC if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "NP_ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined NP_ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "NP_ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if not defined NP_ISCC for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined NP_ISCC set "NP_ISCC=%%I"
if not defined NP_ISCC (
  echo No se encuentra Inno Setup 7 de 64 bits. Pasa la ruta de ISCC.exe como primer argumento.
  goto :error
)
if not exist "%NP_ISCC%" (
  echo No existe el compilador indicado.
  goto :error
)
call packaging\build_windows.bat "%~2" || goto :error
"%NP_ISCC%" packaging\windows_installer.iss || goto :error
echo.
echo Listo: dist\Notes-Prompter-Setup-0.5.0.exe
popd
exit /b 0
:error
echo.
echo No se ha podido generar el instalador.
popd
exit /b 1
