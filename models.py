from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class JogoMonitorado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    icone = db.Column(db.String(250), default="")
    url_ticket = db.Column(db.String(250), default="")
    notas = db.Column(db.Text, default="")
    qtd_tickets_set = db.Column(db.Integer, default=0)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(30), default="pendente")
    ultima_manutencao = db.Column(db.DateTime, nullable=True)
    conquista_manutencao_id = db.Column(db.Integer, nullable=True)
    nota_conquista_manutencao = db.Column(db.Text, default="")
    
    feito_por_mim = db.Column(db.Boolean, default=False)
    em_revisao = db.Column(db.Boolean, default=False)

    conquistas = db.relationship(
        'ConquistaMonitorada',
        backref='jogo',
        lazy=True,
        cascade="all, delete-orphan",
    )

class ConquistaMonitorada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jogo_id = db.Column(db.Integer, db.ForeignKey('jogo_monitorado.id'), nullable=True)
    titulo = db.Column(db.String(150), nullable=False)
    icone = db.Column(db.String(250), default="")
    url_ticket = db.Column(db.String(250), default="")
    notas = db.Column(db.Text, default="")
    qtd_tickets = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default="pendente")
    ultima_manutencao = db.Column(db.DateTime, nullable=True)