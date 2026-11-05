# 🎤 Karaokê Desktop

Aplicativo de karaokê desenvolvido em Python, com reprodução de músicas, visualização de notas em tempo real, reconhecimento de pitch pelo microfone e sistema de pontuação de até **10.000 pontos**.

O projeto utiliza o formato UltraStar para sincronizar letras e notas musicais, permitindo avaliar a precisão vocal durante a execução da música.

## Funcionalidades

- Reprodução de áudio local.
- Interface desktop desenvolvida com PySide6.
- Visualização das notas musicais em movimento (Note Roll).
- Exibição sincronizada das letras.
- Captura de áudio pelo microfone.
- Detecção de pitch utilizando algoritmo YIN com FFT.
- Pontuação em tempo real, de 0 a 10.000.
- Sistema de combo e notas especiais.
- Calibração de latência do microfone.
- Suporte a diferentes dispositivos e interfaces de áudio.
- Biblioteca de músicas com atualização automática.
- Importação de músicas no formato UltraStar.
- Geração automática de arquivos UltraStar a partir de áudio e letras.
- Separação vocal e instrumental utilizando Demucs.
- Transcrição automática de letras com Whisper.
- Geração de executável para Windows.

## Tecnologias

| Tecnologia | Utilização |
|---|---|
| Python | Linguagem principal |
| PySide6 | Interface gráfica |
| pygame-ce | Reprodução de áudio |
| NumPy / SciPy | Processamento de sinais |
| YIN + FFT | Detecção de frequência vocal |
| Demucs | Separação vocal e instrumental |
| faster-whisper | Transcrição de letras |
| FFmpeg | Processamento e conversão de áudio |
| PyInstaller | Geração do executável |
| UltraStar | Formato de letras e notas |

## Requisitos

- Python 3.11 a 3.14.
- Windows, Linux ou macOS para execução pelo código-fonte.
- FFmpeg para as ferramentas de processamento de áudio.
- Microfone.
- Fones de ouvido recomendados.

## Instalação e execução

Clone o repositório:

```bash
git clone <URL_DO_REPOSITORIO>
cd karaoke-UMP
```

Crie e ative o ambiente virtual:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

Opcionalmente, gere a música de demonstração:

```bash
python tools/make_demo.py
```

Execute o aplicativo:

```bash
python main.py
```

## Como utilizar

1. Conecte o microfone e utilize fones de ouvido.
2. Abra o aplicativo.
3. Clique em **Testar microfone** para verificar a captura de áudio.
4. Ajuste o dispositivo de entrada e o portão de ruído, se necessário.
5. Escolha uma música na biblioteca.
6. Clique em **Cantar** para iniciar.
7. Acompanhe as notas e letras enquanto canta.
8. Ao terminar, consulte sua pontuação.

### Controles

- `Espaço`: pausar ou continuar.
- `Esc`: sair da sessão.

### Configuração de áudio

**Microfone e interface de áudio**

É possível selecionar o dispositivo de captura e a entrada utilizada na interface de áudio.

Microfones condensadores podem precisar de alimentação phantom power (+48V). Microfones dinâmicos normalmente não precisam.

**Portão de ruído**

Define o nível mínimo de áudio necessário para que a captura seja considerada válida.

**Calibração de latência**

Compensa o atraso entre a execução da música e a captura da voz.

Como referência inicial, utilize 150 ms. Fones Bluetooth podem exigir valores maiores, geralmente entre 300 e 500 ms.

## Sistema de pontuação

A pontuação é calculada continuamente comparando a frequência vocal detectada com a nota musical esperada.

Pontuação máxima: **10.000 pontos**.

### Níveis de dificuldade

| Dificuldade | Tolerância |
|---|---:|
| Fácil | ±80 cents |
| Normal | ±55 cents |
| Difícil | ±35 cents |

- Acertos dentro da tolerância recebem pontuação integral.
- Acertos dentro do dobro da tolerância recebem pontuação parcial.
- A comparação ignora a oitava, permitindo cantar em registros diferentes.
- Notas douradas (`*`) valem o dobro.
- Notas livres (`F`) não pontuam.
- Notas com pelo menos 60% de aproveitamento aumentam o combo.

## Adicionando músicas

Cada música deve possuir sua própria pasta dentro de `songs/`.

Estrutura:

```text
songs/
└── minha-musica/
    ├── song.txt
    └── playback.mp3
```

Formatos de áudio aceitos:

- MP3
- OGG
- WAV
- FLAC

O arquivo `song.txt` utiliza o formato UltraStar, contendo as notas musicais, letras, duração e informações de sincronização.

## Geração automática de músicas

O projeto possui ferramentas para transformar gravações originais em músicas compatíveis com o karaokê.

### Método recomendado: criar_musicas.bat

1. Coloque a gravação original com voz dentro de `songs/`.
2. Adicione a letra em texto com o mesmo nome do áudio.
3. Execute `criar_musicas.bat`.
4. Aguarde o processamento.
5. Abra o karaokê e clique em **Recarregar**.

Exemplo:

```text
songs/
├── Artista - Musica.mp3
└── Artista - Musica.txt
```

O processamento utiliza:

- Demucs para separar voz e instrumental.
- faster-whisper para transcrição automática opcional.
- Análise de áudio para identificar notas e ataques vocais.
- Divisão silábica para distribuir a letra.
- Geração do arquivo `song.txt`.

A análise é armazenada em `analise.json`, permitindo corrigir a letra posteriormente sem processar novamente todo o áudio.

Para refazer completamente o processamento:

```bash
python ferramentas/audio_to_ultrastar.py --songs songs --refazer
```

Para executar a ferramenta manualmente:

```bash
python ferramentas/audio_to_ultrastar.py --songs songs
```

### Utilizando Whisper

O Whisper é utilizado na etapa de preparação das músicas para reconhecimento e transcrição de letras.

A implementação utiliza `faster-whisper`, com o modelo `small` e configuração `int8`.

A transcrição é uma alternativa à inclusão manual da letra, mas pode apresentar erros devido à música de fundo, efeitos vocais e características da gravação.

**Importante:** o Whisper não realiza reconhecimento de canto ao vivo nem participa diretamente do cálculo da pontuação vocal.

## Outras formas de criar músicas

### Arquivo MIDI

É possível gerar arquivos UltraStar a partir de uma melodia em MIDI:

```bash
python tools/midi_to_ultrastar.py musica.mid --listar
```

Depois de identificar a faixa desejada:

```bash
python tools/midi_to_ultrastar.py musica.mid --track N --saida songs/minha-musica --titulo "Minha Música" --audio playback.mp3
```

### Editores externos

Também é possível criar ou corrigir as notas utilizando:

- Yass Reloaded.
- UltraStar Creator.

## Gerando o executável Windows

O projeto disponibiliza o script:

```text
build.bat
```

Execute com dois cliques para:

1. Criar o ambiente virtual.
2. Instalar as dependências.
3. Gerar o executável utilizando PyInstaller.
4. Criar a pasta `Karaoke App`.
5. Copiar os arquivos necessários.
6. Disponibilizar `Karaoke.exe` e a pasta `songs/`.
7. Oferecer a criação de um atalho na Área de Trabalho.

A pasta final pode ser distribuída compactada.

Ao executar novamente o processo de build, as músicas adicionadas pelo usuário em `Karaoke App/songs` são preservadas.

## Estrutura do projeto

```text
karaoke-UMP/
│
├── main.py
├── requirements.txt
├── build.bat
├── criar_musicas.bat
├── icon.ico
│
├── assets/
│   └── icon.png
│
├── karaoke/
│   ├── song.py
│   ├── pitch.py
│   ├── scoring.py
│   ├── player.py
│   └── ui.py
│
├── tools/
│   ├── make_demo.py
│   ├── midi_to_ultrastar.py
│   ├── audio_to_ultrastar.py
│   └── letras_pt.py
│
├── songs/
│   └── ...
│
└── ferramentas/
    └── ...
```

### Principais módulos

| Módulo | Responsabilidade |
|---|---|
| `main.py` | Inicialização do aplicativo |
| `karaoke/song.py` | Parser UltraStar e biblioteca de músicas |
| `karaoke/pitch.py` | Captura do microfone e detecção de pitch |
| `karaoke/scoring.py` | Pontuação, combo e avaliação das notas |
| `karaoke/player.py` | Reprodução de áudio e controle do relógio |
| `karaoke/ui.py` | Interface gráfica e telas do karaokê |
| `tools/` | Ferramentas auxiliares de geração de músicas |

## Direitos autorais

Playbacks, gravações e letras de músicas comerciais podem estar protegidos por direitos autorais.

O aplicativo não deve ser distribuído com músicas comerciais sem as respectivas autorizações.

Para distribuição, disponibilize o aplicativo sem músicas protegidas e permita que cada usuário adicione seus próprios arquivos.

---

**Projeto:** Karaokê Desktop  
**Linguagem:** Python  
**Interface:** PySide6  
**Formato de músicas:** UltraStar  
**Plataforma principal:** Windows
