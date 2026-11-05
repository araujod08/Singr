"""Letra em texto -> sílabas (português) -> notas do song.txt.

Uso pelo audio_to_ultrastar.py: se existir uma letra (.txt) para a música, ela é dividida em
sílabas e distribuída sobre as notas extraídas do áudio. O resultado é uma boa aproximação:
revise no Yass Reloaded se quiser sincronia perfeita.

Formato da letra (um .txt simples):
  - uma linha de texto = uma linha cantada na tela (use as quebras que quiser ver no karaokê)
  - linhas em branco são ignoradas
  - linhas entre colchetes, como [Refrão], e linhas começando com # são ignoradas
  - marcações como "2x" soltas são ignoradas
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from itertools import accumulate

VOGAIS = set("aeiouáéíóúâêôãõàü")
FORTES = set("aeoáéóâêôãõà")
INSEPARAVEIS = {"bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "tr", "vr",
                "ch", "lh", "nh", "qu", "gu"}


# ------------------------------------------------------------------ sílabas
def _eh_vogal(w: str, i: int) -> bool:
    c = w[i]
    if c not in VOGAIS:
        return False
    if c == "u":
        if i > 0 and w[i - 1] == "q":  # "qu" (que, qui, quando): u não forma sílaba
            return False
        if i > 0 and w[i - 1] == "g" and i + 1 < len(w) and w[i + 1] in "eéêií":  # gue, gui
            return False
    return True


def _hiato(w: str, j: int) -> bool:
    """True se entre w[j] e w[j+1] há hiato (duas sílabas) em vez de ditongo."""
    a, b = w[j], w[j + 1]
    if a in "ãõ":  # ão, ãe, õe
        return False
    if b in "íú" or a in "íú":  # sa-í-da, ba-ú
        return True
    if a in FORTES and b in FORTES:  # co-e-lho, vo-o
        return True
    if a in FORTES and b in "iu" and w[j + 2:j + 4] == "nh":  # ra-i-nha
        return True
    return False


def _nucleos(w: str) -> list[tuple[int, int]]:
    nuc, i, n = [], 0, len(w)
    while i < n:
        if _eh_vogal(w, i):
            j = i
            while j + 1 < n and _eh_vogal(w, j + 1) and not _hiato(w, j):
                j += 1
            nuc.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    return nuc


def silabas_palavra(palavra: str) -> list[str]:
    """Divide uma palavra em sílabas (regras gerais do português; exceções podem errar)."""
    w = palavra.lower()
    nuc = _nucleos(w)
    if len(nuc) <= 1:
        return [palavra]
    cortes = []
    for (_, e0), (s1, _) in zip(nuc, nuc[1:]):
        cons = w[e0:s1]
        if len(cons) == 0:
            cortes.append(s1)
        elif len(cons) == 1:
            cortes.append(e0)  # consoante única vai para a sílaba seguinte
        elif cons[-2:] in INSEPARAVEIS:
            cortes.append(s1 - 2)
        else:
            cortes.append(s1 - 1)
    pontos = [0] + cortes + [len(palavra)]
    return [palavra[a:b] for a, b in zip(pontos, pontos[1:])]


def silabas_linha(linha: str) -> list[str]:
    """Sílabas de uma linha; a última sílaba de cada palavra leva um espaço no fim."""
    saida: list[str] = []
    for tok in linha.split():
        if re.fullmatch(r"\(?(\d+x|x\d+)\)?", tok.lower()):
            continue  # "2x", "x2": marcação de repetição, não é letra
        pre, core, pos = re.match(r"^(\W*)(.*?)(\W*)$", tok, re.UNICODE).groups()
        if not re.search(r"[^\W\d_]", core):
            continue  # sem letras
        sils: list[str] = []
        carry = ""
        for parte in re.findall(r"[^-'’]+[-'’]?", core):  # d'água, faz-me
            if not _nucleos(parte.lower()):
                carry += parte  # pedaço sem vogal (d', s'): gruda no seguinte
                continue
            s = silabas_palavra(parte)
            s[0] = carry + s[0]
            carry = ""
            sils.extend(s)
        if not sils:
            continue
        if carry:
            sils[-1] += carry
        sils[0] = pre + sils[0]
        sils[-1] = sils[-1] + pos + " "
        saida.extend(sils)
    if saida:
        saida[-1] = saida[-1].rstrip()
    return saida


def ler_letra(texto: str) -> list[list[str]]:
    """Texto da letra -> lista de linhas, cada uma uma lista de sílabas."""
    linhas = []
    for bruta in texto.splitlines():
        s = bruta.strip()
        if not s or s.startswith("#") or (s.startswith("[") and s.endswith("]")):
            continue
        sil = silabas_linha(s)
        if sil:
            linhas.append(sil)
    return linhas


# ------------------------------------------------------------------ notas
# Uma nota é uma lista [início_s, fim_s, pitch_midi, texto].
def agrupar_por_pausa(notas: list[list], pausa: float = 0.7) -> list[list[list]]:
    linhas: list[list[list]] = []
    anterior = None
    for n in notas:
        if anterior is None or n[0] - anterior >= pausa:
            linhas.append([])
        linhas[-1].append(n)
        anterior = n[1]
    return linhas


def dividir_notas(notas: list[list], onsets: list, alvo: int,
                  margem: float = 0.10, espaco: float = 0.10) -> list[list]:
    """Divide notas até chegar a `alvo` notas: primeiro nos ataques de sílaba detectados no áudio
    (mais fortes primeiro), depois ao meio nas notas mais longas."""
    notas = [list(n) for n in notas]
    falta = alvo - len(notas)
    if falta <= 0:
        return notas
    inicios = [n[0] for n in notas]
    cortes: dict[int, list[float]] = {}
    cand = []
    for t, forca in onsets:
        i = bisect_right(inicios, t) - 1
        if i >= 0 and notas[i][0] + margem <= t <= notas[i][1] - margem:
            cand.append((forca, t, i))
    cand.sort(reverse=True)
    for _, t, i in cand:
        if falta <= 0:
            break
        ts = cortes.setdefault(i, [])
        if all(abs(t - x) >= espaco for x in ts):
            ts.append(t)
            falta -= 1
    saida: list[list] = []
    for i, n in enumerate(notas):
        pts = [n[0]] + sorted(cortes.get(i, [])) + [n[1]]
        saida.extend([a, b, n[2], "~"] for a, b in zip(pts, pts[1:]))
    while falta > 0:  # sem mais ataques: divide as notas mais longas ao meio
        j = max(range(len(saida)), key=lambda k: saida[k][1] - saida[k][0])
        a, b, p, _ = saida[j]
        if b - a < 0.24:
            break
        m = (a + b) / 2
        saida[j:j + 1] = [[a, m, p, "~"], [m, b, p, "~"]]
        falta -= 1
    return saida


def _preencher_linha(notas: list[list], sils: list[str], onsets: list) -> list[list]:
    if len(notas) < len(sils):
        notas = dividir_notas(notas, onsets, len(sils))
    for n in notas:
        n[3] = "~"
    n_notas, n_sil = len(notas), len(sils)
    if n_notas >= n_sil:
        # espalha as sílabas pelas notas; as que sobram viram "~" (nota sustentada)
        pos = [0] if n_sil == 1 else [round(j * (n_notas - 1) / (n_sil - 1)) for j in range(n_sil)]
        for p, s in zip(pos, sils):
            notas[p][3] = s
    else:
        # ainda faltam notas: mais de uma sílaba por nota
        for j in range(n_notas):
            grupo = sils[j * n_sil // n_notas:(j + 1) * n_sil // n_notas]
            notas[j][3] = "".join(grupo)
    return notas


def alinhar_letra(notas: list[list], letra: list[list[str]], onsets: list,
                  gap_frase: float = 0.30) -> list[list[list]]:
    """Distribui a letra (linhas de sílabas) sobre as notas. Retorna as linhas de notas.

    1) cada linha da letra recebe uma fatia das notas proporcional ao seu número de sílabas
       (medido em tempo cantado), encaixada na pausa mais próxima;
    2) dentro da linha, as notas são divididas (ataques do áudio) ou deixadas como "~"
       até casar com o número de sílabas.
    """
    letra = [l for l in letra if l]
    n, k = len(notas), len(letra)
    if n == 0 or k == 0:
        raise ValueError("sem notas ou sem letra")
    if n < k:
        raise ValueError(f"só {n} notas para {k} linhas de letra")

    total_sil = sum(len(l) for l in letra)
    dur = [x[1] - x[0] for x in notas]
    acum = list(accumulate(dur))
    total_dur = acum[-1]
    pausas = [i for i in range(1, n) if notas[i][0] - notas[i - 1][1] >= gap_frase]
    tol = max(2, int(0.6 * n / k))

    fronteiras: list[int] = []
    soma, anterior = 0, 0
    for i in range(k - 1):
        soma += len(letra[i])
        bruto = bisect_left(acum, soma / total_sil * total_dur) + 1
        b = bruto
        if pausas:
            perto = min(pausas, key=lambda c: abs(c - bruto))
            if abs(perto - bruto) <= tol:
                b = perto
        b = max(anterior + 1, min(b, n - (k - 1 - i)))
        fronteiras.append(b)
        anterior = b

    cortes = [0] + fronteiras + [n]
    linhas = []
    for i in range(k):
        fatia = [list(x) for x in notas[cortes[i]:cortes[i + 1]]]
        linhas.append(_preencher_linha(fatia, letra[i], onsets))
    return linhas
