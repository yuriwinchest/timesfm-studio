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
        this.pendingTicket = null;

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

        // Botão principal: congela o quadro da câmera e prepara preview
        const captureFrameBtn = document.getElementById('captureFrameBtn');
        if (captureFrameBtn) {
            captureFrameBtn.addEventListener('click', () => {
                this.captureFromCamera();
            });
        }

        // Botão Escolher Foto da Galeria / Arquivo
        const triggerPhotoBtn = document.getElementById('triggerPhotoBtn');
        const ticketPhotoInput = document.getElementById('ticketPhotoInput');
        if (triggerPhotoBtn && ticketPhotoInput) {
            triggerPhotoBtn.addEventListener('click', () => {
                ticketPhotoInput.click();
            });

            ticketPhotoInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    this.handlePhotoReady(e.target.files[0]);
                }
            });
        }

        // Botão Ação: Verificar Resultado
        const verifyPhotoBtn = document.getElementById('verifyPhotoBtn');
        if (verifyPhotoBtn) {
            verifyPhotoBtn.addEventListener('click', () => {
                this.analyzeAndVerifyPhoto();
            });
        }

        // Botão Trocar / Tirar Outra Foto
        const retakePhotoBtn = document.getElementById('retakePhotoBtn');
        if (retakePhotoBtn) {
            retakePhotoBtn.addEventListener('click', () => {
                this.resetPhotoCaptureState();
                this.startCameraScanner();
            });
        }

        // Confirmação das dezenas lidas do comprovante
        const confirmTicketBtn = document.getElementById('confirmTicketBtn');
        if (confirmTicketBtn) {
            confirmTicketBtn.addEventListener('click', () => {
                if (!this.pendingTicket) return;
                this.checkTicket(
                    this.pendingTicket.game_id,
                    this.pendingTicket.numbers,
                    this.pendingTicket.contest,
                    this.pendingTicket.games
                );
            });
        }

        const editTicketBtn = document.getElementById('editTicketBtn');
        if (editTicketBtn) {
            editTicketBtn.addEventListener('click', () => {
                const t = this.pendingTicket || {};
                this.openManualWith(t.numbers || [], t.contest, t.game_id);
            });
        }

        const editFromResultsBtn = document.getElementById('editFromResultsBtn');
        if (editFromResultsBtn) {
            editFromResultsBtn.addEventListener('click', () => {
                const t = this.pendingTicket || {};
                this.openManualWith(t.numbers || [], t.contest, t.game_id);
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

            // 503 = fonte oficial fora do ar. A tela diz isso, em vez de exibir
            // um resultado fabricado no lugar do sorteio real.
            if (res.status === 503) throw new Error(json.detail || 'A API oficial da Caixa está indisponível no momento.');
            if (!json.success || !json.data) throw new Error(json.detail || 'Falha ao buscar dados');

            this.currentLotteryData = json.data;
            this.renderDashboard();

        } catch (e) {
            console.error('Erro ao processar loteria:', e);
            if (drawnBallsRow) drawnBallsRow.innerHTML = `<div style="color: var(--danger)">${e.message}</div>`;
            if (aiBallsRow) aiBallsRow.innerHTML = `<div style="color: var(--text-muted)">Sem análise: ela só existe com histórico oficial da Caixa.</div>`;
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

        // Transparencia: quantos concursos oficiais sustentam a analise
        const pillHistory = document.getElementById('pillHistory');
        if (pillHistory && data.history) {
            pillHistory.textContent = `${data.history.contests} concursos reais`;
            pillHistory.title = `Concursos #${data.history.from_contest} a #${data.history.to_contest} — ${data.history.source}`;
        }

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

    formatCurrency(val) {
        if (!val || isNaN(val)) return 'R$ 0,00';
        return val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    }

    capitalize(str) {
        if (!str) return '';
        return str.charAt(0).toUpperCase() + str.slice(1);
    }
}

// Acopla o modulo de conferencia de bilhetes ao controlador principal.
Object.getOwnPropertyNames(TicketScannerMixin.prototype)
    .filter(name => name !== 'constructor')
    .forEach(name => {
        TimesFMStudio.prototype[name] = TicketScannerMixin.prototype[name];
    });

// Inicializar aplicação
document.addEventListener('DOMContentLoaded', () => {
    window.timesfmStudio = new TimesFMStudio();
});
