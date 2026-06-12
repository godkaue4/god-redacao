from microsaas.BD import db
from flask_login import UserMixin
from datetime import datetime

class Usuarios(db.Model,UserMixin):
    id=db.Column(db.Integer,primary_key=True)
    is_admin=db.Column(db.Boolean,default=False)
    email=db.Column(db.String(120),unique=True)
    premium=db.Column(db.Boolean,default=False)
    username=db.Column(db.String(80),unique=True)
    senha=db.Column(db.LargeBinary)
    correcoes=db.Column(db.Integer,default=0)
    plano=db.Column(db.String(20), default='free')
    data_assinatura=db.Column(db.DateTime, nullable=True)
    status_pagamento=db.Column(db.String(20), default='ativo')
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    
class Redacao(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    
    texto=db.Column(db.Text,nullable=False)
    nota=db.Column(db.Integer)
    tema=db.Column(db.String(255))
    competencias=db.Column(db.Text)
    erros=db.Column(db.Text)
    sugestoes=db.Column(db.Text)
    criada_em = db.Column(db.DateTime, default=datetime.utcnow)
    usuario_id=db.Column(db.Integer, db.ForeignKey("usuarios.id"))

class Pagamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    usuario_nome = db.Column(db.String(80))
    valor = db.Column(db.Float, default=5.90)
    status = db.Column(db.String(20), default="pendente")
    metodo = db.Column(db.String(20), default="pix")
    comprovante = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    aprovado_em = db.Column(db.DateTime, nullable=True)
    aprovado_por = db.Column(db.Integer, nullable=True)
    observacao = db.Column(db.Text, nullable=True)

class PasswordResetCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    codigo_hash = db.Column(db.String(64), nullable=False)
    expira_em = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    usuario_nome = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    tipo = db.Column(db.String(20), default="feedback")
    mensagem = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="novo")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)