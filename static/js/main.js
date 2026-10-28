// Se a sessão expirar, qualquer chamada à API volta 401: manda para o login.
(() => {
    const fetchOriginal = window.fetch.bind(window);
    window.fetch = async (...args) => {
        const resposta = await fetchOriginal(...args);
        if (resposta.status === 401) window.location.href = '/login';
        return resposta;
    };
})();

document.addEventListener('DOMContentLoaded', () => {

    // ==========================================
    // 1. BARRA DE ADICIONAR
    // ==========================================
    const tipoInput = document.getElementById('tipoInput');
    const gameIdInput = document.getElementById('gameIdInput');
    const idsInput = document.getElementById('idsInput');
    const formAdd = document.getElementById('form-add-lote');

    if (tipoInput) {
        tipoInput.addEventListener('change', (e) => {
            if (e.target.value === 'conquista') {
                gameIdInput.classList.remove('d-none');
                idsInput.placeholder = "Cole os IDs das Conquistas (vírgula ou espaço)...";
            } else {
                gameIdInput.classList.add('d-none');
                idsInput.placeholder = "Cole os IDs dos Sets (vírgula ou espaço)...";
            }
        });
    }

    if (formAdd) {
        formAdd.addEventListener('submit', async (e) => {
            e.preventDefault();
            const tipo = tipoInput.value;
            const ids = idsInput.value.match(/\d+/g);
            let gameId = null;

            if (tipo === 'conquista') {
                const matchGame = gameIdInput.value.match(/\d+/);
                if (!matchGame) {
                    alert("Informe o ID do Set (Game ID) para vincular as conquistas.");
                    return;
                }
                gameId = parseInt(matchGame[0]);
            }

            if (!ids || ids.length === 0) {
                alert("Nenhum ID extraído.");
                return;
            }

            const idsUnicos = [...new Set(ids)];
            const btn = formAdd.querySelector('button');
            btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Salvando...';
            btn.disabled = true;

            try {
                const response = await fetch('/api/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tipo, ids: idsUnicos, game_id: gameId })
                });
                if (response.ok) window.location.reload();
                else throw new Error('Erro no servidor');
            } catch (erro) {
                console.error(erro);
                alert("Erro ao salvar.");
                btn.innerHTML = '<i class="bi bi-plus-lg"></i> Adicionar';
                btn.disabled = false;
            }
        });
    }

    // ==========================================
    // 2. SANFONA (ABRIR/FECHAR CONQUISTAS)
    // ==========================================
    const LS_KEY = 'conquistas_abertas';
    
    function getAbertas() {
        try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}'); }
        catch { return {}; }
    }
    
    function setAberta(jogoId, aberta) {
        const a = getAbertas();
        a[jogoId] = aberta;
        localStorage.setItem(LS_KEY, JSON.stringify(a));
    }

    document.querySelectorAll('.conquistas-toggle').forEach(toggle => {
        const jogoId = toggle.dataset.jogoId;
        const container = document.getElementById(`conquistas-${jogoId}`);
        const icon = toggle.querySelector('.toggle-icon');
        if (!container) return;

        const abertas = getAbertas();
        const abertoInicial = abertas[jogoId] !== false; // default = aberto

        function aplicar(aberto) {
            if (aberto) {
                container.classList.remove('d-none');
                if (icon) icon.style.transform = 'rotate(0deg)';
            } else {
                container.classList.add('d-none');
                if (icon) icon.style.transform = 'rotate(-90deg)';
            }
        }
        aplicar(abertoInicial);

        toggle.addEventListener('click', () => {
            const estaAberto = !container.classList.contains('d-none');
            aplicar(!estaAberto);
            setAberta(jogoId, !estaAberto);
        });
    });

    // ==========================================
    // 3. DELETE E REFRESH
    // ==========================================
    document.querySelectorAll('.btn-delete').forEach(btn => {
        btn.addEventListener('click', async () => {
            const tipo = btn.dataset.tipo;
            const id = btn.dataset.id;
            if (!confirm(`Excluir este ${tipo === 'jogo' ? 'set (e suas conquistas)' : 'item'}?`)) return;

            btn.disabled = true;
            try {
                const r = await fetch(`/api/delete/${tipo}/${id}`, { method: 'DELETE' });
                if (r.ok) {
                    if (tipo === 'jogo') window.location.reload();
                    else btn.closest('.item-linha').remove();
                } else {
                    alert('Erro ao excluir.');
                    btn.disabled = false;
                }
            } catch (e) {
                console.error(e);
                alert('Erro de conexão.');
                btn.disabled = false;
            }
        });
    });

    document.querySelectorAll('.btn-refresh').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            btn.disabled = true;
            btn.innerHTML = '<i class="bi bi-hourglass-split"></i>';
            try {
                const r = await fetch(`/api/refresh/${id}`, { method: 'POST' });
                if (r.ok) window.location.reload();
                else throw new Error();
            } catch (e) {
                console.error(e);
                alert('Erro ao atualizar.');
                btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i>';
                btn.disabled = false;
            }
        });
    });

    // ==========================================
    // 4. MODAL DE NOTAS, TAGS E CONQUISTA EXCLUSIVA
    // ==========================================
    const modalEl = document.getElementById('modalEditar');
    const modal = modalEl && window.bootstrap ? new bootstrap.Modal(modalEl) : null;
    
    const modalTitulo = document.getElementById('modalTitulo');
    const modalStatus = document.getElementById('modalStatus');
    const modalNotas = document.getElementById('modalNotas');
    const modalConquista = document.getElementById('modalConquista');
    const modalConquistaIdManual = document.getElementById('modalConquistaIdManual');
    const wrapConquista = document.getElementById('wrapConquista');
    const wrapConquistaManual = document.getElementById('wrapConquistaManual');
    
    // Novos elementos
    const wrapNotaConquista = document.getElementById('wrapNotaConquista');
    const modalNotaConquista = document.getElementById('modalNotaConquista');
    
    const wrapTags = document.getElementById('wrapTags');
    const modalFeitoPorMim = document.getElementById('modalFeitoPorMim');
    const modalEmRevisao = document.getElementById('modalEmRevisao');
    
    const modalUltima = document.getElementById('modalUltima');
    const btnMarcar = document.getElementById('btnMarcarManutencao');
    const btnSalvar = document.getElementById('btnSalvarModal');

    let itemAtual = { tipo: null, id: null };
    let marcarManutencao = false;

    // Função que mostra/oculta o bloco de nota baseado na seleção da conquista
    function checarConquistaSelecionada() {
        if (!wrapNotaConquista) return;
        let temConquista = false;
        
        if (wrapConquistaManual.style.display === 'block') {
            temConquista = modalConquistaIdManual.value.trim() !== '';
        } else {
            temConquista = modalConquista.value !== '';
        }

        if (temConquista) {
            wrapNotaConquista.style.display = 'block';
        } else {
            wrapNotaConquista.style.display = 'none';
            modalNotaConquista.value = ''; // Limpa se desmarcar
        }
    }

    // Adiciona eventos para verificar quando o usuário muda a conquista
    if (modalConquista) modalConquista.addEventListener('change', checarConquistaSelecionada);
    if (modalConquistaIdManual) modalConquistaIdManual.addEventListener('input', checarConquistaSelecionada);

    function abrirModal(tipo, id, titulo) {
        if (!modal) return;
        
        itemAtual = { tipo, id };
        marcarManutencao = false;
        if (btnMarcar) btnMarcar.classList.remove('active');

        modalTitulo.textContent = `${tipo === 'jogo' ? 'Set' : 'Conquista'}: ${titulo}`;

        fetch(`/api/item/${tipo}/${id}`)
            .then(r => r.json())
            .then(d => {
                modalStatus.value = d.status || 'pendente';
                modalNotas.value = d.notas || '';
                modalUltima.textContent = d.ultima_manutencao
                    ? new Date(d.ultima_manutencao).toLocaleString('pt-BR')
                    : '—';

                // Reseta a caixa de conquista
                modalNotaConquista.value = d.nota_conquista_manutencao || '';
                wrapNotaConquista.style.display = 'none'; // começa oculta

                if (tipo === 'jogo') {
                    wrapConquista.style.display = 'block';
                    wrapTags.style.display = 'flex';
                    modalFeitoPorMim.checked = d.feito_por_mim || false;
                    modalEmRevisao.checked = d.em_revisao || false;
                    
                    const conquistas = d.conquistas || [];

                    if (conquistas.length > 0) {
                        wrapConquistaManual.style.display = 'none';
                        modalConquista.style.display = 'block';
                        modalConquista.innerHTML = '<option value="">— Nenhuma —</option>';
                        
                        conquistas.forEach(c => {
                            const opt = document.createElement('option');
                            opt.value = c.id;
                            opt.textContent = `${c.titulo} (#${c.id})`;
                            if (c.id === d.conquista_manutencao_id) opt.selected = true;
                            modalConquista.appendChild(opt);
                        });

                        if (d.conquista_manutencao_id && !d.conquista_referenciada_cadastrada) {
                            wrapConquistaManual.style.display = 'block';
                            modalConquista.style.display = 'none';
                            modalConquistaIdManual.value = d.conquista_manutencao_id;
                        } else {
                            modalConquistaIdManual.value = '';
                        }
                    } else {
                        modalConquista.style.display = 'none';
                        wrapConquistaManual.style.display = 'block';
                        modalConquistaIdManual.value = d.conquista_manutencao_id || '';
                    }
                } else {
                    wrapConquista.style.display = 'none';
                    wrapTags.style.display = 'none';
                }

                // Verifica se precisa mostrar a caixa de texto da conquista
                checarConquistaSelecionada();

                modal.show();
            })
            .catch(e => {
                console.error(e);
                alert('Erro ao carregar dados do item.');
            });
    }

    // Clique nos botões de nota
    document.querySelectorAll('.btn-nota').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const linha = btn.closest('.item-linha');
            const tituloEl = linha.querySelector('.fw-bold, .fw-medium');
            const titulo = tituloEl ? tituloEl.textContent.trim() : 'Desconhecido';
            abrirModal(btn.dataset.tipo, btn.dataset.id, titulo);
        });
    });

    if (btnMarcar) {
        btnMarcar.addEventListener('click', () => {
            marcarManutencao = true;
            modalUltima.textContent = new Date().toLocaleString('pt-BR') + ' (salvar p/ confirmar)';
            btnMarcar.classList.add('active');
        });
    }

    if (btnSalvar) {
        btnSalvar.addEventListener('click', async () => {
            const payload = {
                notas: modalNotas.value,
                status: modalStatus.value,
                marcar_manutencao: marcarManutencao,
            };

            if (itemAtual.tipo === 'jogo') {
                payload.feito_por_mim = modalFeitoPorMim.checked;
                payload.em_revisao = modalEmRevisao.checked;
                
                // Se a caixa estiver visível, salva a nota exclusiva
                if (wrapNotaConquista.style.display === 'block') {
                    payload.nota_conquista_manutencao = modalNotaConquista.value;
                } else {
                    payload.nota_conquista_manutencao = "";
                }

                let refId = null;
                if (wrapConquistaManual.style.display === 'block') {
                    const val = modalConquistaIdManual.value.trim();
                    refId = val ? parseInt(val) : null;
                } else {
                    refId = modalConquista.value ? parseInt(modalConquista.value) : null;
                }
                payload.conquista_manutencao_id = refId;
            }

            btnSalvar.disabled = true;
            btnSalvar.innerHTML = '<i class="bi bi-hourglass-split"></i> Salvando...';

            try {
                const r = await fetch(`/api/editar/${itemAtual.tipo}/${itemAtual.id}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (r.ok) {
                    modal.hide();
                    window.location.reload();
                } else {
                    alert('Erro ao salvar.');
                }
            } catch (e) {
                console.error(e);
                alert('Erro de conexão.');
            } finally {
                btnSalvar.disabled = false;
                btnSalvar.innerHTML = '<i class="bi bi-check2"></i> Salvar';
            }
        });
    }
});