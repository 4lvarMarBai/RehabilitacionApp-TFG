@echo off
setlocal
cd /d "%~dp0"

set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
if not exist "%ROOT%logs" mkdir "%ROOT%logs"
set "LOG=%ROOT%logs\launcher.log"

if not exist "%ROOT%cliente\app.py" goto app_missing

if not exist "%PYTHON_EXE%" (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%ROOT%.venv" >> "%LOG%" 2>&1
    ) else (
        where python >nul 2>&1
        if errorlevel 1 goto python_missing
        python -m venv "%ROOT%.venv" >> "%LOG%" 2>&1
    )
    if errorlevel 1 goto venv_failed
)

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto python_version

"%PYTHON_EXE%" -c "import streamlit, requests, pandas, matplotlib" >nul 2>&1
if errorlevel 1 (
    echo Installing application dependencies... >> "%LOG%"
    "%PYTHON_EXE%" -m pip install -r "%ROOT%requirements.txt" >> "%LOG%" 2>&1
    if errorlevel 1 goto install_failed
)


"%PYTHON_EXE%" -m streamlit run "%ROOT%cliente\app.py" --server.headless=false --server.address=127.0.0.1 >> "%LOG%" 2>&1
if errorlevel 1 goto runtime_failed
exit /b 0

:app_missing
echo ERROR: app.py no existe en %ROOT% > "%LOG%"
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('No se encuentra cliente\app.py dentro del repositorio. Comprueba que has descargado el repositorio completo.','RehabilitacionApp') | Out-Null"
exit /b 1

:python_missing
echo ERROR: Python 3 no está instalado o no está en PATH. >> "%LOG%"
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Instala Python 3.11 o posterior y vuelve a iniciar la aplicación.','RehabilitacionApp') | Out-Null"
exit /b 1

:python_version
echo ERROR: se necesita Python 3.11 o posterior. >> "%LOG%"
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Se necesita Python 3.11 o posterior. Instala esa versión y vuelve a iniciar.','RehabilitacionApp') | Out-Null"
exit /b 1

:venv_failed
echo ERROR: no se pudo crear .venv. >> "%LOG%"
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('No se pudo crear el entorno Python. Consulta launcher.log.','RehabilitacionApp') | Out-Null"
exit /b 1

:install_failed
echo ERROR: falló la instalación de requirements.txt. >> "%LOG%"
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('No se pudieron instalar las dependencias. Comprueba Internet y consulta launcher.log.','RehabilitacionApp') | Out-Null"
exit /b 1

:runtime_failed
echo ERROR: Streamlit terminó con error. Revisa el registro de inicio. >> "%LOG%"
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('La aplicación se cerró con un error. Consulta launcher.log.','RehabilitacionApp') | Out-Null"
exit /b 1
