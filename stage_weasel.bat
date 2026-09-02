@echo off
call "J:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x64
if errorlevel 1 goto error
cd /d d:\desktop\input\weasel
call build.bat data opencc weasel installer
if errorlevel 1 goto error
echo ====== WEASEL STAGE DONE ======
exit /b 0
:error
echo ====== WEASEL STAGE FAILED ======
exit /b 1
