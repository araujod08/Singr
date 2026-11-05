@echo off
REM Reabre este script dentro de "cmd /k": a janela NUNCA fecha sozinha, mesmo se algo der errado.
if /i not "%~1"=="--interno" cmd /k ""%~f0" --interno" & exit /b
setlocal EnableExtensions
cd /d "%~dp0"
title Karaoke - criar musicas
set "PYTHONUTF8=1"
REM o winget instala o ffmpeg aqui; assim ele e achado sem reabrir a janela
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"

echo ============================================
echo   Karaoke - criar musicas a partir de audios
echo ============================================
echo.

REM ---- onde estao as musicas e as ferramentas (funciona na pasta do programa e na do projeto) ----
set "PASTA=songs"
if not exist "Karaoke.exe" if exist "Karaoke App\songs" set "PASTA=Karaoke App\songs"
set "FERR=tools"
if exist "ferramentas\audio_to_ultrastar.py" set "FERR=ferramentas"
if not exist "%FERR%\audio_to_ultrastar.py" goto :sem_ferramentas
if not exist "%PASTA%" mkdir "%PASTA%"

echo Pasta de musicas: %CD%\%PASTA%
echo.
echo   1. Coloque o audio (mp3 ou wav) na pasta de musicas, de preferencia como
echo      "Artista - Titulo.mp3"  (use a gravacao original, com a voz)
echo   2. Se tiver a letra, salve em TEXTO com o mesmo nome: "Artista - Titulo.txt"
echo   3. Esta janela cria o playback sem a voz e o song.txt com a letra
echo.

REM ---- Python 3.11 a 3.14 (o 3.15 ainda nao funciona com o demucs) ----
set "VENV=%LOCALAPPDATA%\Karaoke\ferramentas-venv"
if exist "%VENV%\Scripts\python.exe" goto :venv_ok
call :achar_python
if defined PY goto :criar_venv
echo Nao achei o Python 3.11 a 3.14 neste computador.
choice /c SN /m "Instalar o Python 3.12 agora (winget)"
if errorlevel 2 goto :sem_python
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
call :achar_python
if not defined PY goto :reabrir
:criar_venv
echo Criando o ambiente das ferramentas (so na primeira vez)...
%PY% -m venv "%VENV%"
if errorlevel 1 goto :erro
:venv_ok

REM ---- ffmpeg ----
where ffmpeg >nul 2>nul
if not errorlevel 1 goto :ffmpeg_ok
echo O ffmpeg nao esta instalado.
choice /c SN /m "Instalar o ffmpeg agora (winget)"
if errorlevel 2 goto :sem_ffmpeg
winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
where ffmpeg >nul 2>nul
if errorlevel 1 goto :reabrir
:ffmpeg_ok

REM ---- bibliotecas (so na primeira vez; precisa de internet e baixa alguns GB) ----
call "%VENV%\Scripts\activate.bat"
python -c "import demucs, librosa" >nul 2>nul
if not errorlevel 1 goto :rodar
echo Instalando as bibliotecas das ferramentas. Pode demorar bastante, so acontece uma vez...
python -m pip install --upgrade pip
python -m pip install -r "%FERR%\requirements-tools.txt"
if errorlevel 1 goto :erro

:rodar
echo.
echo Processando (cada musica leva alguns minutos)...
python "%FERR%\audio_to_ultrastar.py" --songs "%PASTA%"
if errorlevel 1 goto :erro
echo.
echo ============================================
echo   PRONTO! Abra o Karaoke e clique em Recarregar.
echo   Para corrigir uma letra: edite o letra.txt dentro da pasta da musica
echo   e rode este arquivo de novo (e rapido).
echo   Pode fechar esta janela.
echo ============================================
exit /b 0

:achar_python
set "PY="
for %%V in (3.12 3.13 3.11 3.14) do if not defined PY py -%%V -c "pass" >nul 2>nul && set "PY=py -%%V"
exit /b 0

:sem_ferramentas
echo.
echo Nao encontrei a pasta "ferramentas" (ou "tools") ao lado deste arquivo.
echo Mantenha o criar_musicas.bat junto das outras pastas do programa.
exit /b 1

:sem_python
echo.
echo Sem o Python 3.11 a 3.14 nao da para criar musicas. Para instalar:
echo     winget install Python.Python.3.12
echo Depois feche esta janela e rode este arquivo de novo.
exit /b 1

:sem_ffmpeg
echo.
echo Sem o ffmpeg nao da para criar musicas. Para instalar:
echo     winget install Gyan.FFmpeg
echo Depois feche esta janela e rode este arquivo de novo.
exit /b 1

:reabrir
echo.
echo Instalado! Feche esta janela e abra este arquivo de novo para continuar.
exit /b 0

:erro
echo.
echo ERRO: algo falhou. Leia as mensagens acima e me envie se precisar de ajuda.
exit /b 1
