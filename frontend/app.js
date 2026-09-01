// TimesFM Studio — Controlador Frontend para Loterias Caixa e Séries Temporais

class TimesFMStudio {
    constructor() {
        this.currentGame = 'megasena';
        this.currentStrategy = 0;
        this.currentLotteryData = null;
        this.currentFilter = 'all';
        this.probChart = null;

        this.init();
    }

    init() {
        this.bindEvents();
        this.checkHealth();
        this.loadAllLotteryPrizes();
        this.selectLotteryGame('megasena');
    }

    bindEvents() {
        // Modo de Visualização (Loterias vs Séries Gerais)
        const modeLotteryBtn = document.getElementById('modeLotteryBtn');
        const modeGeneralBtn = document.getElementById('modeGeneralBtn');
        const lotteryView = document.getElementById('lotteryView');
        const genericView = document.getElementById('genericView');

        if (modeLotteryBtn && modeGeneralBtn) {
            modeLotteryBtn.addEventListener('click', () => {
                modeLotteryBtn.classList.add('active');
                modeGeneralBtn.classList.remove('active');
                lotteryView.style.display = 'flex';
                genericView.style.display = 'none';
            });

            modeGeneralBtn.addEventListener('click', () => {
                modeGeneralBtn.classList.add('active');
                modeLotteryBtn.classList.remove('active');
                lotteryView.style.display = 'none';
                genericView.style.display = 'grid';
            });
        }

        // Seletores de Loterias
        const lotteryBtns = document.querySelectorAll('.lottery-card-btn');
        lotteryBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const game = btn.getAttribute('data-game');
                this.selectLotteryGame(game);
            });
        });

        // Seletores de Estratégia do Jogo
        const stratBtns = document.querySelectorAll('.strategy-tab');
        stratBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                stratBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentStrategy = parseInt(btn.getAttribute('data-strategy'), 10);
                this.renderSuggestedGame();
            });
        });

        // Recalcular Previsão
        const recalcBtn = document.getElementById('recalculateLotteryBtn');
        if (recalcBtn) {
            recalcBtn.addEventListener('click', () => {
                this.loadLotteryPrediction(this.currentGame);
            });
        }

        // Copiar Jogo
        const copyBtn = document.getElementById('copyGameBtn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                this.copyCurrentGameToClipboard();
            });
        }

        // Filtros das Dezenas
        const filterBtns = document.querySelectorAll('.filter-pill');
        filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentFilter = btn.getAttribute('data-filter');
                this.renderNumbersMatrix();
                this.renderProbabilityChart();
            });
        });
    }

    async checkHealth() {
        const statusText = document.getElementById('engineStatusText');
        const statusPill = document.getElementById('engineStatusPill');

        try {
            const res = await fetch('/api/health');
            const data = await res.json();
            if (statusText) {
                statusText.textContent = data.model_loaded 
                    ? 'Google TimesFM Pronto (PyTorch CPU)' 
                    : 'Motor Analítico Ativo (Caixa Live)';
            }
        } catch (e) {
            if (statusText) {
                statusText.textContent = 'Modo Local / Standalone';
            }
        }
    }

    async loadAllLotteryPrizes() {
        const games = ['megasena', 'quina', 'lotofacil', 'lotomania'];
        for (const g of games) {
            try {
                const res = await fetch(`/api/lottery/info/${g}`);
                const json = await res.json();
                if (json.success && json.data) {
                    const prizeBadge = document.getElementById(`badgePrize${this.capitalize(g)}`);
                    const statusBadge = document.getElementById(`badgeStatus${this.capitalize(g)}`);
                    
                    if (prizeBadge) {
                        prizeBadge.textContent = this.formatCurrency(json.data.valor_estimado_proximo);
                    }
                    if (statusBadge) {
                        statusBadge.textContent = json.data.acumulou ? 'Acumulou 🔥' : 'Premiado ✨';
                        statusBadge.style.color = json.data.acumulou ? '#fbbf24' : '#34d399';
                    }
                }
            } catch (e) {
                console.warn(`Erro ao buscar prêmio de ${g}:`, e);
            }
        }
    }

    selectLotteryGame(gameId) {
        this.currentGame = gameId;

        // Atualiza estilo do body e dos botões
        document.body.className = `theme-${gameId}`;
        document.querySelectorAll('.lottery-card-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-game') === gameId);
        });

        this.loadLotteryPrediction(gameId);
    }

    async loadLotteryPrediction(gameId) {
        const ballsContainer = document.getElementById('predictedBallsContainer');
        if (ballsContainer) {
            ballsContainer.innerHTML = `
                <div class="loading-balls">
                    <div class="spinner"></div>
                    <span>Executando inferência com TimesFM para ${this.capitalize(gameId)}...</span>
                </div>
            `;
        }

        try {
            const res = await fetch('/api/lottery/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId })
            });

            const json = await res.json();
            if (!json.success || !json.data) {
                throw new Error(json.detail || 'Falha ao processar previsão.');
            }

            this.currentLotteryData = json.data;
            this.renderFullLotteryDashboard();

        } catch (e) {
            console.error('Erro na previsão:', e);
            if (ballsContainer) {
                ballsContainer.innerHTML = `<div style="color: var(--danger)">Erro: ${e.message}</div>`;
            }
        }
    }

    renderFullLotteryDashboard() {
        const data = this.currentLotteryData;
        if (!data) return;

        // 1. Títulos e Badges
        const predTitle = document.getElementById('predictionTitle');
        const confScore = document.getElementById('confidenceScore');
        const latVal = document.getElementById('engineLatency');

        if (predTitle) {
            predTitle.textContent = `Projeção para o Próximo Concurso: ${data.game_name} #${data.target_contest}`;
        }
        if (confScore) {
            confScore.textContent = `${data.confidence_score}%`;
        }
        if (latVal) {
            latVal.textContent = `Inferência: ${data.inference_time_ms} ms`;
        }

        // 2. Renderizar Jogo Sugerido
        this.renderSuggestedGame();

        // 3. Renderizar Último Concurso Oficial e Comparativo
        this.renderLatestContestSection();

        // 4. Renderizar Gráfico e Matriz de Dezenas
        this.renderProbabilityChart();
        this.renderNumbersMatrix();
    }

    renderSuggestedGame() {
        const data = this.currentLotteryData;
        if (!data || !data.suggested_games) return;

        const game = data.suggested_games[this.currentStrategy] || data.suggested_games[0];
        const container = document.getElementById('predictedBallsContainer');
        const parityBalance = document.getElementById('parityBalance');
        const sumBalance = document.getElementById('sumBalance');

        if (container) {
            container.innerHTML = '';
            const sizeClass = game.numbers.length > 15 ? 'mini-size' : (game.numbers.length > 6 ? 'compact-size' : '');
            
            game.numbers.forEach(num => {
                const ball = document.createElement('div');
                ball.className = `ball ball-${this.currentGame} ${sizeClass}`;
                ball.textContent = num;
                container.appendChild(ball);
            });
        }

        if (parityBalance) {
            parityBalance.textContent = `${game.evens} Pares / ${game.odds} Ímpares`;
        }
        if (sumBalance) {
            sumBalance.textContent = `Soma Total: ${game.sum}`;
        }
    }

    renderLatestContestSection() {
        const data = this.currentLotteryData;
        if (!data || !data.latest_contest_full) return;

        const latest = data.latest_contest_full;
        const comp = data.comparison_with_latest;

        // Títulos
        const contestTitle = document.getElementById('latestContestTitle');
        const contestLoc = document.getElementById('latestContestLocation');
        const jackpotVal = document.getElementById('jackpotValue');
        const jackpotStatus = document.getElementById('jackpotStatusText');
        const matchTag = document.getElementById('matchTag');

        if (contestTitle) {
            contestTitle.textContent = `Concurso #${latest.concurso} realizado em ${latest.data_apuracao}`;
        }
        if (contestLoc) {
            contestLoc.textContent = `Local: ${latest.local_sorteio} — ${latest.municipio_sorteio}`;
        }
        if (jackpotVal) {
            jackpotVal.textContent = this.formatCurrency(latest.valor_estimado_proximo);
        }
        if (jackpotStatus) {
            jackpotStatus.textContent = latest.acumulou ? '🔥 Acumulou para o Próximo:' : '✨ Estimativa Próximo:';
        }
        if (matchTag) {
            matchTag.innerHTML = `Comparação com Projeção IA: <strong>${comp.hits_count} Acertos (${comp.hit_rate_pct}%)</strong>`;
        }

        // Bolas do Último Concurso
        const ballsContainer = document.getElementById('latestOfficialBalls');
        if (ballsContainer) {
            ballsContainer.innerHTML = '';
            const sizeClass = latest.dezenas.length > 15 ? 'mini-size' : (latest.dezenas.length > 6 ? 'compact-size' : '');
            
            const matchedSet = new Set(comp.matched_numbers || []);

            latest.dezenas.forEach(num => {
                const ball = document.createElement('div');
                const isMatched = matchedSet.has(num);
                ball.className = `ball ball-${this.currentGame} ${sizeClass} ${isMatched ? 'matched-hit' : ''}`;
                ball.textContent = num;
                if (isMatched) {
                    ball.title = 'Acerto na Projeção IA!';
                }
                ballsContainer.appendChild(ball);
            });
        }

        // Tabela de Rateio
        const tableBody = document.getElementById('payoutTableBody');
        if (tableBody && latest.rateio) {
            tableBody.innerHTML = '';
            latest.rateio.forEach(row => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${row.descricao}</td>
                    <td>${row.ganhadores.toLocaleString('pt-BR')} apostas</td>
                    <td class="prize-val">${this.formatCurrency(row.premio)}</td>
                `;
                tableBody.appendChild(tr);
            });
        }
    }

    renderProbabilityChart() {
        const data = this.currentLotteryData;
        if (!data || !data.all_numbers_ranking) return;

        const ctx = document.getElementById('lotteryProbChart');
        if (!ctx) return;

        let ranking = [...data.all_numbers_ranking];

        if (this.currentFilter === 'hot') {
            ranking = ranking.filter(x => x.recent_freq >= 2);
        } else if (this.currentFilter === 'delay') {
            ranking = ranking.filter(x => x.delay >= 5);
        } else if (this.currentFilter === 'ai') {
            ranking = ranking.slice(0, 15);
        }

        // Ordenar por número para gráfico limpo
        ranking.sort((a, b) => a.number - b.number);

        const labels = ranking.map(x => x.number_str);
        const scores = ranking.map(x => x.score);
        const delays = ranking.map(x => x.delay);

        if (this.probChart) {
            this.probChart.destroy();
        }

        const colorMap = {
            megasena: '#209869',
            quina: '#6a38eb',
            lotofacil: '#d63384',
            lotomania: '#f78100'
        };
        const activeColor = colorMap[this.currentGame] || '#209869';

        this.probChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Probabilidade TimesFM',
                        data: scores,
                        backgroundColor: activeColor,
                        borderRadius: 4,
                        borderSkipped: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#111a2e',
                        borderColor: '#1e2d4a',
                        borderWidth: 1,
                        callbacks: {
                            afterLabel: (ctx) => {
                                const idx = ctx.dataIndex;
                                return `Atraso: ${delays[idx]} concursos | Freq: ${ranking[idx].recent_freq} recentes`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } }
                    },
                    y: {
                        grid: { color: 'rgba(30, 45, 74, 0.4)' },
                        ticks: { color: '#64748b' }
                    }
                }
            }
        });
    }

    renderNumbersMatrix() {
        const data = this.currentLotteryData;
        if (!data || !data.all_numbers_ranking) return;

        const grid = document.getElementById('numbersMatrixGrid');
        if (!grid) return;

        grid.innerHTML = '';
        let ranking = [...data.all_numbers_ranking];

        if (this.currentFilter === 'hot') {
            ranking = ranking.filter(x => x.recent_freq >= 2);
        } else if (this.currentFilter === 'delay') {
            ranking = ranking.filter(x => x.delay >= 5);
        } else if (this.currentFilter === 'ai') {
            ranking = ranking.slice(0, 15);
        }

        ranking.sort((a, b) => a.number - b.number);

        ranking.forEach(item => {
            const cell = document.createElement('div');
            cell.className = 'number-cell';
            cell.innerHTML = `
                <span class="cell-num">${item.number_str}</span>
                <span class="cell-status">${item.status}</span>
                <span class="cell-freq">Atraso: ${item.delay}</span>
            `;
            grid.appendChild(cell);
        });
    }

    copyCurrentGameToClipboard() {
        const data = this.currentLotteryData;
        if (!data || !data.suggested_games) return;

        const game = data.suggested_games[this.currentStrategy] || data.suggested_games[0];
        const text = `${data.game_name} (Concurso #${data.target_contest}): ${game.numbers.join(' - ')}`;

        navigator.clipboard.writeText(text).then(() => {
            const btnText = document.getElementById('copyBtnText');
            if (btnText) {
                const original = btnText.textContent;
                btnText.textContent = '✅ Bilhete Copiado!';
                setTimeout(() => {
                    btnText.textContent = original;
                }, 2500);
            }
        }).catch(err => {
            console.error('Falha ao copiar:', err);
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

// Inicializar quando o DOM carregar
document.addEventListener('DOMContentLoaded', () => {
    window.timesfmStudio = new TimesFMStudio();
});
