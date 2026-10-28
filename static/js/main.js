document.addEventListener('DOMContentLoaded', () => {
    const tipoInput = document.getElementById('tipoInput');
    const gameIdInput = document.getElementById('gameIdInput');
    const idsInput = document.getElementById('idsInput');
    const formAdd = document.getElementById('form-add-lote');

    // ---- Alterna visibilidade do campo extra ----
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

    // ---- Adicionar em lote ----
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
                alert("Nenhum ID extraído do campo principal.");
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

                if (response.ok) {
                    window.location.reload();
                } else {
                    alert("Erro ao salvar no servidor.");
                    btn.innerHTML = '<i class="bi bi-cpu"></i> Adicionar';
                    btn.disabled = false;
                }
            } catch (erro) {
                console.error(erro);
                alert("Erro de conexão.");
            }
        });
    }

    // ---- DELETE ----
    document.querySelectorAll('.btn-delete').forEach(btn => {
        btn.addEventListener('click', async () => {
            const tipo = btn.dataset.tipo;
            const id = btn.dataset.id;
            const nome = tipo === 'jogo' ? 'este set (e suas conquistas)' : 'esta conquista';

            if (!confirm(`Excluir ${nome}?`)) return;

            btn.disabled = true;
            btn.innerHTML = '<i class="bi bi-hourglass-split"></i>';

            try {
                const r = await fetch(`/api/delete/${tipo}/${id}`, { method: 'DELETE' });
                if (r.ok) {
                    // remove do DOM sem reload (mais rápido)
                    const row = document.querySelector(
                        `[data-tipo="${tipo}"][data-id="${id}"]`
                    );
                    if (row) row.remove();
                    // se era jogo, remove as conquistas filhas do DOM também
                    if (tipo === 'jogo') {
                        document.querySelectorAll(
                            `[data-tipo="conquista"]`
                        ).forEach(c => {
                            // conquistas filhas estão logo depois do jogo no DOM;
                            // o reload simples resolve, então recarrega se for jogo
                        });
                        window.location.reload();
                    }
                } else {
                    alert('Erro ao excluir.');
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-trash"></i>';
                }
            } catch (e) {
                console.error(e);
                alert('Erro de conexão.');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-trash"></i>';
            }
        });
    });

    // ---- REFRESH MANUAL ----
    document.querySelectorAll('.btn-refresh').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            btn.disabled = true;
            btn.innerHTML = '<i class="bi bi-hourglass-split"></i>';

            try {
                const r = await fetch(`/api/refresh/${id}`, { method: 'POST' });
                if (r.ok) {
                    window.location.reload();
                } else {
                    alert('Erro ao atualizar.');
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i>';
                }
            } catch (e) {
                console.error(e);
                alert('Erro de conexão.');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i>';
            }
        });
    });

    // ---- AUTOSAVE DE NOTAS (debounce) ----
    const timers = {};
    document.querySelectorAll('.autosave-notas').forEach(input => {
        input.addEventListener('input', () => {
            const tipo = input.dataset.tipo;
            const id = input.dataset.id;
            const key = `${tipo}-${id}`;

            clearTimeout(timers[key]);
            timers[key] = setTimeout(async () => {
                try {
                    await fetch(`/api/notas/${tipo}/${id}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ notas: input.value })
                    });
                    // feedback sutil
                    input.style.borderColor = 'rgba(16,185,129,0.5)';
                    setTimeout(() => { input.style.borderColor = ''; }, 600);
                } catch (e) {
                    console.error('Erro ao salvar nota', e);
                }
            }, 600); // espera 600ms após parar de digitar
        });
    });
});