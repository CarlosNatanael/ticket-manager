import os
import re
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify
import requests
from dotenv import load_dotenv

from models import db, JogoMonitorado, ConquistaMonitorada

# Carrega as credenciais do .env
load_dotenv()
RA_USER = os.getenv('RA_USER')
RA_API_KEY = os.getenv('RA_API_KEY')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///monitor.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

CACHE_TTL = timedelta(minutes=10)

def buscar_dados_jogo(game_id):
    url = (
        f"https://retroachievements.org/API/API_GetGame.php"
        f"?z={RA_USER}&y={RA_API_KEY}&i={game_id}"
    )
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            d = r.json()
            icone_path = d.get('ImageIcon', '')
            icone_url = (
                f"https://media.retroachievements.org{icone_path}"
                if icone_path else ""
            )
            return {
                'titulo': d.get('GameTitle', f"Jogo {game_id}"),
                'icone': icone_url,
                'url_ticket': f"https://retroachievements.org/game/{game_id}/tickets",
            }
    except Exception as e:
        print(f"Erro ao buscar jogo {game_id}: {e}")
    return {
        'titulo': f"Jogo {game_id}",
        'icone': "",
        'url_ticket': f"https://retroachievements.org/game/{game_id}/tickets",
    }


def buscar_dados_conquista(achievement_id):
    url = (
        f"https://retroachievements.org/API/API_GetTicketData.php"
        f"?z={RA_USER}&y={RA_API_KEY}&a={achievement_id}"
    )
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            d = r.json()
            return {
                'titulo': d.get('AchievementTitle', f"Conquista #{achievement_id}"),
                'tickets': d.get('OpenTickets', 0) or 0,
                'url_ticket': d.get(
                    'URL',
                    f"https://retroachievements.org/achievement/{achievement_id}/tickets",
                ),
                'icone': "https://static.retroachievements.org/assets/images/favicon.webp",
            }
    except Exception:
        pass
    return {
        'titulo': f"Conquista #{achievement_id}",
        'tickets': 0,
        'url_ticket': "",
        'icone': "",
    }


def buscar_tickets_abertos_set(game_id):
    url = (
        f"https://retroachievements.org/API/API_GetTicketData.php"
        f"?z={RA_USER}&y={RA_API_KEY}&g={game_id}&d=1"
    )
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return 0
        tickets = r.json().get('Tickets', [])
        return sum(1 for t in tickets if t.get('ReportState') == 1)
    except Exception as e:
        print(f"Erro ao buscar tickets abertos do set {game_id}: {e}")
        return 0


def buscar_tickets_set_detalhado(game_id):
    url = (
        f"https://retroachievements.org/API/API_GetTicketData.php"
        f"?z={RA_USER}&y={RA_API_KEY}&g={game_id}&d=1"
    )
    contagem = {'open': 0, 'resolved': 0, 'closed': 0, 'total_abertos': 0}
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return contagem
        for t in r.json().get('Tickets', []):
            state = t.get('ReportState')
            if state == 1:
                contagem['open'] += 1
            elif state == 2:
                contagem['resolved'] += 1
            elif state == 3:
                contagem['closed'] += 1
        contagem['total_abertos'] = contagem['open']
    except Exception as e:
        print(f"Erro ao buscar detalhes do set {game_id}: {e}")
    return contagem

@app.route('/')
def dashboard():
    ordem = request.args.get('ordem', 'tickets')
    filtro_tag = request.args.get('tag', 'todas') # todas | meu | revisao

    jogos = JogoMonitorado.query.all()
    agora = datetime.utcnow()

    for jogo in jogos:
        idade = agora - (jogo.atualizado_em or datetime.min)
        if idade > CACHE_TTL:
            jogo.qtd_tickets_set = buscar_tickets_abertos_set(jogo.id)
            jogo.atualizado_em = agora
            for conquista in jogo.conquistas:
                dados = buscar_dados_conquista(conquista.id)
                conquista.qtd_tickets = dados['tickets']
                conquista.titulo = dados['titulo']
                if dados['url_ticket']:
                    conquista.url_ticket = dados['url_ticket']

    db.session.commit()

    # APLICA FILTRO DE TAG
    if filtro_tag == 'meu':
        jogos = [j for j in jogos if j.feito_por_mim]
    elif filtro_tag == 'revisao':
        jogos = [j for j in jogos if j.em_revisao]

    # ORDENAÇÃO
    if ordem == 'az':
        jogos.sort(key=lambda j: j.titulo.lower())
    elif ordem == 'set':
        jogos.sort(key=lambda j: j.id)
    elif ordem == 'conquista':
        jogos.sort(key=lambda j: (len(j.conquistas) == 0, j.titulo.lower()))
    else:
        jogos.sort(key=lambda j: j.qtd_tickets_set or 0, reverse=True)

    for jogo in jogos:
        jogo.conquistas.sort(key=lambda c: c.qtd_tickets or 0, reverse=True)

    return render_template('dashboard.html', jogos=jogos, ordem=ordem, filtro_tag=filtro_tag, ra_user=RA_USER)

@app.route('/api/delete/<tipo>/<int:item_id>', methods=['DELETE'])
def delete_item(tipo, item_id):
    if tipo == 'jogo':
        item = JogoMonitorado.query.get_or_404(item_id)
    elif tipo == 'conquista':
        item = ConquistaMonitorada.query.get_or_404(item_id)
    else:
        return jsonify({'erro': 'Tipo inválido'}), 400

    db.session.delete(item)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/editar/<tipo>/<int:item_id>', methods=['POST'])
def editar_item(tipo, item_id):
    dados = request.get_json() or {}

    if tipo == 'jogo':
        item = JogoMonitorado.query.get_or_404(item_id)
        if 'conquista_manutencao_id' in dados:
            item.conquista_manutencao_id = dados.get('conquista_manutencao_id')
        if 'nota_conquista_manutencao' in dados:
            item.nota_conquista_manutencao = dados.get('nota_conquista_manutencao')
    elif tipo == 'conquista':
        item = ConquistaMonitorada.query.get_or_404(item_id)
    else:
        return jsonify({'erro': 'Tipo inválido'}), 400

    if 'notas' in dados:
        item.notas = dados.get('notas', '')

    if 'status' in dados:
        item.status = dados.get('status', 'pendente')

    if 'feito_por_mim' in dados:
        item.feito_por_mim = bool(dados.get('feito_por_mim'))
    if 'em_revisao' in dados:
        item.em_revisao = bool(dados.get('em_revisao'))

    # marcar/desmarcar manutenção
    if dados.get('marcar_manutencao'):
        item.ultima_manutencao = datetime.utcnow()

    db.session.commit()
    return jsonify({
        'status': 'ok',
        'ultima_manutencao': item.ultima_manutencao.isoformat() if item.ultima_manutencao else None,
    })

@app.route('/api/item/<tipo>/<int:item_id>')
def get_item(tipo, item_id):
    if tipo == 'jogo':
        item = JogoMonitorado.query.get_or_404(item_id)
        conquistas = [
            {'id': c.id, 'titulo': c.titulo, 'qtd_tickets': c.qtd_tickets}
            for c in item.conquistas
        ]
        ref_id = item.conquista_manutencao_id
        ref_cadastrada = any(c['id'] == ref_id for c in conquistas) if ref_id else False
        return jsonify({
            'id': item.id,
            'titulo': item.titulo,
            'notas': item.notas or '',
            'status': item.status or 'pendente',
            'nota_conquista_manutencao': item.nota_conquista_manutencao or '',
            'ultima_manutencao': item.ultima_manutencao.isoformat() if item.ultima_manutencao else None,
            'conquista_manutencao_id': ref_id,
            'feito_por_mim': item.feito_por_mim,
            'em_revisao': item.em_revisao,
            'conquista_referenciada_cadastrada': ref_cadastrada,
            'conquistas': conquistas,
        })
    elif tipo == 'conquista':
        item = ConquistaMonitorada.query.get_or_404(item_id)
        return jsonify({
            'id': item.id,
            'titulo': item.titulo,
            'notas': item.notas or '',
            'status': item.status or 'pendente',
            'ultima_manutencao': item.ultima_manutencao.isoformat() if item.ultima_manutencao else None,
        })
    return jsonify({'erro': 'Tipo inválido'}), 400

@app.route('/api/add', methods=['POST'])
def add_ids():
    dados = request.get_json()
    tipo = dados.get('tipo')
    ids = dados.get('ids', [])
    game_id_str = dados.get('game_id')

    if not ids or not tipo:
        return jsonify({'erro': 'Dados inválidos'}), 400

    game_id = None
    if tipo == 'conquista' and game_id_str:
        game_id = int(game_id_str)
        if not JogoMonitorado.query.get(game_id):
            dados_jogo = buscar_dados_jogo(game_id)
            novo_jogo = JogoMonitorado(
                id=game_id,
                titulo=dados_jogo['titulo'],
                icone=dados_jogo['icone'],
                url_ticket=dados_jogo['url_ticket'],
                qtd_tickets_set=buscar_tickets_abertos_set(game_id),
                atualizado_em=datetime.utcnow(),
            )
            db.session.add(novo_jogo)
            db.session.commit()

    for string_id in ids:
        try:
            num_id = int(string_id)
        except (ValueError, TypeError):
            continue

        if tipo == 'jogo':
            if not JogoMonitorado.query.get(num_id):
                dados_j = buscar_dados_jogo(num_id)
                novo_jogo = JogoMonitorado(
                    id=num_id,
                    titulo=dados_j['titulo'],
                    icone=dados_j['icone'],
                    url_ticket=dados_j['url_ticket'],
                    qtd_tickets_set=buscar_tickets_abertos_set(num_id),
                    atualizado_em=datetime.utcnow(),
                )
                db.session.add(novo_jogo)

        elif tipo == 'conquista':
            if not ConquistaMonitorada.query.get(num_id):
                dados_c = buscar_dados_conquista(num_id)
                nova_conquista = ConquistaMonitorada(
                    id=num_id,
                    titulo=dados_c['titulo'],
                    qtd_tickets=dados_c['tickets'],
                    icone=dados_c['icone'],
                    url_ticket=dados_c['url_ticket'],
                    jogo_id=game_id,
                )
                db.session.add(nova_conquista)

    db.session.commit()
    return jsonify({'status': 'sucesso'})


@app.route('/api/refresh/<int:game_id>', methods=['POST'])
def refresh_set(game_id):
    """Força a atualização do set, ignorando o TTL do cache."""
    jogo = JogoMonitorado.query.get_or_404(game_id)
    jogo.qtd_tickets_set = buscar_tickets_abertos_set(game_id)
    jogo.atualizado_em = datetime.utcnow()

    for conquista in jogo.conquistas:
        dados = buscar_dados_conquista(conquista.id)
        conquista.qtd_tickets = dados['tickets']
        conquista.titulo = dados['titulo']
        if dados['url_ticket']:
            conquista.url_ticket = dados['url_ticket']

    db.session.commit()
    return jsonify({
        'game_id': game_id,
        'qtd_tickets_set': jogo.qtd_tickets_set,
        'atualizado_em': jogo.atualizado_em.isoformat(),
    })

@app.route('/api/tickets/<int:game_id>')
def api_tickets_detalhado(game_id):
    """Breakdown open/resolved/closed para uma tela de detalhes."""
    return jsonify(buscar_tickets_set_detalhado(game_id))

if __name__ == '__main__':
    app.run(debug=True)