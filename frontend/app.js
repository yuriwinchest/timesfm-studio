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
        // Seleção de Visão Principal: Resultados vs Palpites com IA
        const viewModeResults = document.getElementById('viewModeResults');
        const viewModePredictions = document.getElementById('viewModePredictions');
        const resultsView = document.getElementById('resultsView');
        const predictionsView = document.getElementById('predictionsView');

        if (viewModeResults && viewModePredictions) {
            viewModeResults.addEventListener('click', () => {
                viewModeResults.classList.add('active');
                viewModePredictions.classList.remove('active');
                if (resultsView) resultsView.style.display = 'block';
                if (predictionsView) predictionsView.style.display = 'none';
            });

            viewModePredictions.addEventListener('click', () => {
                viewModePredictions.classList.add('active');
                viewModeResults.classList.remove('active');
                if (resultsView) resultsView.style.display = 'none';
                if (predictionsView) predictionsView.style.display = 'block';
            });
        }

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

        // Recalcular Previsão IA TimesFM
        const recalcBtn = document.getElementById('recalcAiBtn');
        if (recalcBtn) {
            recalcBtn.addEventListener('click', () => {
                this.loadLotteryData(this.currentGame, true);
            });
        }

        // Copiar Jogos de Palpite
        const copyMainBtn = document.getElementById('copyAiGameBtn');
        if (copyMainBtn) {
            copyMainBtn.addEventListener('click', () => {
                this.copyGameByIndex(0, copyMainBtn);
            });
        }

        const copyHotBtn = document.getElementById('copyHotGameBtn');
        if (copyHotBtn) {
            copyHotBtn.addEventListener('click', () => {
                this.copyGameByIndex(1, copyHotBtn);
            });
        }

        const copyDelayBtn = document.getElementById('copyDelayGameBtn');
        if (copyDelayBtn) {
            copyDelayBtn.addEventListener('click', () => {
                this.copyGameByIndex(2, copyDelayBtn);
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
                flipMirrorBtn.classList.toggle('active', this.isMirrored);
                flipMirrorBtn.title = this.isMirrored ? 'Modo Normal (Espelhado)' : 'Desespelhar (Inverter)';
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

    async loadLotteryData(gameId, isRegenerate = false) {
        const drawnBallsRow = document.getElementById('officialDrawnBalls');
        const aiBallsRow = document.getElementById('predictedBallsRow');
        const hotBallsRow = document.getElementById('hotBallsRow');
        const delayBallsRow = document.getElementById('delayBallsRow');
        const recalcBtn = document.getElementById('recalcAiBtn');

        if (drawnBallsRow) drawnBallsRow.innerHTML = '<div class="spinner"></div>';
        if (aiBallsRow) aiBallsRow.innerHTML = '<div class="spinner"></div>';
        if (hotBallsRow) hotBallsRow.innerHTML = '<div class="spinner"></div>';
        if (delayBallsRow) delayBallsRow.innerHTML = '<div class="spinner"></div>';

        if (isRegenerate && recalcBtn) {
            recalcBtn.disabled = true;
            recalcBtn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div><span>Calculando TimesFM...</span>';
        }

        try {
            const res = await fetch('/api/lottery/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId })
            });

            const json = await res.json();

            if (res.status === 503) throw new Error(json.detail || 'A API oficial da Caixa está indisponível no momento.');
            if (!json.success || !json.data) throw new Error(json.detail || 'Falha ao buscar dados');

            this.currentLotteryData = json.data;
            this.renderDashboard();

        } catch (e) {
            console.error('Erro ao processar loteria:', e);
            if (drawnBallsRow) drawnBallsRow.innerHTML = `<div style="color: var(--danger)">${e.message}</div>`;
            if (aiBallsRow) aiBallsRow.innerHTML = `<div style="color: var(--text-muted)">Sem análise: ela só existe com histórico oficial da Caixa.</div>`;
        } finally {
            if (recalcBtn) {
                recalcBtn.disabled = false;
                recalcBtn.innerHTML = `
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                        <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
                    </svg>
                    <span>✨ Gerar Novo Palpite TimesFM</span>
                `;
            }
        }
    }

    renderDashboard() {
        const data = this.currentLotteryData;
        if (!data) return;

        const latest = data.latest_contest_full;
        const games = data.suggested_games || [];
        const mainAiGame = games[0] || { numbers: [], evens: 0, odds: 0, sum: 0 };
        const hotGame = games[1] || { numbers: [], evens: 0, odds: 0, sum: 0 };
        const delayGame = games[2] || { numbers: [], evens: 0, odds: 0, sum: 0 };

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

        // 4. Aba de Palpites com IA (TimesFM)
        const predSectionTitle = document.getElementById('predSectionTitle');
        const predConfidenceTag = document.getElementById('predConfidenceTag');
        const aiBallsRow = document.getElementById('predictedBallsRow');
        const hotBallsRow = document.getElementById('hotBallsRow');
        const delayBallsRow = document.getElementById('delayBallsRow');

        if (predSectionTitle) {
            predSectionTitle.textContent = `Palpites Oficiais para o Concurso #${data.target_contest} (${data.game_name})`;
        }
        if (predConfidenceTag) {
            predConfidenceTag.textContent = `Confiança: ${data.confidence_score}%`;
        }

        // Renderiza Bolas do Jogo 1 (Principal)
        if (aiBallsRow) {
            this.renderBallsList(aiBallsRow, mainAiGame.numbers);
            const pillParity = document.getElementById('pillParity');
            const pillSum = document.getElementById('pillSum');
            if (pillParity) pillParity.textContent = `${mainAiGame.evens}P / ${mainAiGame.odds}I`;
            if (pillSum) pillSum.textContent = `Soma: ${mainAiGame.sum}`;
        }

        // Renderiza Bolas do Jogo 2 (Quentes)
        if (hotBallsRow) {
            this.renderBallsList(hotBallsRow, hotGame.numbers);
            const hotParity = document.getElementById('hotParity');
            const hotSum = document.getElementById('hotSum');
            if (hotParity) hotParity.textContent = `${hotGame.evens}P / ${hotGame.odds}I`;
            if (hotSum) hotSum.textContent = `Soma: ${hotGame.sum}`;
        }

        // Renderiza Bolas do Jogo 3 (Atrasadas)
        if (delayBallsRow) {
            this.renderBallsList(delayBallsRow, delayGame.numbers);
            const delayParity = document.getElementById('delayParity');
            const delaySum = document.getElementById('delaySum');
            if (delayParity) delayParity.textContent = `${delayGame.evens}P / ${delayGame.odds}I`;
            if (delaySum) delaySum.textContent = `Soma: ${delayGame.sum}`;
        }
    }

    renderBallsList(container, numbers) {
        container.innerHTML = '';
        const sizeClass = numbers.length > 15 ? 'mini-size' : (numbers.length > 6 ? 'compact-size' : '');

        numbers.forEach(num => {
            const ball = document.createElement('div');
            ball.className = `ball ball-${this.currentGame} ${sizeClass}`;
            ball.textContent = num;
            container.appendChild(ball);
        });
    }

    copyGameByIndex(index, btnElement) {
        const data = this.currentLotteryData;
        if (!data || !data.suggested_games || !data.suggested_games[index]) return;

        const game = data.suggested_games[index];
        const text = `${data.game_name} #${data.target_contest} (${game.name}): ${game.numbers.join(' - ')}`;

        navigator.clipboard.writeText(text).then(() => {
            if (btnElement) {
                const original = btnElement.innerHTML;
                btnElement.innerHTML = '✅ Copiado!';
                btnElement.style.borderColor = '#10b981';
                btnElement.style.color = '#34d399';
                setTimeout(() => {
                    btnElement.innerHTML = original;
                    btnElement.style.borderColor = '';
                    btnElement.style.color = '';
                }, 2000);
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
