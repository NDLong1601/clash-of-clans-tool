@echo off
cd /d "%~dp0"
start "" /D "%~dp0" pythonw.exe "%~dp0gui.py" %*
