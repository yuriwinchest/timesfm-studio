"""
Camada de visao computacional da leitura de comprovantes.

Responsabilidade unica: transformar pixels em numeros de 2 digitos posicionados.
Nao conhece modalidade, nao valida aposta e nao conversa com a API da Caixa - quem
decide o que aquilo significa e o ticket_scanner.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from lottery_rules import BET_SIZE_RULES, NUMBER_RANGE_RULES

logger = logging.getLogger("ticket-vision")

try:
    import cv2
    import numpy as np
    CV_AVAILABLE = True
except ImportError:  # pragma: no cover - depende do ambiente de deploy
    CV_AVAILABLE = False

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:  # pragma: no cover
    OCR_AVAILABLE = False

try:
    from pyzbar import pyzbar
    ZBAR_AVAILABLE = True
except ImportError:  # pragma: no cover
    ZBAR_AVAILABLE = False

# Termos usados para pontuar a orientacao correta da foto do comprovante.
ORIENTATION_ANCHORS = (
    "loteria", "caixa", "concurso", "aposta", "lotomania", "quina",
    "lotofacil", "mega", "valor", "sena", "federal",
)

TESS_DIGITS = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789"
TESS_TEXT = "--oem 3 --psm 6"


class TicketVision:
    """Decodifica, orienta, realca e extrai dezenas posicionadas do comprovante."""

    def is_available(self):
        """Diz, sem eufemismo, se a stack optica esta de pe neste container."""
        if not CV_AVAILABLE:
            return False, "OpenCV nao instalado no container (opencv-python-headless)."
        if not OCR_AVAILABLE:
            return False, "pytesseract nao instalado no container."
        try:
            pytesseract.get_tesseract_version()
        except Exception as e:
            return False, f"Binario do Tesseract indisponivel no sistema: {e}"
        return True, "ok"

    def read_qr(self, image) -> Optional[str]:
        """Tenta decodificar o QR do comprovante com zbar e, em seguida, com OpenCV."""
        if not CV_AVAILABLE:
            return None

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        candidates = [
            gray,
            cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC),
            cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        ]

        if ZBAR_AVAILABLE:
            for cand in candidates:
                try:
                    for code in pyzbar.decode(cand):
                        payload = code.data.decode("utf-8", errors="replace").strip()
                        if payload:
                            logger.info("QR do comprovante decodificado (zbar): %s", payload)
                            return payload
                except Exception as e:
                    logger.debug("Falha zbar: %s", e)

        try:
            detector = cv2.QRCodeDetector()
            for cand in candidates:
                payload, _, _ = detector.detectAndDecode(cand)
                if payload:
                    logger.info("QR do comprovante decodificado (OpenCV): %s", payload)
                    return payload.strip()
        except Exception as e:
            logger.debug("Falha OpenCV QR: %s", e)

        return None

    # ------------------------------------------------------------------
    # Etapas internas
    def decode(self, image_bytes: bytes):
        try:
            buf = np.frombuffer(image_bytes, dtype=np.uint8)
            return cv2.imdecode(buf, cv2.IMREAD_COLOR)
        except Exception as e:
            logger.warning("Erro ao decodificar imagem: %s", e)
            return None
    def auto_orient(self, image):
        """
        Fotos de comprovante chegam de cabeca para baixo, giradas ou espelhadas
        (preview de webcam). Testamos as 8 orientacoes em baixa resolucao e
        escolhemos a que produz texto reconhecivel.
        """
        variants = {
            "0": image,
            "180": cv2.rotate(image, cv2.ROTATE_180),
            "90": cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
            "270": cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE),
        }
        variants.update({f"{k}-espelhado": cv2.flip(v, 1) for k, v in list(variants.items())})

        best_key, best_score, best_img = "0", -1, image
        for key, candidate in variants.items():
            score = self._orientation_score(candidate)
            if score > best_score:
                best_key, best_score, best_img = key, score, candidate

        logger.info("Orientacao escolhida para o comprovante: %s (score=%s)", best_key, best_score)
        return best_img, best_key

    def _orientation_score(self, image) -> int:
        probe = self._prepare(image, max_width=900)
        try:
            text = pytesseract.image_to_string(probe, config=TESS_TEXT).lower()
        except Exception:
            return 0
        return sum(text.count(anchor) for anchor in ORIENTATION_ANCHORS)
    def _grayscale(self, image, max_width: int = 2000):
        """Normaliza escala e contraste antes de qualquer binarizacao."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        width = gray.shape[1]
        if width != max_width and width > 0:
            factor = max_width / float(width)
            interp = cv2.INTER_CUBIC if factor > 1 else cv2.INTER_AREA
            gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=interp)

        gray = cv2.bilateralFilter(gray, 7, 60, 60)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _prepare_variants(self, image, max_width: int = 2000) -> List[Any]:
        """
        Gera binarizacoes alternativas do mesmo comprovante.

        Motivo: a linha das dezenas e a maior e mais grossa do bilhete. Um
        adaptiveThreshold com bloco pequeno cabe inteiro dentro do traco dessa fonte,
        calcula media igual ao proprio traco e APAGA o numero - some justamente a
        unica linha que interessa. Otsu global preserva texto grosso; o adaptativo
        salva papel amassado com sombra. Testamos os dois e ficamos com o que produzir
        uma aposta valida.
        """
        gray = self._grayscale(image, max_width)

        otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        # Bloco proporcional a largura, nunca menor que a altura de uma linha grossa
        block = max(41, int(gray.shape[1] * 0.04) | 1)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 12
        )

        return [otsu, adaptive, gray]

    def _prepare(self, image, max_width: int = 2000):
        """Variante principal (Otsu), usada na leitura de texto e na orientacao."""
        return self._prepare_variants(image, max_width)[0]

    def ocr(self, image, config: str) -> str:
        try:
            prepared = self._prepare(image)
            return pytesseract.image_to_string(prepared, config=config)
        except Exception as e:
            logger.warning("Erro no OCR: %s", e)
            return ""
    def extract_numbers(self, image, game_id: Optional[str]) -> List[str]:
        """
        Extrai as dezenas apostadas lendo o comprovante LINHA A LINHA.

        A primeira versao tentava separar aposta de ruido por geometria (altura do
        digito, folga entre numeros). Rodando com Tesseract real sobre comprovantes
        que reproduzem os bilhetes fisicos, isso leu 27 dezenas numa Quina de 5: o
        codigo da aposta impresso no rodape virou uma fileira de numeros plausiveis.

        O comprovante entrega uma pista muito mais forte que geometria: a linha da
        aposta e a UNICA composta apenas por numeros de dois digitos. Todo o resto
        carrega letra ou simbolo junto - "CONC 2971", "TOTAL R$ 3,00", "01SET2026
        HORA DF 14:46:23", "E. LOTERICO 04.007703-9" - e o codigo do rodape e uma
        sequencia continua longa, que nunca se parte em pares de dois digitos.
        """
        rules = BET_SIZE_RULES.get(game_id)
        best_effort: List[str] = []

        for prepared in self._prepare_variants(image):
            try:
                texto = pytesseract.image_to_string(prepared, config=TESS_TEXT)
            except Exception as e:
                logger.warning("Erro no OCR de dezenas: %s", e)
                continue

            numeros = self._numbers_from_lines(texto, game_id)
            if rules and rules[0] <= len(numeros) <= rules[1]:
                return numeros

            if len(numeros) > len(best_effort):
                best_effort = numeros

        return best_effort

    def _numbers_from_lines(self, texto: str, game_id: Optional[str]) -> List[str]:
        """Junta as linhas que contem exclusivamente dezenas da modalidade."""
        baixo, alto = NUMBER_RANGE_RULES.get(game_id or "megasena", (0, 99))

        linhas_de_aposta = []
        for bruta in texto.splitlines():
            tokens = self._bet_line_tokens(bruta, baixo, alto)
            linhas_de_aposta.append(tokens)

        # Preferimos o bloco contiguo da grade impressa; se ele nao fechar as regras
        # da modalidade, quem decide e o conjunto completo de linhas de aposta.
        blocos = []
        atual = []
        for tokens in linhas_de_aposta:
            if tokens:
                atual.append(tokens)
            elif atual:
                blocos.append(atual)
                atual = []
        if atual:
            blocos.append(atual)

        if not blocos:
            return []

        rules = BET_SIZE_RULES.get(game_id)
        todas = [tokens for bloco in blocos for tokens in bloco]
        candidatos = [sum(todas, [])]                       # todas as linhas de aposta
        candidatos += [sum(b, []) for b in sorted(blocos, key=len, reverse=True)]

        for candidato in candidatos:
            dezenas = self._dedupe(candidato)
            if rules and rules[0] <= len(dezenas) <= rules[1]:
                return dezenas

        return self._dedupe(sum(max(blocos, key=len), []))

    def _bet_line_tokens(self, linha: str, baixo: int, alto: int) -> List[str]:
        """
        Devolve as dezenas da linha, ou vazio se ela nao for uma linha de aposta.

        Aceita o marcador da aposta ("A", "B") e os colchetes da Lotomania ("[01]").
        Recusa qualquer linha com letra, simbolo ou numero que nao seja de 2 digitos:
        e isso que descarta data, hora, valor, CNPJ do loterico e codigo do rodape.
        """
        limpa = linha.replace("[", " ").replace("]", " ").replace("|", " ").strip()
        if not limpa:
            return []

        tokens = limpa.split()

        # Marcador da aposta isolado no inicio da linha
        if tokens and len(tokens[0]) == 1 and tokens[0].isalpha():
            tokens = tokens[1:]

        if len(tokens) < 2:
            return []

        for token in tokens:
            if not re.fullmatch(r"\d{2}", token):
                return []
            if not (baixo <= int(token) <= alto):
                return []

        return tokens

    def _dedupe(self, numeros: List[str]) -> List[str]:
        vistos = set()
        saida = []
        for numero in numeros:
            if numero not in vistos:
                vistos.add(numero)
                saida.append(numero)
        return saida


ticket_vision = TicketVision()
