# Karaokê

Karaokê desktop em Python: toca o playback, mostra as notas rolando, ouve o microfone
e dá a pontuação (0 a 10.000).

## Rodar

```bash
python -m venv .venv
.venv\Scripts\activate        # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
python tools/make_demo.py     # (opcional) recria a música de demonstração
python main.py
```

## Gerar o .exe (Windows)

Dê dois cliques em `build.bat`. Ele cria o ambiente virtual, instala tudo, gera o executável e entrega
a pasta **`Karaoke App`** ao lado do `build.bat` (abre sozinha no fim), com `Karaoke.exe` e `songs\`.
Ele também pergunta se quer um atalho na Área de Trabalho.
Rodar de novo atualiza o programa sem apagar as músicas que você pôs em `Karaoke App\songs`.
Para distribuir, compacte a pasta `Karaoke App` inteira. O ícone do programa é o `icon.ico` da raiz
(o `assets/icon.png` é o da janela). Para trocar, substitua os dois e rode o `build.bat` de novo.

## Como usar

1. **Use fones de ouvido**, senão o microfone capta o playback.
2. Clique em **Testar microfone** e cante: o nível e a nota detectada devem aparecer.
3. Escolha a música e clique em **Cantar**. Espaço pausa, Esc sai.
4. **Interface de áudio / mic externo**: escolha o dispositivo em *Microfone* e a *Entrada* onde o mic
   está ligado (se ouvir silêncio, tente a outra entrada). Mic condensador precisa de phantom power (+48V)
   na interface; mic dinâmico, não.
5. **Portão de ruído**: abaixo desse nível (em dB) o app ignora o som. Durante o *Testar microfone* a tela
   mostra o nível atual e avisa "abaixo do portão"; ajuste o slider ao vivo até a sua voz passar
   e o ruído de fundo não. Ganho muito alto na interface distorce o pitch: a barra deve ficar em ~60–80%.
6. **Calibração de latência**: se você acerta mas o app diz que errou (ou o contrário),
   ajuste os ms. Comece em 150; fones Bluetooth precisam de bem mais (300–500).

## Pontuação

- A cada frame, compara a nota cantada com a nota esperada (já descontada a latência).
- Acerto cheio dentro da tolerância (Fácil ±80¢ · Normal ±55¢ · Difícil ±35¢); até o dobro vale meio ponto.
- A oitava é ignorada: homem cantando música de mulher pontua normalmente.
- Notas douradas (`*`) valem o dobro; notas livres (`F`) não pontuam.
- Combo: nota com ≥ 60% de acerto soma ao combo.

## Adicionar músicas

Cada música é uma pasta em `songs/`:

```
songs/minha-musica/
├─ song.txt        # formato UltraStar (notas + letra)
└─ playback.mp3    # também aceita .ogg, .wav, .flac
```

### Jeito automático (recomendado): `audio_to_ultrastar.py`

**Mais fácil:** dois cliques em `criar_musicas.bat` (na pasta do projeto, ao lado do `build.bat`).
Ele usa a pasta `Karaoke App\songs` se ela existir (senão, `songs`), instala o que falta na primeira vez
e processa os áudios novos, num ambiente próprio (`.venv-tools`) com Python 3.11 a 3.14
(se só tiver o 3.15, instale o 3.12: `winget install Python.Python.3.12`). Precisa do ffmpeg (`winget install ffmpeg`). Depois, abra o Karaokê e
clique em **Recarregar**. Essas ferramentas ficam só no seu computador: quem receber a pasta
`Karaoke App` não precisa delas, só das músicas já prontas.

Pela linha de comando (equivalente):

```bash
pip install -r requirements-tools.txt     # demucs + librosa (precisa de ffmpeg no PATH)
# 1) jogue os áudios ORIGINAIS (com voz) em songs/, de preferência como "Artista - Título.mp3"
# 2) rode:
python tools/audio_to_ultrastar.py            # só a melodia
python tools/audio_to_ultrastar.py --letra    # + tenta transcrever a letra (pip install faster-whisper)
```

Para cada áudio novo ele cria `songs/<nome>/` com o `playback.mp3` (voz removida pelo demucs),
o `song.txt` e o áudio original. Pastas que já têm `song.txt` são ignoradas.
Em CPU o demucs leva alguns minutos por música (`--device cuda` acelera se tiver placa NVIDIA).

Limitações: precisa da gravação **original com voz** (num playback não há melodia para extrair);
às vezes sai uma nota na oitava errada (não afeta a pontuação, que ignora oitava); a letra
transcrita erra bastante em português com música: revise no Yass Reloaded.

### Outras formas de criar o `song.txt`


- **A partir de um MIDI da melodia**: `python tools/midi_to_ultrastar.py musica.mid --listar`
  e depois `--track N --saida songs/minha-musica --titulo "..." --audio playback.mp3`.
- **Editor visual** (grátis): Yass Reloaded ou UltraStar Creator, marcando as notas ouvindo a música.
- **Hinos de domínio público**: grave o playback e crie o `.txt` sem problema de direitos.

Formato resumido: `: início duração tom sílaba` (início e duração em beats; tom 0 = Dó4;
`*` dourada, `F` livre, `- N` quebra de linha, `E` fim). 1 beat = 15/BPM segundos.

> Playbacks e letras de músicas atuais têm direitos autorais. Para uso pessoal/na igreja,
> tudo bem; se for distribuir o app, **não inclua as músicas**: deixe cada pessoa colocar as suas.

## Estrutura

```
main.py                 ponto de entrada
karaoke/song.py         parser UltraStar + varredura da pasta songs/
karaoke/pitch.py        captura do mic + YIN (via FFT)
karaoke/scoring.py      lógica de pontuação, combo e notas
karaoke/player.py       playback e relógio da música (contagem, pausa)
karaoke/ui.py           telas: biblioteca, canto (barras + letra), resultado
tools/                  make_demo.py, midi_to_ultrastar.py, audio_to_ultrastar.py
```
