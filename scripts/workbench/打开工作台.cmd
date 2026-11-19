@echo off
setlocal
set "PYTHONUTF8=1"

py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 goto use_python

echo Python 3.11 or newer is required to start the workbench.
pause
exit /b 1

:use_py
py -3 "%~dp0launch.py" --ask-project %*
goto finish

:use_python
python "%~dp0launch.py" --ask-project %*

:finish
set "WORKBENCH_STATUS=%ERRORLEVEL%"
if not "%WORKBENCH_STATUS%"=="0" pause
exit /b %WORKBENCH_STATUS%
