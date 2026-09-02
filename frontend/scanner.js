// TimesFM Studio - Modulo de Conferencia de Bilhetes das Loterias Caixa
//
// Regra do modulo: o navegador NAO calcula acerto e NAO inventa dezena.
// Ele captura a imagem, envia para o pipeline optico do backend, mostra o que
// foi lido para o usuario confirmar e exibe a conferencia oficial da Caixa.

class TicketScannerMixin {
    // ==========================================
    // MÓDULO SCANNER DE BILHETES (CÂMERA & FOTO HD)
    // ==========================================
    initScannerMode(mode) {
        const cameraBox = document.getElementById('scannerCameraBox');
        const manualBox = document.getElementById('manualCheckBox');
        const resultBox = document.getElementById('ticketCheckResult');
        if (resultBox) resultBox.style.display = 'none';
        this.hideConfirmBox();

        if (mode === 'camera') {
            if (cameraBox) cameraBox.style.display = 'flex';
            if (manualBox) manualBox.style.display = 'none';
            this.startCameraScanner();
        } else {
            if (cameraBox) cameraBox.style.display = 'none';
            if (manualBox) manualBox.style.display = 'flex';
            this.stopCameraScanner();
            this.renderQuickPickerGrid();
        }
    }

    async startCameraScanner() {
        if (typeof Html5Qrcode === 'undefined') {
            console.error('Html5Qrcode scanner não disponível.');
            return;
        }

        const cameraViewport = document.getElementById('cameraReader');
        if (cameraViewport) {
            cameraViewport.innerHTML = ''; // Limpar previews anteriores
        }

        try {
            if (this.html5QrCode) {
                try { await this.html5QrCode.stop(); } catch (e) {}
            }

            this.html5QrCode = new Html5Qrcode("cameraReader", {
                experimentalFeatures: {
                    useBarCodeDetectorIfSupported: true
                }
            });

            const config = {
                fps: 15,
                qrbox: (viewfinderWidth, viewfinderHeight) => {
                    return {
                        width: Math.floor(viewfinderWidth * 0.9),
                        height: Math.floor(viewfinderHeight * 0.85)
                    };
                },
                aspectRatio: 0.76, // Formato Retrato / Vertical (como celular)
                videoConstraints: {
                    facingMode: this.currentCameraFacing,
                    width: { ideal: 1080 },
                    height: { ideal: 1920 }
                }
            };

            await this.html5QrCode.start(
                { facingMode: this.currentCameraFacing },
                config,
                (decodedText) => {
                    this.onQrCodeScanned(decodedText);
                },
                () => {}
            );
            this.isScannerRunning = true;
            this.setScannerStatus('Enquadre o bilhete no visor e toque em 📸 Capturar e Ler o Bilhete', 'muted');
        } catch (err) {
            console.warn('Erro ao abrir câmera:', err);
            const secure = window.isSecureContext;
            this.setScannerStatus(
                secure
                    ? '💡 Câmera indisponível. Use "🖼️ Enviar Foto do Arquivo" para mandar uma foto do bilhete.'
                    : '🔒 A câmera exige HTTPS. Acesse pelo domínio seguro ou use "🖼️ Enviar Foto do Arquivo".',
                'warn'
            );
        }
    }

    async stopCameraScanner() {
        if (this.html5QrCode && this.isScannerRunning) {
            try {
                await this.html5QrCode.stop();
                this.isScannerRunning = false;
            } catch (e) {
                console.warn('Erro ao pausar scanner:', e);
            }
        }
    }

    /**
     * Congela o quadro atual da câmera ao vivo e manda para o OCR.
     * É o caminho do desktop: no computador o input de arquivo abre um seletor,
     * não a câmera, então sem isto não existe como capturar o bilhete pelo navegador.
     */
    async captureFromCamera() {
        const video = document.querySelector('#cameraReader video');
        if (!video || !video.videoWidth) {
            this.setScannerStatus('⚠️ Câmera ainda não está pronta. Aguarde a imagem aparecer e tente de novo.', 'warn');
            return;
        }

        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');

        // Desfaz o espelhamento se o usuário ativou o modo espelho no visor
        if (this.isMirrored) {
            ctx.translate(canvas.width, 0);
            ctx.scale(-1, 1);
        }
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95));
        if (!blob) {
            this.setScannerStatus('⚠️ Não consegui capturar o quadro da câmera.', 'warn');
            return;
        }

        console.info(`Quadro capturado da câmera: ${canvas.width}x${canvas.height}px`);
        await this.processUploadedPhoto(blob);
    }

    /**
     * Envia a foto do comprovante para o pipeline óptico do backend (OpenCV + Tesseract).
     * O navegador não decide nada aqui: ele mostra o que foi lido e pede confirmação.
     */
    async processUploadedPhoto(file) {
        const cameraViewport = document.getElementById('cameraReader');

        await this.stopCameraScanner();
        this.hideConfirmBox();

        if (cameraViewport) {
            cameraViewport.innerHTML = '';
            const previewImg = document.createElement('img');
            previewImg.src = URL.createObjectURL(file);
            previewImg.style.width = '100%';
            previewImg.style.height = '100%';
            previewImg.style.objectFit = 'contain';
            previewImg.style.borderRadius = 'var(--radius-md)';
            previewImg.onload = () => URL.revokeObjectURL(previewImg.src);
            cameraViewport.appendChild(previewImg);
        }

        this.setScannerStatus('🔄 Lendo o comprovante (orientação, QR e dezenas impressas)...', 'info');

        try {
            const form = new FormData();
            form.append('file', file, file.name || 'bilhete.jpg');
            form.append('game_id', this.currentGame);

            const res = await fetch('/api/lottery/scan-ticket', { method: 'POST', body: form });
            const json = await res.json();

            if (!res.ok) {
                this.setScannerStatus(`⚠️ ${json.detail || 'Falha ao processar a imagem.'}`, 'warn');
                this.openManualWith([], null, this.currentGame);
                return;
            }

            const data = json.data || {};
            if (data.qr_payload) {
                console.info('Payload bruto do QR do comprovante:', data.qr_payload);
            }

            if (!data.success) {
                this.setScannerStatus(`⚠️ ${data.message}`, 'warn');
                this.openManualWith(data.numbers || [], data.contest, data.game_id);
                return;
            }

            this.showTicketConfirmation(data);

        } catch (err) {
            console.error('Erro no processamento da foto:', err);
            this.setScannerStatus('⚠️ Não consegui falar com o servidor de leitura. Use o modo manual.', 'warn');
            this.openManualWith([], null, this.currentGame);
        } finally {
            this.resetFileInput();
        }
    }

    setScannerStatus(message, tone = 'info') {
        const instruction = document.getElementById('scannerInstruction');
        if (!instruction) return;
        const colors = { info: '#38bdf8', warn: '#fbbf24', ok: '#34d399', muted: 'var(--text-muted)' };
        instruction.textContent = message;
        instruction.style.color = colors[tone] || colors.muted;
    }

    hideConfirmBox() {
        const box = document.getElementById('ticketConfirmBox');
        if (box) box.style.display = 'none';
        this.pendingTicket = null;
    }

    /** Mostra as dezenas lidas para o usuário validar ANTES de qualquer conferência. */
    showTicketConfirmation(data) {
        const gameId = data.game_id || this.currentGame;
        if (gameId !== this.currentGame) this.selectLottery(gameId);

        this.pendingTicket = {
            game_id: gameId,
            numbers: data.numbers || [],
            contest: data.contest || null
        };

        const box = document.getElementById('ticketConfirmBox');
        const subtitle = document.getElementById('confirmSubtitle');
        const ballsRow = document.getElementById('confirmBalls');

        if (subtitle) {
            const contestTxt = data.contest ? `Concurso #${data.contest}` : 'Concurso: último oficial disponível';
            subtitle.textContent = `${this.capitalize(gameId)} • ${contestTxt} • ${this.pendingTicket.numbers.length} dezenas lidas`;
        }

        if (ballsRow) {
            ballsRow.innerHTML = '';
            const sizeClass = this.pendingTicket.numbers.length > 15 ? 'mini-size' : 'compact-size';
            this.pendingTicket.numbers.forEach(num => {
                const ball = document.createElement('div');
                ball.className = `ball ball-${gameId} ${sizeClass}`;
                ball.textContent = num;
                ballsRow.appendChild(ball);
            });
        }

        if (box) box.style.display = 'flex';
        this.setScannerStatus('👀 Confira se as dezenas batem com o seu bilhete antes de validar.', 'ok');
    }

    /** Abre o volante manual já preenchido com o que o OCR conseguiu ler. */
    openManualWith(numbers = [], contest = null, gameId = null) {
        if (gameId && gameId !== this.currentGame) this.selectLottery(gameId);

        const modeManualBtn = document.getElementById('scannerModeManual');
        const modeCameraBtn = document.getElementById('scannerModeCamera');
        if (modeManualBtn && modeCameraBtn) {
            modeManualBtn.classList.add('active');
            modeCameraBtn.classList.remove('active');
        }
        this.initScannerMode('manual');

        const contestInput = document.getElementById('manualContestInput');
        if (contestInput) contestInput.value = contest || '';

        numbers.forEach(num => {
            this.selectedManualNumbers.add(num);
            const ball = Array.from(document.querySelectorAll('.pick-ball'))
                .find(b => b.textContent === num);
            if (ball) ball.classList.add('selected');
        });
        this.updateManualInputText();
    }

    resetFileInput() {
        const ticketPhotoInput = document.getElementById('ticketPhotoInput');
        if (ticketPhotoInput) {
            ticketPhotoInput.value = '';
        }
    }

    resetScanner() {
        // Ocultar card de resultado e painel de confirmação
        const resultBox = document.getElementById('ticketCheckResult');
        if (resultBox) resultBox.style.display = 'none';
        this.hideConfirmBox();

        // Resetar instruções
        this.lastQrPayload = null;
        this.setScannerStatus('Enquadre o bilhete no visor e toque em 📸 Capturar e Ler o Bilhete', 'muted');

        // Limpar campos manuais
        const input = document.getElementById('manualNumbersInput');
        if (input) input.value = '';
        this.selectedManualNumbers.clear();
        document.querySelectorAll('.pick-ball').forEach(b => b.classList.remove('selected'));

        // Reiniciar Câmera
        this.startCameraScanner();

        // Rolar modal de volta para o topo
        const modalContainer = document.querySelector('.modal-container');
        if (modalContainer) {
            modalContainer.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }

    /**
     * O QR do comprovante da Caixa é um payload opaco: ele NÃO contém as dezenas
     * apostadas. Serve para identificar o comprovante e, quando presente, o concurso.
     * Por isso o fluxo correto é: leu o QR -> pede a foto para o OCR ler as dezenas.
     */
    async onQrCodeScanned(decodedText) {
        // Não para a câmera: o QR é só um bônus, quem lê as dezenas é a captura da foto.
        if (this.lastQrPayload === decodedText) return;
        this.lastQrPayload = decodedText;
        console.info('Payload bruto do QR do comprovante:', decodedText);

        const contest = this.extractContestFromQr(decodedText);
        const gameId = this.detectGameFromText(decodedText);
        if (gameId && gameId !== this.currentGame) this.selectLottery(gameId);

        const contestInput = document.getElementById('manualContestInput');
        if (contestInput && contest) contestInput.value = contest;

        this.setScannerStatus(
            contest
                ? `✅ QR lido (Concurso #${contest}). O QR não traz as dezenas — toque em 📸 Capturar para lê-las.`
                : '✅ QR lido, mas ele não traz as dezenas apostadas — toque em 📸 Capturar para lê-las.',
            'warn'
        );
    }

    extractContestFromQr(text) {
        const match = /concurso[=:/-]?(\d{3,5})/i.exec(text || '');
        return match ? match[1] : null;
    }

    detectGameFromText(text) {
        const t = (text || '').toLowerCase();
        if (t.includes('lotomania')) return 'lotomania';
        if (t.includes('lotofacil') || t.includes('lotofácil')) return 'lotofacil';
        if (t.includes('quina')) return 'quina';
        if (t.includes('mega')) return 'megasena';
        return null;
    }

    renderQuickPickerGrid() {
        const grid = document.getElementById('quickPickerGrid');
        if (!grid) return;

        grid.innerHTML = '';
        this.selectedManualNumbers.clear();

        const totalMap = { megasena: 60, quina: 80, lotofacil: 25, lotomania: 100 };
        const startMap = { megasena: 1, quina: 1, lotofacil: 1, lotomania: 0 };
        
        const total = totalMap[this.currentGame] || 60;
        const start = startMap[this.currentGame] || 1;

        for (let i = start; i < start + total; i++) {
            const numStr = String(i).padStart(2, '0');
            const ball = document.createElement('div');
            ball.className = 'pick-ball';
            ball.textContent = numStr;
            ball.addEventListener('click', () => {
                if (this.selectedManualNumbers.has(numStr)) {
                    this.selectedManualNumbers.delete(numStr);
                    ball.classList.remove('selected');
                } else {
                    this.selectedManualNumbers.add(numStr);
                    ball.classList.add('selected');
                }
                this.updateManualInputText();
            });
            grid.appendChild(ball);
        }
    }

    updateManualInputText() {
        const input = document.getElementById('manualNumbersInput');
        if (input) {
            const sorted = Array.from(this.selectedManualNumbers).sort((a, b) => parseInt(a) - parseInt(b));
            input.value = sorted.join(', ');
        }
    }

    checkManualGame() {
        const input = document.getElementById('manualNumbersInput');
        const contestInput = document.getElementById('manualContestInput');

        if (!input || !input.value.trim()) {
            this.setScannerStatus('⚠️ Selecione ou digite as dezenas do seu bilhete.', 'warn');
            return;
        }

        const numbers = input.value
            .split(/[\s,;.-]+/)
            .map(n => n.trim())
            .filter(n => /^\d{1,2}$/.test(n))
            .map(n => n.padStart(2, '0'));

        const contest = contestInput && contestInput.value.trim()
            ? parseInt(contestInput.value.trim(), 10)
            : null;

        this.checkTicket(this.currentGame, [...new Set(numbers)], contest);
    }

    /**
     * Conferência oficial: quem calcula acertos, faixa e prêmio é o backend,
     * contra o resultado real da Caixa. O front só exibe.
     */
    async checkTicket(gameId, numbers, contest = null) {
        this.setScannerStatus('🔄 Conferindo na base oficial da Caixa...', 'info');

        try {
            const res = await fetch('/api/lottery/check-ticket', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId, numbers, contest })
            });
            const json = await res.json();

            if (!res.ok || !json.success) {
                this.setScannerStatus(`⚠️ ${json.detail || 'Não foi possível conferir este bilhete.'}`, 'warn');
                return;
            }

            this.hideConfirmBox();
            this.renderTicketResult(json.data);

        } catch (e) {
            console.error('Erro ao conferir bilhete:', e);
            this.setScannerStatus('⚠️ Servidor indisponível para a conferência. Tente novamente.', 'warn');
        }
    }

    renderTicketResult(result) {
        const officialSet = new Set(result.official_numbers || []);
        const hitCount = result.hit_count;
        const isWinner = result.is_winner;

        const resultBox = document.getElementById('ticketCheckResult');
        const banner = document.getElementById('resultBanner');
        const icon = document.getElementById('resultIcon');
        const title = document.getElementById('resultTitle');
        const subtitle = document.getElementById('resultSubtitle');
        const userBallsContainer = document.getElementById('ticketUserBalls');
        const statHits = document.getElementById('statHits');
        const statFaixa = document.getElementById('statFaixa');
        const statPrize = document.getElementById('statPrize');

        if (resultBox) resultBox.style.display = 'flex';

        const contestLabel = `Concurso #${result.contest} • ${result.contest_date || ''}`.trim();

        if (isWinner) {
            if (banner) banner.className = 'result-banner';
            if (icon) icon.textContent = '🎉';
            if (title) title.textContent = `PARABÉNS! BILHETE PREMIADO — ${hitCount} ACERTO(S)!`;
            if (subtitle) {
                subtitle.textContent = result.prize > 0
                    ? `${contestLabel} • Faixa premiada: ${result.band_description} (${result.band_winners} ganhador(es))`
                    : `${contestLabel} • Faixa ${result.band_description}: sem ganhadores neste concurso, valor acumulado pela Caixa.`;
            }
        } else {
            if (banner) banner.className = 'result-banner loser';
            if (icon) icon.textContent = '🎯';
            if (title) title.textContent = `Você acertou ${hitCount} dezena(s).`;
            if (subtitle) subtitle.textContent = `${contestLabel} • Essa quantidade de acertos não paga prêmio nesta modalidade.`;
        }

        if (statHits) statHits.textContent = hitCount;
        if (statFaixa) statFaixa.textContent = isWinner ? result.band_description : 'Sem premiação';
        if (statPrize) statPrize.textContent = this.formatCurrency(result.prize);

        // Bolas do Usuário com Destaque Dourado para Acertos
        if (userBallsContainer) {
            const userNumbers = result.user_numbers || [];
            userBallsContainer.innerHTML = '';
            const sizeClass = userNumbers.length > 15 ? 'mini-size' : (userNumbers.length > 6 ? 'compact-size' : '');

            userNumbers.forEach(num => {
                const ball = document.createElement('div');
                const isHit = officialSet.has(num);
                ball.className = `ball ball-${result.game_id} ${sizeClass} ${isHit ? 'hit-match' : ''}`;
                ball.textContent = num;
                if (isHit) ball.title = 'Dezena sorteada acertada!';
                userBallsContainer.appendChild(ball);
            });
        }

        this.setScannerStatus(`✅ Conferido no resultado oficial da Caixa (${contestLabel}).`, 'ok');

        // Rolar suavemente para exibir o resultado da conferência
        setTimeout(() => {
            const modalContainer = document.querySelector('.modal-container');
            if (modalContainer) {
                modalContainer.scrollTo({ top: modalContainer.scrollHeight, behavior: 'smooth' });
            }
        }, 120);
    }
}
