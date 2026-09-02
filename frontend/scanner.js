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
            this.resetPhotoCaptureState();
            this.startCameraScanner();
        } else {
            if (cameraBox) cameraBox.style.display = 'none';
            if (manualBox) manualBox.style.display = 'flex';
            this.stopCameraScanner();
            this.renderQuickPickerGrid();
        }
    }

    resetPhotoCaptureState() {
        this.currentPhotoBlob = null;
        const activeActions = document.getElementById('cameraActiveActions');
        const previewActions = document.getElementById('photoPreviewActions');
        if (activeActions) activeActions.style.display = 'flex';
        if (previewActions) previewActions.style.display = 'none';
        this.setScannerStatus('Aponte a câmera para o comprovante ou selecione uma foto nítida do seu bilhete.', 'muted');
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

            const isMobile = window.innerWidth <= 768;
            const ratio = isMobile ? (window.innerHeight / window.innerWidth) : (16 / 9);

            const config = {
                fps: 24,
                aspectRatio: ratio,
                videoConstraints: {
                    facingMode: this.currentCameraFacing || "environment",
                    width: { ideal: 1920, min: 1080 },
                    height: { ideal: 1080, min: 720 }
                }
            };

            await this.html5QrCode.start(
                { facingMode: this.currentCameraFacing || "environment" },
                config,
                (decodedText) => {
                    this.onQrCodeScanned(decodedText);
                },
                () => {}
            );
            this.isScannerRunning = true;

            // Força o vídeo a cobrir 100% da viewport em tela cheia no mobile
            const videoEl = cameraViewport.querySelector('video');
            if (videoEl) {
                videoEl.style.width = '100%';
                videoEl.style.height = '100%';
                videoEl.style.objectFit = 'cover';
                videoEl.style.position = 'absolute';
                videoEl.style.inset = '0';
            }

            this.setScannerStatus('Enquadre o comprovante e toque no botão circular para fotografar.', 'muted');
        } catch (err) {
            console.warn('Erro ao abrir câmera:', err);
            const secure = window.isSecureContext;
            this.setScannerStatus(
                secure
                    ? '💡 Toque em "Galeria" para escolher uma foto do bilhete.'
                    : '🔒 Câmera requer HTTPS. Toque em "Galeria" para enviar foto.',
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
     * Congela o quadro da câmera e prepara para verificação.
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

        await this.handlePhotoReady(blob);
    }

    /**
     * Recebe um Blob de foto (seja da câmera ao vivo ou do input de arquivo da galeria),
     * congela a visualização com preview nítido e exibe o botão destacado "Verificar Resultado".
     */
    async handlePhotoReady(fileOrBlob) {
        this.currentPhotoBlob = fileOrBlob;
        await this.stopCameraScanner();
        this.hideConfirmBox();

        const cameraViewport = document.getElementById('cameraReader');
        if (cameraViewport) {
            cameraViewport.innerHTML = '';
            const previewImg = document.createElement('img');
            previewImg.src = URL.createObjectURL(fileOrBlob);
            previewImg.style.width = '100%';
            previewImg.style.height = '100%';
            previewImg.style.objectFit = 'contain';
            previewImg.style.borderRadius = 'var(--radius-md)';
            previewImg.onload = () => URL.revokeObjectURL(previewImg.src);
            cameraViewport.appendChild(previewImg);
        }

        // Alterna os botões: esconde captura e mostra "Verificar Resultado"
        const activeActions = document.getElementById('cameraActiveActions');
        const previewActions = document.getElementById('photoPreviewActions');
        if (activeActions) activeActions.style.display = 'none';
        if (previewActions) previewActions.style.display = 'flex';

        this.setScannerStatus('📸 Foto pronta! Toque em "🔍 Verificar Resultado" para ler o bilhete e calcular seus acertos.', 'ok');
    }

    /**
     * Dispara a leitura do bilhete via OCR e realiza a conferência oficial na Caixa.
     */
    async analyzeAndVerifyPhoto() {
        if (!this.currentPhotoBlob) {
            this.setScannerStatus('⚠️ Nenhuma foto capturada. Tire uma foto ou escolha da galeria.', 'warn');
            return;
        }

        const verifyBtn = document.getElementById('verifyPhotoBtn');
        const originalBtnHtml = verifyBtn ? verifyBtn.innerHTML : '';
        if (verifyBtn) {
            verifyBtn.disabled = true;
            verifyBtn.innerHTML = `
                <div class="spinner" style="width: 20px; height: 20px; border-width: 2px;"></div>
                <span>Lendo bilhete e conferindo...</span>
            `;
        }

        this.setScannerStatus('🔄 Lendo dezenas, modalidade e concurso do comprovante...', 'info');

        try {
            const form = new FormData();
            form.append('file', this.currentPhotoBlob, 'bilhete.jpg');
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

            if (!data.success || !data.numbers || data.numbers.length === 0) {
                this.setScannerStatus(`⚠️ ${data.message || 'Não foi possível ler as dezenas com nitidez.'}`, 'warn');
                this.openManualWith(data.numbers || [], data.contest, data.game_id);
                return;
            }

            // Detectou o jogo e as dezenas! Executa imediatamente a conferência oficial
            const gameId = data.game_id || this.currentGame;
            if (gameId !== this.currentGame) this.selectLottery(gameId);

            this.pendingTicket = {
                game_id: gameId,
                numbers: data.numbers || [],
                contest: data.contest || null,
                games: data.games || [data.numbers]
            };

            await this.checkTicket(gameId, data.numbers, data.contest, data.games);

        } catch (err) {
            console.error('Erro no processamento da foto:', err);
            this.setScannerStatus('⚠️ Erro ao comunicar com o servidor. Verifique sua conexão.', 'warn');
        } finally {
            if (verifyBtn) {
                verifyBtn.disabled = false;
                verifyBtn.innerHTML = originalBtnHtml;
            }
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

    /** Mostra as dezenas lidas para o usuário validar caso queira alterar manualmente. */
    showTicketConfirmation(data) {
        const gameId = data.game_id || this.currentGame;
        if (gameId !== this.currentGame) this.selectLottery(gameId);

        this.pendingTicket = {
            game_id: gameId,
            numbers: data.numbers || [],
            contest: data.contest || null,
            games: data.games || [data.numbers]
        };

        const box = document.getElementById('ticketConfirmBox');
        const subtitle = document.getElementById('confirmSubtitle');
        const ballsRow = document.getElementById('confirmBalls');

        if (subtitle) {
            const contestTxt = data.contest ? `Concurso #${data.contest}` : 'Concurso: último oficial';
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
        this.setScannerStatus('👀 Confira as dezenas lidas antes de prosseguir.', 'ok');
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

        // Resetar instruções e capturas
        this.lastQrPayload = null;
        this.currentPhotoBlob = null;

        // Limpar campos manuais
        const input = document.getElementById('manualNumbersInput');
        if (input) input.value = '';
        this.selectedManualNumbers.clear();
        document.querySelectorAll('.pick-ball').forEach(b => b.classList.remove('selected'));

        // Reiniciar Câmera
        this.resetPhotoCaptureState();
        this.startCameraScanner();

        // Rolar modal de volta para o topo
        const modalContainer = document.querySelector('.modal-container');
        if (modalContainer) {
            modalContainer.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }

    async onQrCodeScanned(decodedText) {
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
                ? `✅ QR lido (Concurso #${contest}). Toque em "Tirar Foto da Câmera" para ler as dezenas.`
                : '✅ QR identificado. Toque em "Tirar Foto da Câmera" para ler as dezenas apostadas.',
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
     * Conferência oficial contra o resultado real da Caixa.
     */
    async checkTicket(gameId, numbers, contest = null, games = null) {
        this.setScannerStatus('🔄 Consultando resultado oficial na Caixa...', 'info');

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
            this.renderTicketResult(json.data, games);

        } catch (e) {
            console.error('Erro ao conferir bilhete:', e);
            this.setScannerStatus('⚠️ Servidor indisponível para conferência. Tente novamente.', 'warn');
        }
    }

    renderTicketResult(result, detectedGames = null) {
        const officialNumbers = result.official_numbers || [];
        const officialSet = new Set(officialNumbers);
        const hitCount = result.hit_count;
        const isWinner = result.is_winner;

        const resultBox = document.getElementById('ticketCheckResult');
        const banner = document.getElementById('resultBanner');
        const icon = document.getElementById('resultIcon');
        const title = document.getElementById('resultTitle');
        const subtitle = document.getElementById('resultSubtitle');
        const statHits = document.getElementById('statHits');
        const statFaixa = document.getElementById('statFaixa');
        const statPrize = document.getElementById('statPrize');
        const contestBadge = document.getElementById('resultContestBadge');
        const officialBallsRow = document.getElementById('officialResultBalls');
        const gamesContainer = document.getElementById('ticketGamesContainer');

        if (resultBox) resultBox.style.display = 'flex';

        const contestLabel = `Concurso #${result.contest} • ${result.contest_date || ''}`.trim();
        if (contestBadge) {
            contestBadge.textContent = `${this.capitalize(result.game_id)} #${result.contest}`;
        }

        // Renderizar Bolas Sorteadas Oficiais da Caixa
        if (officialBallsRow) {
            officialBallsRow.innerHTML = '';
            const sizeClass = officialNumbers.length > 15 ? 'mini-size' : 'compact-size';
            officialNumbers.forEach(num => {
                const ball = document.createElement('div');
                ball.className = `ball ball-${result.game_id} ${sizeClass}`;
                ball.textContent = num;
                officialBallsRow.appendChild(ball);
            });
        }

        // Renderizar Jogos do Usuário
        if (gamesContainer) {
            gamesContainer.innerHTML = '';
            const gamesList = (result.games_results && result.games_results.length > 0)
                ? result.games_results
                : (detectedGames && detectedGames.length > 1)
                    ? detectedGames.map((g, idx) => {
                        const gHits = g.filter(n => officialSet.has(n));
                        return {
                            game_label: `Jogo ${chr(65 + idx) || (idx + 1)}`,
                            numbers: g,
                            hit_count: gHits.length,
                            hit_numbers: gHits
                        };
                    })
                    : [{
                        game_label: 'Seu Jogo',
                        numbers: result.user_numbers || [],
                        hit_count: hitCount,
                        hit_numbers: result.hit_numbers || []
                    }];

            gamesList.forEach(game => {
                const gameCard = document.createElement('div');
                gameCard.className = 'game-block-card';

                const header = document.createElement('div');
                header.className = 'game-block-header';

                const label = document.createElement('span');
                label.style.fontWeight = '700';
                label.textContent = game.game_label || 'Seu Jogo';

                const badge = document.createElement('span');
                const hits = game.hit_count !== undefined ? game.hit_count : (game.hit_numbers ? game.hit_numbers.length : 0);
                badge.className = `game-hits-badge ${hits >= 3 ? 'winner' : ''}`;
                badge.textContent = `${hits} acerto(s)`;

                header.appendChild(label);
                header.appendChild(badge);
                gameCard.appendChild(header);

                const ballsRow = document.createElement('div');
                ballsRow.className = 'lottery-balls-row compact';
                const sizeClass = game.numbers.length > 15 ? 'mini-size' : (game.numbers.length > 6 ? 'compact-size' : '');

                game.numbers.forEach(num => {
                    const ball = document.createElement('div');
                    const isHit = officialSet.has(num);
                    ball.className = `ball ball-${result.game_id} ${sizeClass} ${isHit ? 'hit-match' : ''}`;
                    ball.textContent = num;
                    if (isHit) ball.title = 'Dezena acertada!';
                    ballsRow.appendChild(ball);
                });

                gameCard.appendChild(ballsRow);
                gamesContainer.appendChild(gameCard);
            });
        }

        if (isWinner) {
            if (banner) banner.className = 'result-banner';
            if (icon) icon.textContent = '🎉';
            if (title) title.textContent = `PARABÉNS! BILHETE PREMIADO — ${hitCount} ACERTO(S)!`;
            if (subtitle) {
                subtitle.textContent = result.prize > 0
                    ? `${contestLabel} • Faixa: ${result.band_description} (${result.band_winners} ganhador(es))`
                    : `${contestLabel} • Faixa ${result.band_description}: prêmio acumulado pela Caixa.`;
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

        this.setScannerStatus(`✅ Conferência concluída com sucesso (${contestLabel}).`, 'ok');

        setTimeout(() => {
            const modalContainer = document.querySelector('.modal-container');
            if (modalContainer) {
                modalContainer.scrollTo({ top: modalContainer.scrollHeight, behavior: 'smooth' });
            }
        }, 120);
    }
}
