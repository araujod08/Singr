@echo off
setlocal
cd /d "%~dp0"
title Karaoke - gerar executavel

echo ============================================
echo   Karaoke - gerando o executavel
echo ============================================
echo.

REM ---- 1) ambiente virtual + dependencias (automatico) ----
if exist ".venv\Scripts\python.exe" goto :venv_ok
echo [1/4] Criando ambiente virtual...
py -3 -m venv .venv 2>nul || python -m venv .venv
if not exist ".venv\Scripts\python.exe" goto :sem_python
:venv_ok
call ".venv\Scripts\activate.bat"
echo [1/4] Instalando dependencias...
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 goto :erro

REM ---- 2) build ----
echo [2/4] Gerando o .exe (pode demorar 1 a 3 minutos)...
set "ICONE="
if exist "icon.ico" set "ICONE=--icon icon.ico"
if not exist "icon.ico" echo Aviso: icon.ico nao encontrado, o exe ficara com o icone padrao.
python -m PyInstaller --noconfirm --clean --noconsole --onedir --name Karaoke %ICONE% --add-data "assets;assets" --collect-all _sounddevice_data main.py
if errorlevel 1 goto :erro

REM ---- 3) pasta final facil de achar: "Karaoke App" ao lado deste arquivo ----
echo [3/4] Montando a pasta "Karaoke App"...
REM /MIR atualiza o programa, mas NAO mexe na subpasta songs (suas musicas ficam salvas)
robocopy "dist\Karaoke" "Karaoke App" /MIR /XD songs /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :erro
robocopy "songs" "Karaoke App\songs" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :erro
REM ferramentas para criar musicas: ficam FORA do .exe (podem ser atualizadas sem novo build)
robocopy "tools" "Karaoke App\ferramentas" audio_to_ultrastar.py letras_pt.py /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :erro
copy /Y "requirements-tools.txt" "Karaoke App\ferramentas\" >nul
copy /Y "criar_musicas.bat" "Karaoke App\" >nul
copy /Y "LEIA-ME.txt" "Karaoke App\" >nul

REM ---- 4) atalho na Area de Trabalho ----
echo [4/4] Atalho
choice /c SN /m "Criar atalho na Area de Trabalho"
if errorlevel 2 goto :fim
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Karaoke.lnk'); $s.TargetPath='%CD%\Karaoke App\Karaoke.exe'; $s.WorkingDirectory='%CD%\Karaoke App'; $s.Save()"
if errorlevel 1 echo Nao consegui criar o atalho, mas o programa esta pronto.

:fim
echo.
echo ============================================
echo   PRONTO!
echo   Programa: %CD%\Karaoke App\Karaoke.exe
echo   Musicas:  %CD%\Karaoke App\songs
echo ============================================
explorer "Karaoke App"
pause
exit /b 0

:sem_python
echo.
echo Python nao encontrado. Instale em python.org e marque "Add python.exe to PATH".
pause
exit /b 1

:erro
echo.
echo ERRO: algo falhou. Leia as mensagens acima e me envie se precisar de ajuda.
pause
exit /b 1
