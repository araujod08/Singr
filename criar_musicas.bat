@echo off
setlocal
cd /d "%~dp0"
title Karaoke - criar musicas

echo ============================================
echo   Karaoke - criar musicas a partir de audios
echo ============================================
echo.

REM ---- pasta de musicas: a do programa pronto, se existir; senao a do projeto ----
set "PASTA=Karaoke App\songs"
if not exist "%PASTA%" set "PASTA=songs"
if not exist "%PASTA%" mkdir "%PASTA%"
echo Pasta de musicas: %CD%\%PASTA%
echo (coloque os audios .mp3/.wav ali, de preferencia como "Artista - Titulo.mp3")
echo.

REM ---- ambiente virtual SO das ferramentas (.venv-tools) ----
REM O demucs precisa de Python 3.11 a 3.14: no 3.15 ainda nao ha pacotes prontos e a instalacao falha.
if exist ".venv-tools\Scripts\python.exe" goto :venv_ok
echo Criando o ambiente das ferramentas...
for %%V in (3.12 3.13 3.11 3.14) do if not exist ".venv-tools\Scripts\python.exe" py -%%V -m venv .venv-tools 2>nul
if not exist ".venv-tools\Scripts\python.exe" goto :sem_python
echo.
echo Nao achei o Python 3.11 a 3.14 (o 3.15 nao serve para o demucs). Instale com:
echo     winget install Python.Python.3.12
echo Depois feche esta janela, abra uma nova e rode este arquivo de novo.
pause
exit /b 1

:sem_ffmpeg
python -c "import demucs, librosa" >nul 2>nul
if not errorlevel 1 goto :rodar
echo Instalando as ferramentas (so na primeira vez; pode demorar e baixar ate ~2 GB)...
python -m pip install -q --upgrade pip
python -m pip install -r requirements-tools.txt
if errorlevel 1 goto :erro

:rodar
set "EXTRA="
choice /c NS /m "Tentar transcrever a letra tambem (Whisper, erra bastante)"
if errorlevel 2 goto :com_letra
goto :executar
:com_letra
python -c "import faster_whisper" >nul 2>nul
if errorlevel 1 python -m pip install faster-whisper
if errorlevel 1 goto :erro
set "EXTRA=--letra"

:executar
echo.
echo Processando (cada musica leva alguns minutos)...
python tools\audio_to_ultrastar.py --songs "%PASTA%" %EXTRA%
if errorlevel 1 goto :erro
echo.
echo ============================================
echo   PRONTO! Abra o Karaoke e clique em Recarregar.
echo ============================================
pause
exit /b 0

:sem_python
echo.
echo Python nao encontrado. Instale em python.org e marque "Add python.exe to PATH".
pause
exit /b 1

:sem_ffmpeg
echo.
echo ffmpeg nao encontrado. Instale com:  winget install ffmpeg
echo Depois feche esta janela, abra uma nova e rode este arquivo de novo.
pause
exit /b 1

:erro
echo.
echo ERRO: algo falhou. Leia as mensagens acima e me envie se precisar de ajuda.
pause
exit /b 1
