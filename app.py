import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for,
)
import requests
from dotenv import load_dotenv
from werkzeug.security import check_password_hash

from models import db, JogoMonitorado, ConquistaMonitorada

# Carrega as credenciais do .env
load_dotenv()
RA_USER = os.getenv('RA_USER')
RA_API_KEY = os.getenv('RA_API_KEY')

# Segurança: senha única de acesso ao app.
# Prefira APP_PASSWORD_HASH (veja o README); APP_PASSWORD (texto puro) também funciona.
APP_PASSWORD_HASH = os.getenv('APP_PASSWORD_HASH')
APP_PASSWORD = os.getenv('APP_PASSWORD')

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print("AVISO: SECRET_KEY não definida no .env. Usando uma chave temporária "
          "(o login será perdido a cada reinício do servidor).")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///monitor.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',  # também protege as rotas POST/DELETE contra CSRF
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') == '1',  # use 1 se estiver em HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

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


def buscar_tickets_set(game_id):
    """Todos os tickets do set.

    A API só devolve os tickets das conquistas oficiais (Core) por padrão;
    os das conquistas não oficiais exigem outra chamada com f=5. O site do RA
    mostra os dois somados, então buscamos os dois.
    """
    tickets = []
    vistos = set()
    for filtro in ('', '&f=5'):
        url = (
            f"https://retroachievements.org/API/API_GetTicketData.php"
            f"?z={RA_USER}&y={RA_API_KEY}&g={game_id}&d=1{filtro}"
        )
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} ao buscar tickets do set {game_id}")
        for t in r.json().get('Tickets', []) or []:
            tid = t.get('ID')
            if tid is not None:
                if tid in vistos:
                    continue
                vistos.add(tid)
            tickets.append(t)
    return tickets


def buscar_tickets_abertos_set(game_id):
    try:
        return sum(1 for t in buscar_tickets_set(game_id) if t.get('ReportState') == 1)
    except Exception as e:
        print(f"Erro ao buscar tickets abertos do set {game_id}: {e}")
        return 0


def buscar_tickets_set_detalhado(game_id):
    contagem = {'open': 0, 'resolved': 0, 'closed': 0, 'total_abertos': 0}
    try:
        for t in buscar_tickets_set(game_id):
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

# ==========================================
# AUTENTICAÇÃO
# ==========================================
MAX_FALHAS_LOGIN = 5
BLOQUEIO_LOGIN_SEG = 300
_falhas_login = {}  # ip -> {'falhas': int, 'bloqueado_ate': float}


def verificar_senha(senha):
    if APP_PASSWORD_HASH:
        return check_password_hash(APP_PASSWORD_HASH, senha)
    if APP_PASSWORD:
        return hmac.compare_digest(APP_PASSWORD.encode(), senha.encode())
    return False


def segundos_bloqueio(ip):
    reg = _falhas_login.get(ip)
    if not reg:
        return 0
    restante = reg['bloqueado_ate'] - time.time()
    if restante <= 0:
        if reg['bloqueado_ate']:
            _falhas_login.pop(ip, None)
        return 0
    return int(restante) + 1


def registrar_falha(ip):
    reg = _falhas_login.setdefault(ip, {'falhas': 0, 'bloqueado_ate': 0})
    reg['falhas'] += 1
    if reg['falhas'] >= MAX_FALHAS_LOGIN:
        reg['bloqueado_ate'] = time.time() + BLOQUEIO_LOGIN_SEG
        reg['falhas'] = 0


def destino_seguro(destino):
    # Só aceita caminhos internos (evita open redirect)
    if destino and destino.startswith('/') and not destino.startswith('//'):
        return destino
    return url_for('dashboard')


@app.before_request
def exigir_login():
    if request.endpoint in (None, 'login', 'static'):
        return None
    if session.get('autenticado'):
        return None
    if request.path.startswith('/api/'):
        return jsonify({'erro': 'Não autenticado'}), 401
    destino = request.full_path.rstrip('?')
    return redirect(url_for('login', next=destino))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('autenticado'):
        return redirect(url_for('dashboard'))

    if not (APP_PASSWORD_HASH or APP_PASSWORD):
        return render_template(
            'login.html',
            erro='Nenhuma senha configurada. Defina APP_PASSWORD_HASH no arquivo .env.',
        ), 503

    erro = None
    status = 200
    if request.method == 'POST':
        ip = request.remote_addr or 'desconhecido'
        espera = segundos_bloqueio(ip)
        if espera:
            erro = f'Muitas tentativas. Tente novamente em {espera // 60 + 1} min.'
            status = 429
        elif verificar_senha(request.form.get('senha', '')):
            _falhas_login.pop(ip, None)
            session.clear()
            session['autenticado'] = True
            session.permanent = True
            return redirect(destino_seguro(request.args.get('next')))
        else:
            registrar_falha(ip)
            erro = 'Senha incorreta.'
            status = 401
    return render_template('login.html', erro=erro), status


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))


# ==========================================
# DASHBOARD
# ==========================================
STATUS_VALIDOS = ('pendente', 'concluido', 'em_manutencao', 'nao_publicado')


@app.route('/')
def dashboard():
    ordem = request.args.get('ordem', 'tickets')
    filtro_tag = request.args.get('tag', 'todas') # todas | meu | revisao
    filtro_status = request.args.get('status', 'todos') # todos | pendente | concluido | em_manutencao | nao_publicado
    if filtro_status not in STATUS_VALIDOS:
        filtro_status = 'todos'

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

    # APLICA FILTRO DE STATUS
    if filtro_status != 'todos':
        jogos = [j for j in jogos if (j.status or 'pendente') == filtro_status]

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

    return render_template(
        'dashboard.html',
        jogos=jogos,
        ordem=ordem,
        filtro_tag=filtro_tag,
        filtro_status=filtro_status,
        ra_user=RA_USER,
    )

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
    # O debugger do Flask permite executar código no servidor: só ligue localmente (FLASK_DEBUG=1).
    app.run(debug=os.getenv('FLASK_DEBUG', '0') == '1')