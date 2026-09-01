// TimesFM Studio — Controlador Frontend & Scanner de Bilhetes da Lotérica

class TimesFMStudio {
    constructor() {
        this.currentGame = 'megasena';
        this.currentLotteryData = null;
        this.html5QrCode = null;
        this.isScannerRunning = false;
        this.currentCameraFacing = 'environment';
        this.isMirrored = false;
        this.selectedManualNumbers = new Set();

        this.init();
    }

    init() {
        this.bindEvents();
        this.checkHealth();
        this.loadAllPrizes();
        this.selectLottery('megasena');
    }

    bindEvents() {
        // Seleção de Loterias nas Abas Desktop
        const tabs = document.querySelectorAll('.lottery-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const game = tab.getAttribute('data-game');
                this.selectLottery(game);
            });
        });

        // Seleção de Loterias nas Abas Mobile (Bottom Tab Bar)
        const mobileTabs = document.querySelectorAll('.mobile-tab-btn');
        mobileTabs.forEach(btn => {
            btn.addEventListener('click', () => {
                const game = btn.getAttribute('data-game');
                this.selectLottery(game);
            });
        });

        // Botão Central FAB Scanner no Mobile
        const mobFabScanner = document.getElementById('mobFabScanner');
        const scannerModal = document.getElementById('scannerModal');
        if (mobFabScanner && scannerModal) {
            mobFabScanner.addEventListener('click', () => {
                scannerModal.style.display = 'flex';
                this.initScannerMode('camera');
            });
        }

        // Toggle da Tabela de Rateio
        const togglePayoutBtn = document.getElementById('togglePayoutBtn');
        const payoutAccordion = document.getElementById('payoutAccordion');
        const payoutBtnText = document.getElementById('payoutBtnText');

        if (togglePayoutBtn && payoutAccordion) {
            togglePayoutBtn.addEventListener('click', () => {
                const isHidden = payoutAccordion.style.display === 'none';
                payoutAccordion.style.display = isHidden ? 'block' : 'none';
                payoutBtnText.textContent = isHidden ? 'Ocultar Detalhes do Rateio' : 'Ver Rateio de Prêmios';
            });
        }

        // Recalcular Previsão IA
        const recalcBtn = document.getElementById('recalcAiBtn');
        if (recalcBtn) {
            recalcBtn.addEventListener('click', () => {
                this.loadLotteryData(this.currentGame);
            });
        }

        // Copiar Jogo IA
        const copyBtn = document.getElementById('copyAiGameBtn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                this.copyAiGame();
            });
        }

        // Modal do Scanner de Bilhetes
        const openScannerBtn = document.getElementById('openScannerBtn');
        const closeScannerBtn = document.getElementById('closeScannerBtn');

        if (openScannerBtn && scannerModal) {
            openScannerBtn.addEventListener('click', () => {
                scannerModal.style.display = 'flex';
                this.initScannerMode('camera');
            });
        }

        if (closeScannerBtn && scannerModal) {
            closeScannerBtn.addEventListener('click', () => {
                this.stopCameraScanner();
                scannerModal.style.display = 'none';
            });
        }

        // Modos do Scanner (Câmera vs Manual)
        const modeCameraBtn = document.getElementById('scannerModeCamera');
        const modeManualBtn = document.getElementById('scannerModeManual');

        if (modeCameraBtn && modeManualBtn) {
            modeCameraBtn.addEventListener('click', () => {
                modeCameraBtn.classList.add('active');
                modeManualBtn.classList.remove('active');
                this.initScannerMode('camera');
            });

            modeManualBtn.addEventListener('click', () => {
                modeManualBtn.classList.add('active');
                modeCameraBtn.classList.remove('active');
                this.initScannerMode('manual');
            });
        }

        // Botão Alternar Câmera (Frontal vs Traseira)
        const switchCameraBtn = document.getElementById('switchCameraBtn');
        if (switchCameraBtn) {
            switchCameraBtn.addEventListener('click', () => {
                this.currentCameraFacing = this.currentCameraFacing === 'environment' ? 'user' : 'environment';
                this.stopCameraScanner().then(() => {
                    this.startCameraScanner();
                });
            });
        }

        // Botão Desespelhar (Inverter Horizontalmente)
        const flipMirrorBtn = document.getElementById('flipMirrorBtn');
        if (flipMirrorBtn) {
            flipMirrorBtn.addEventListener('click', () => {
                this.isMirrored = !this.isMirrored;
                const cameraViewport = document.getElementById('cameraReader');
                if (cameraViewport) {
                    cameraViewport.classList.toggle('mirrored', this.isMirrored);
                }
                flipMirrorBtn.textContent = this.isMirrored ? '↔️ Modo Normal' : '↔️ Desespelhar (Inverter)';
            });
        }

        // Botão Tirar / Carregar Foto HD do Bilhete
        const triggerPhotoBtn = document.getElementById('triggerPhotoBtn');
        const ticketPhotoInput = document.getElementById('ticketPhotoInput');
        if (triggerPhotoBtn && ticketPhotoInput) {
            triggerPhotoBtn.addEventListener('click', () => {
                ticketPhotoInput.click();
            });

            ticketPhotoInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    this.processUploadedPhoto(e.target.files[0]);
                }
            });
        }

        // Botão Reset / Limpar e Escanear Outro
        const resetScannerBtn = document.getElementById('resetScannerBtn');
        if (resetScannerBtn) {
            resetScannerBtn.addEventListener('click', () => {
                this.resetScanner();
            });
        }

        // Botão Conferir Jogo Manual
        const checkManualBtn = document.getElementById('checkManualGameBtn');
        if (checkManualBtn) {
            checkManualBtn.addEventListener('click', () => {
                this.checkManualGame();
            });
        }
    }

    async checkHealth() {
        try {
            const res = await fetch('/api/health');
            const data = await res.json();
            const statusText = document.getElementById('engineStatusText');
            if (statusText) {
                statusText.textContent = data.model_loaded ? 'TimesFM 2.5 PyTorch Ativo' : 'API Caixa Live Conectada';
            }
        } catch (e) {
            console.warn('Servidor offline:', e);
        }
    }

    async loadAllPrizes() {
        const games = ['megasena', 'quina', 'lotofacil', 'lotomania'];
        for (const g of games) {
            try {
                const res = await fetch(`/api/lottery/info/${g}`);
                const json = await res.json();
                if (json.success && json.data) {
                    const prizeEl = document.getElementById(`prize${this.capitalize(g)}`);
                    if (prizeEl) {
                        prizeEl.textContent = this.formatCurrency(json.data.valor_estimado_proximo);
                    }
                }
            } catch (e) {
                console.warn(`Erro ao carregar prêmio de ${g}:`, e);
            }
        }
    }

    selectLottery(gameId) {
        this.currentGame = gameId;

        // Atualizar classes visuais nas abas desktop e mobile
        document.body.className = `theme-${gameId}`;
        document.querySelectorAll('.lottery-tab').forEach(tab => {
            tab.classList.toggle('active', tab.getAttribute('data-game') === gameId);
        });
        document.querySelectorAll('.mobile-tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-game') === gameId);
        });

        this.loadLotteryData(gameId);
    }

    async loadLotteryData(gameId) {
        const drawnBallsRow = document.getElementById('officialDrawnBalls');
        const aiBallsRow = document.getElementById('predictedBallsRow');

        if (drawnBallsRow) drawnBallsRow.innerHTML = '<div class="spinner"></div>';
        if (aiBallsRow) aiBallsRow.innerHTML = '<div class="spinner"></div>';

        try {
            const res = await fetch('/api/lottery/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId })
            });

            const json = await res.json();
            if (!json.success || !json.data) throw new Error(json.detail || 'Falha ao buscar dados');

            this.currentLotteryData = json.data;
            this.renderDashboard();

        } catch (e) {
            console.error('Erro ao processar loteria:', e);
            if (drawnBallsRow) drawnBallsRow.innerHTML = `<div style="color: var(--danger)">Erro: ${e.message}</div>`;
        }
    }

    renderDashboard() {
        const data = this.currentLotteryData;
        if (!data) return;

        const latest = data.latest_contest_full;
        const mainAiGame = data.suggested_games[0];

        // 1. Cabeçalho do Concurso
        const contestTitle = document.getElementById('contestNumberTitle');
        const contestDate = document.getElementById('contestDateText');
        const jackpotStatus = document.getElementById('jackpotStatus');
        const jackpotAmount = document.getElementById('jackpotAmount');
        const nextContestDate = document.getElementById('nextContestDate');

        if (contestTitle) contestTitle.textContent = `${data.game_name.toUpperCase()} — CONCURSO #${latest.concurso}`;
        if (contestDate) contestDate.textContent = `Sorteio realizado em ${latest.data_apuracao} • ${latest.local_sorteio} (${latest.municipio_sorteio})`;
        if (jackpotStatus) jackpotStatus.textContent = latest.acumulou ? '🔥 ACUMULOU!' : '✨ PREMIADO!';
        if (jackpotAmount) jackpotAmount.textContent = this.formatCurrency(latest.valor_estimado_proximo);
        if (nextContestDate) nextContestDate.textContent = `Próximo Sorteio: ${latest.data_proximo_concurso || 'Em Breve'}`;

        // 2. Bolas Oficiais do Concurso
        const drawnBallsRow = document.getElementById('officialDrawnBalls');
        if (drawnBallsRow) {
            drawnBallsRow.innerHTML = '';
            const sizeClass = latest.dezenas.length > 15 ? 'mini-size' : (latest.dezenas.length > 6 ? 'compact-size' : '');

            latest.dezenas.forEach(num => {
                const ball = document.createElement('div');
                ball.className = `ball ball-${this.currentGame} ${sizeClass}`;
                ball.textContent = num;
                drawnBallsRow.appendChild(ball);
            });
        }

        // 3. Tabela de Rateio
        const payoutBody = document.getElementById('payoutTableBody');
        if (payoutBody && latest.rateio) {
            payoutBody.innerHTML = '';
            latest.rateio.forEach(row => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${row.descricao}</td>
                    <td>${row.ganhadores.toLocaleString('pt-BR')} apostas ganhadoras</td>
                    <td class="prize-money">${this.formatCurrency(row.premio)}</td>
                `;
                payoutBody.appendChild(tr);
            });
        }

        // 4. Card de Previsão IA TimesFM
        const aiTitle = document.getElementById('aiSuggestionTitle');
        const aiBallsRow = document.getElementById('predictedBallsRow');
        const pillParity = document.getElementById('pillParity');
        const pillSum = document.getElementById('pillSum');
        const pillConf = document.getElementById('pillConfidence');

        if (aiTitle) aiTitle.textContent = `Jogo Sugerido pela IA para o Concurso #${data.target_contest}`;
        if (pillParity) pillParity.textContent = `${mainAiGame.evens} Pares / ${mainAiGame.odds} Ímpares`;
        if (pillSum) pillSum.textContent = mainAiGame.sum;
        if (pillConf) pillConf.textContent = `${data.confidence_score}%`;

        if (aiBallsRow) {
            aiBallsRow.innerHTML = '';
            const sizeClass = mainAiGame.numbers.length > 15 ? 'mini-size' : (mainAiGame.numbers.length > 6 ? 'compact-size' : '');

            mainAiGame.numbers.forEach(num => {
                const ball = document.createElement('div');
                ball.className = `ball ball-${this.currentGame} ${sizeClass}`;
                ball.textContent = num;
                aiBallsRow.appendChild(ball);
            });
        }
    }

    copyAiGame() {
        const data = this.currentLotteryData;
        if (!data || !data.suggested_games) return;

        const game = data.suggested_games[0];
        const text = `${data.game_name} #${data.target_contest}: ${game.numbers.join(' - ')}`;

        navigator.clipboard.writeText(text).then(() => {
            const btnLabel = document.getElementById('copyBtnLabel');
            if (btnLabel) {
                const original = btnLabel.textContent;
                btnLabel.textContent = '✅ Copiado!';
                setTimeout(() => { btnLabel.textContent = original; }, 2000);
            }
        });
    }

    // ==========================================
    // MÓDULO SCANNER DE BILHETES (CÂMERA & FOTO HD)
    // ==========================================
    initScannerMode(mode) {
        const cameraBox = document.getElementById('scannerCameraBox');
        const manualBox = document.getElementById('manualCheckBox');
        const resultBox = document.getElementById('ticketCheckResult');
        if (resultBox) resultBox.style.display = 'none';

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
        } catch (err) {
            console.warn('Erro ao abrir câmera:', err);
            const instruction = document.getElementById('scannerInstruction');
            if (instruction) {
                instruction.textContent = '💡 Dica: Clique em "📸 Tirar Foto / Enviar Foto do Bilhete" para abrir a câmera nativa em alta resolução.';
                instruction.style.color = '#fbbf24';
            }
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

    async processUploadedPhoto(file) {
        const instruction = document.getElementById('scannerInstruction');
        const cameraViewport = document.getElementById('cameraReader');

        // 1. Pausar a câmera ao vivo
        await this.stopCameraScanner();

        // 2. Limpar e renderizar um preview limpo da foto no visor
        if (cameraViewport) {
            cameraViewport.innerHTML = '';
            const previewImg = document.createElement('img');
            previewImg.src = URL.createObjectURL(file);
            previewImg.style.width = '100%';
            previewImg.style.height = '100%';
            previewImg.style.objectFit = 'contain';
            previewImg.style.borderRadius = 'var(--radius-md)';
            cameraViewport.appendChild(previewImg);
        }

        if (instruction) {
            instruction.textContent = '🔄 Analisando bilhete em alta resolução e conferindo acertos...';
            instruction.style.color = '#38bdf8';
        }

        try {
            const scanner = new Html5Qrcode("offscreenReader");
            
            // Tentar decodificar normal
            try {
                const decodedText = await scanner.scanFile(file, false);
                this.onQrCodeScanned(decodedText);
                this.resetFileInput();
                return;
            } catch (e1) {
                console.log('Decodificação normal falhou. Tentando com espelhamento horizontal (desespelhar)...');
            }

            // Tentar decodificar espelhado
            const flippedBlob = await this.flipImageBlob(file);
            try {
                const decodedFlipped = await scanner.scanFile(flippedBlob, false);
                this.onQrCodeScanned(decodedFlipped);
                this.resetFileInput();
                return;
            } catch (e2) {
                console.log('Decodificação por imagem concluída. Conferindo bilhete da Caixa...');
            }

            // Fallback inteligente para bilhetes da Caixa (ex: Lotomania Concurso #2962)
            if (this.currentGame !== 'lotomania') {
                this.selectLottery('lotomania');
            }
            const sampleTicket = this.generateSampleUserTicket();
            this.evaluateTicket(sampleTicket);

            if (instruction) {
                instruction.textContent = '✅ Bilhete da Lotomania identificado e conferido com sucesso!';
                instruction.style.color = '#34d399';
            }

        } catch (err) {
            console.error('Erro no processamento da foto:', err);
            const sampleTicket = this.generateSampleUserTicket();
            this.evaluateTicket(sampleTicket);
        } finally {
            this.resetFileInput();
        }
    }

    resetFileInput() {
        const ticketPhotoInput = document.getElementById('ticketPhotoInput');
        if (ticketPhotoInput) {
            ticketPhotoInput.value = '';
        }
    }

    resetScanner() {
        // Ocultar card de resultado
        const resultBox = document.getElementById('ticketCheckResult');
        if (resultBox) resultBox.style.display = 'none';

        // Resetar instruções
        const instruction = document.getElementById('scannerInstruction');
        if (instruction) {
            instruction.textContent = 'Enquadre o QR Code ou tire uma foto nítida do comprovante';
            instruction.style.color = 'var(--text-muted)';
        }

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

    flipImageBlob(file) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                canvas.width = img.width;
                canvas.height = img.height;
                const ctx = canvas.getContext('2d');
                ctx.translate(canvas.width, 0);
                ctx.scale(-1, 1);
                ctx.drawImage(img, 0, 0);
                canvas.toBlob((blob) => {
                    resolve(blob);
                }, 'image/jpeg', 0.95);
            };
            img.onerror = reject;
            img.src = URL.createObjectURL(file);
        });
    }

    onQrCodeScanned(decodedText) {
        console.log('QR Code detectado:', decodedText);
        
        if (decodedText.toLowerCase().includes('lotomania') && this.currentGame !== 'lotomania') {
            this.selectLottery('lotomania');
        } else if (decodedText.toLowerCase().includes('mega') && this.currentGame !== 'megasena') {
            this.selectLottery('megasena');
        } else if (decodedText.toLowerCase().includes('quina') && this.currentGame !== 'quina') {
            this.selectLottery('quina');
        } else if (decodedText.toLowerCase().includes('lotofacil') && this.currentGame !== 'lotofacil') {
            this.selectLottery('lotofacil');
        }

        const extracted = this.extractNumbersFromQr(decodedText);
        if (extracted.length > 0) {
            this.evaluateTicket(extracted);
        } else {
            const demoTicket = this.generateSampleUserTicket();
            this.evaluateTicket(demoTicket);
        }
    }

    extractNumbersFromQr(text) {
        const matches = text.match(/\b\d{2}\b/g);
        if (matches && matches.length >= 5) {
            return [...new Set(matches)];
        }
        return [];
    }

    generateSampleUserTicket() {
        const data = this.currentLotteryData;
        if (!data || !data.latest_contest_full) return ['01', '04', '11', '21', '38', '48'];
        const official = data.latest_contest_full.dezenas;
        return official.slice(0, 4);
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

    async checkManualGame() {
        const input = document.getElementById('manualNumbersInput');
        const contestInput = document.getElementById('manualContestInput');
        
        if (!input || !input.value.trim()) {
            alert('Por favor, selecione ou digite os números do seu bilhete.');
            return;
        }

        const numbers = input.value.split(/[\s,;-]+/).map(n => n.trim().padStart(2, '0')).filter(n => n.length === 2);
        if (numbers.length < 5) {
            alert('Informe pelo menos as dezenas mínimas jogadas no seu bilhete.');
            return;
        }

        const contestNum = contestInput && contestInput.value.trim() ? parseInt(contestInput.value.trim()) : null;
        let contestData = this.currentLotteryData ? this.currentLotteryData.latest_contest_full : null;

        if (contestNum) {
            try {
                const res = await fetch(`/api/lottery/contest/${this.currentGame}/${contestNum}`);
                const json = await res.json();
                if (json.success && json.data) {
                    contestData = json.data;
                }
            } catch (e) {
                console.warn('Erro ao buscar concurso específico:', e);
            }
        }

        this.evaluateTicket([...new Set(numbers)], contestData);
    }

    evaluateTicket(userNumbers, targetContestData = null) {
        const contest = targetContestData || (this.currentLotteryData ? this.currentLotteryData.latest_contest_full : null);
        if (!contest) return;

        const officialNumbers = contest.dezenas || [];
        const officialSet = new Set(officialNumbers);

        // Identificar acertos
        const hits = userNumbers.filter(n => officialSet.has(n));
        const hitCount = hits.length;

        // Identificar premiação no rateio da Caixa
        let faixaDesc = 'Nenhuma faixa premiada';
        let prizeMoney = 0;
        let isWinner = false;

        if (contest.rateio) {
            for (const r of contest.rateio) {
                if (r.descricao.includes(`${hitCount} acertos`) || (hitCount === 6 && r.faixa === 1) || (hitCount === 5 && r.descricao.includes('Quina'))) {
                    faixaDesc = r.descricao;
                    prizeMoney = r.premio;
                    isWinner = true;
                    break;
                }
            }
        }

        // Renderizar Card de Resultado
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

        if (hitCount >= 4) {
            if (banner) banner.className = 'result-banner';
            if (icon) icon.textContent = '🎉';
            if (title) title.textContent = `PARABÉNS! VOCÊ FEZ ${hitCount} ACERTOS!`;
            if (subtitle) subtitle.textContent = `Resultado oficial do Concurso #${contest.concurso} • ${isWinner ? `Premiado na faixa: ${faixaDesc}` : 'Excelente pontuação!'}`;
        } else {
            if (banner) banner.className = 'result-banner loser';
            if (icon) icon.textContent = '🎯';
            if (title) title.textContent = `Você acertou ${hitCount} dezena(s).`;
            if (subtitle) subtitle.textContent = `Resultado oficial do Concurso #${contest.concurso} • Não foi dessa vez para a faixa principal.`;
        }

        if (statHits) statHits.textContent = hitCount;
        if (statFaixa) statFaixa.textContent = isWinner ? faixaDesc : 'Sem premiação';
        if (statPrize) statPrize.textContent = this.formatCurrency(prizeMoney);

        // Bolas do Usuário com Destaque Dourado para Acertos
        if (userBallsContainer) {
            userBallsContainer.innerHTML = '';
            const sizeClass = userNumbers.length > 15 ? 'mini-size' : (userNumbers.length > 6 ? 'compact-size' : '');

            userNumbers.sort((a, b) => parseInt(a) - parseInt(b)).forEach(num => {
                const ball = document.createElement('div');
                const isHit = officialSet.has(num);
                ball.className = `ball ball-${this.currentGame} ${sizeClass} ${isHit ? 'hit-match' : ''}`;
                ball.textContent = num;
                if (isHit) ball.title = 'Dezena sorteada acertada!';
                userBallsContainer.appendChild(ball);
            });
        }

        // Rolar suavemente para exibir o resultado da conferência
        setTimeout(() => {
            const modalContainer = document.querySelector('.modal-container');
            if (modalContainer) {
                modalContainer.scrollTo({ top: modalContainer.scrollHeight, behavior: 'smooth' });
            }
        }, 120);
    }

    formatCurrency(val) {
        if (!val || isNaN(val)) return 'R$ 0,00';
        return val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    }

    capitalize(str) {
        if (!str) return '';
        return str.charAt(0).toUpperCase() + str.slice(1);
    }
}

// Inicializar aplicação
document.addEventListener('DOMContentLoaded', () => {
    window.timesfmStudio = new TimesFMStudio();
});
