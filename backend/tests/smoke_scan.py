"""
Teste de fumaca da leitura optica de comprovantes.

Existe por um motivo concreto: uma refatoracao subiu para producao com um `import re`
faltando no modulo de visao. O py_compile do CI passou - NameError dentro de funcao so
aparece em execucao - e o scanner respondeu 500 no ar. Este teste executa o pipeline
inteiro de verdade, com Tesseract real, sobre comprovantes sinteticos que reproduzem o
layout dos bilhetes fisicos da Caixa.

Roda no CI antes do deploy. Falhou, nao sobe.
"""

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lottery_rules import NUMBER_RANGE_RULES  # noqa: E402
from ticket_scanner import ticket_scanner  # noqa: E402

FONT = cv2.FONT_HERSHEY_SIMPLEX
falhas = []


def texto(img, txt, x, y, escala=0.62, espessura=2):
    cv2.putText(img, txt, (x, y), FONT, escala, (15, 15, 15), espessura, cv2.LINE_AA)


def comprovante_quina():
    """Quina 7107: uma linha de aposta, cabecalho promocional da Mega e codigo longo."""
    img = np.full((820, 700, 3), 245, dtype=np.uint8)
    texto(img, "quina", 270, 80, 1.1, 3)
    texto(img, "MEGA-SENA ESTA EM 36 MILHOES!!", 40, 140, 0.55, 1)
    texto(img, "BORA? GARANTA SUA APOSTA E PARTICIPE", 40, 175, 0.5, 1)
    texto(img, "01SET2026        HORA DE 14:46:47", 40, 240, 0.55, 1)
    texto(img, "A  04  24  34  42  52", 60, 340, 0.95, 2)
    texto(img, "E. LOTERICO 04.007703-9  TERMINAL 060711", 40, 430, 0.5, 1)
    texto(img, "CONC 7107            01SET2026", 40, 480, 0.6, 2)
    texto(img, "TOTAL                R$ 3,00", 40, 530, 0.6, 2)
    texto(img, "78472444486523100176457300171Bc59", 40, 600, 0.5, 1)
    texto(img, "CONFIRA O RECIBO DA APOSTA", 40, 645, 0.5, 1)
    return img


def comprovante_lotomania():
    """Lotomania 2971: grade de 50 dezenas que fecha com uma linha de apenas duas."""
    img = np.full((1150, 760, 3), 245, dtype=np.uint8)
    texto(img, "lotomania", 220, 80, 1.1, 3)
    texto(img, "MEGA-SENA ESTA EM 36 MILHOES!!", 40, 140, 0.55, 1)
    texto(img, "01SET2026        HORA DE 14:46:23", 40, 210, 0.55, 1)

    grade = [
        ["01", "04", "05", "07", "09", "10"], ["11", "12", "14", "15", "18", "26"],
        ["28", "29", "31", "32", "36", "37"], ["38", "40", "41", "47", "50", "51"],
        ["54", "55", "57", "59", "60", "63"], ["66", "67", "68", "69", "70", "76"],
        ["78", "79", "82", "84", "85", "86"], ["87", "88", "91", "92", "93", "96"],
        ["97", "00"],
    ]
    for linha, dezenas in enumerate(grade):
        texto(img, "   ".join(dezenas), 90, 300 + linha * 62, 0.9, 2)

    texto(img, "E. LOTERICO 04.007703-9  TERMINAL 060711", 40, 900, 0.5, 1)
    texto(img, "CONC 2971            02SET2026", 40, 950, 0.6, 2)
    texto(img, "TOTAL                R$ 3,00", 40, 1000, 0.6, 2)
    texto(img, "37162444234923520176456700152203", 40, 1070, 0.5, 1)
    return img


def executar(nome, imagem, jogo_esperado, concurso_esperado, dezenas_esperadas):
    payload = cv2.imencode(".png", imagem)[1].tobytes()
    resultado = ticket_scanner.scan(payload)

    print(f"\n--- {nome} ---")
    print("  modalidade:", resultado["game_id"], "| concurso:", resultado["contest"])
    print("  dezenas lidas:", len(resultado["numbers"]), resultado["numbers"])
    print("  mensagem:", resultado["message"])

    if not resultado["success"] or len(resultado["numbers"]) != dezenas_esperadas:
        # Diagnostico: sem o texto bruto, uma falha de leitura no CI vira adivinhacao.
        print("  --- texto lido pelo OCR ---")
        for linha in resultado["raw_text"].splitlines():
            print("   |", linha)

    if resultado["game_id"] != jogo_esperado:
        falhas.append(f"{nome}: modalidade {resultado['game_id']}, esperado {jogo_esperado}")

    if resultado["contest"] != concurso_esperado:
        falhas.append(f"{nome}: concurso {resultado['contest']}, esperado {concurso_esperado}")

    if not resultado["success"]:
        falhas.append(f"{nome}: aposta recusada -> {resultado['message']}")

    lidas = resultado["numbers"]
    if len(lidas) != dezenas_esperadas:
        falhas.append(f"{nome}: {len(lidas)} dezenas lidas, esperado {dezenas_esperadas}")

    baixo, alto = NUMBER_RANGE_RULES[jogo_esperado]
    fora = [n for n in lidas if not (len(n) == 2 and baixo <= int(n) <= alto)]
    if fora:
        falhas.append(f"{nome}: dezenas fora da faixa da modalidade: {fora}")


def main():
    disponivel, motivo = ticket_scanner.is_available()
    if not disponivel:
        print(f"ERRO: stack optica indisponivel no ambiente de teste: {motivo}")
        return 1

    executar("Quina 7107", comprovante_quina(), "quina", 7107, 5)
    executar("Lotomania 2971", comprovante_lotomania(), "lotomania", 2971, 50)

    print()
    if falhas:
        for falha in falhas:
            print("FALHA:", falha)
        return 1

    print("Leitura optica validada: modalidade, concurso e dezenas conferem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
