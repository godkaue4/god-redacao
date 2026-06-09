import json
import bcrypt
from flask_migrate import Migrate
import os
import re
from werkzeug.utils import secure_filename
from functools import wraps
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask import render_template, request,jsonify
from flask import Flask
from flask_admin import Admin, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask import redirect, url_for
from microsaas.BD import db
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from microsaas.models import Usuarios,Redacao,Pagamento
from datetime import datetime,timedelta 
import google.generativeai as genai
from flask_wtf.csrf import CSRFProtect
from flask_limiter.util import get_remote_address
load_dotenv()
Key = os.getenv('API_KEY')
genai.configure(api_key=Key)
model=genai.GenerativeModel("gemini-3.1-flash-lite-preview",
                            generation_config={
                                "temperature": 0.2,
                                "top_p": 1,
                                "max_output_tokens": 2048
                            })
app= Flask(__name__)
app.secret_key=os.getenv("SECRET_KEY")
csrf = CSRFProtect(app)
limiter = Limiter(
                  key_func=get_remote_address,
                  app=app
                  )
lm=LoginManager(app)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'sqlite:///users.db'
)

db.init_app(app)
migrate=Migrate(app,db)
lm.login_view='login'

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'comprovantes')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB máximo

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
print(os.getenv('DATABASE_URL'))
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@lm.user_loader
def user_loader(id):
    usuario=db.session.query(Usuarios).filter_by(id=id).first()
    return usuario
def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return "Acesso negado", 403
        return func(*args, **kwargs)
    return wrapper

class AdminModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
 
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))
 
 
class DashboardView(BaseView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
 
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))
 
    @expose('/')
    def index(self):
        hoje = datetime.utcnow()
        semana_passada = hoje - timedelta(days=7)
 
        labels_dias = []
        dados_dias = []
        for i in range(6, -1, -1):
            dia = hoje - timedelta(days=i)
            inicio = dia.replace(hour=0, minute=0, second=0, microsecond=0)
            fim = dia.replace(hour=23, minute=59, second=59, microsecond=999999)
            count = Redacao.query.filter(
                Redacao.criada_em >= inicio,
                Redacao.criada_em <= fim
            ).count()
            labels_dias.append(dia.strftime('%d/%m'))
            dados_dias.append(count)
 
        stats = {
            'total_usuarios': Usuarios.query.count(),
            'total_redacoes': Redacao.query.count(),
            'usuarios_premium': Usuarios.query.filter_by(premium=True).count(),
            'redacoes_semana': Redacao.query.filter(Redacao.criada_em >= semana_passada).count(),
            'media_notas': db.session.query(db.func.avg(Redacao.nota)).scalar() or 0,
            'pagamentos': Pagamento.query.order_by(Pagamento.criado_em.desc()).limit(5).all(),
            'ultimos_usuarios': Usuarios.query.order_by(Usuarios.id.desc()).limit(5).all(),
            'labels_dias': labels_dias,
            'dados_dias': dados_dias,
        }
        return self.render('admin/dashboard.html', **stats)
 
 
class UsuarioAdminView(AdminModelView):
    column_list = ('id', 'username', 'email', 'premium', 'correcoes', 'is_admin', 'criado_em')
    column_searchable_list = ('username', 'email')
    column_filters = ('premium', 'is_admin')
    form_excluded_columns = ('senha',)
    column_labels = {
        'username': 'Usuário',
        'premium': 'Premium',
        'correcoes': 'Correções',
        'is_admin': 'Admin',
        'criado_em': 'Cadastro'
    }
 
 
class RedacaoAdminView(AdminModelView):
    
    column_list = ('id', 'tema', 'nota', 'usuario_id', 'criada_em')
    column_searchable_list = ('tema',)
    column_filters = ('nota',)
    can_create = False
    can_edit = False
    column_labels = {'criada_em': 'Data', 'usuario_id': 'Usuário ID'}
 
 
class PagamentoAdminView(AdminModelView):
    column_list = ('id', 'usuario_nome', 'usuario_id', 'valor', 'status', 'metodo', 'criado_em')
    column_filters = ('status', 'metodo')
    can_create = False
    can_edit = False
    column_labels = {
        'usuario_nome': 'Nome',
        'usuario_id': 'ID',
        'criado_em': 'Data'
    }
 
 
admin = Admin(
    app,
    name='CorretorENEM',
    index_view=DashboardView(name='Dashboard', url='/admin', endpoint='admin_dashboard')
)
admin.add_view(UsuarioAdminView(Usuarios, db.session, name='Usuários',   endpoint='usuarioadminview'))
admin.add_view(RedacaoAdminView(Redacao,  db.session, name='Redações',   endpoint='redacaoadminview'))
admin.add_view(PagamentoAdminView(Pagamento, db.session, name='Pagamentos', endpoint='pagamentoadminview'))
 
csrf.exempt(admin.name)

@app.route('/admin/usuarios-lista')
@admin_required
def admin_usuarios():
    usuarios = Usuarios.query.order_by(Usuarios.id.desc()).all()
    total_usuarios = Usuarios.query.count()
    usuarios_premium = Usuarios.query.filter_by(premium=True).count()
    return render_template('admin/usuarios.html',
                           usuarios=usuarios,
                           total_usuarios=total_usuarios,
                           usuarios_premium=usuarios_premium)
 
 
@app.route('/admin/editar_usuario', methods=['POST'])
@csrf.exempt
@admin_required
def admin_editar_usuario():
    uid = request.form.get('usuario_id')
    user = Usuarios.query.get_or_404(uid)
    user.email = request.form.get('email', user.email)
    user.premium = request.form.get('premium') == 'true'
    user.is_admin = request.form.get('is_admin') == 'true'
    db.session.commit()
    #flash('Usuário atualizado com sucesso.', 'success')
    return redirect(url_for('admin_usuarios'))
 
 
@app.route('/admin/deletar_usuario/<int:id>', methods=['POST'])
@admin_required
def admin_deletar_usuario(id):
    user = Usuarios.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    #flash('Usuário deletado.', 'success')
    return redirect(url_for('admin_usuarios'))
@app.route('/admin/redacoes-lista')
@admin_required
def admin_redacoes():
    from models import Redacao
    redacoes = Redacao.query.order_by(Redacao.criada_em.desc()).all()
    total_redacoes = Redacao.query.count()
    return render_template('admin/redacoes.html', redacoes=redacoes, total_redacoes=total_redacoes)

@app.route('/admin/ver_comprovante/<nome_arquivo>')
@admin_required
def ver_comprovante(nome_arquivo):
    return redirect(url_for('static', filename=f'comprovantes/{nome_arquivo}'))
@app.route('/admin/aprovar_pagamento/<int:id>', methods=['POST'])
@admin_required
@csrf.exempt
def admin_aprovar_pagamento(id):
    pagamento=Pagamento.query.get_or_404(id)
    pagamento.status='aprovado'
    pagamento.aprovado_em=datetime.utcnow()
    pagamento.aprovado_por=current_user.id
    
    usuario=Usuarios.query.get(pagamento.usuario_id)
    if usuario:
        usuario.premium=True
    db.session.commit()
    return redirect(url_for('admin_usuarios'))
@app.route('/admin/rejeitar_pagamento/<int:id>', methods=['POST'])
@admin_required
@csrf.exempt
def admin_rejeitar_pagamentos(id):
    pagamento=Pagamento.query.get_or_404(id)
    pagamento.status='rejeitado'
    db.session.commit()
    return redirect(url_for('admin_usuarios'))
@app.route('/admin/pagamentos-lista')
@admin_required
def admin_pagamentos():
    pagamentos = Pagamento.query.order_by(Pagamento.criado_em.desc()).all()
    total=len(pagamentos)
    aprovados=Pagamento.query.filter_by(status='aprovado').count()
    rejeitados=Pagamento.query.filter_by(status='rejeitado').count()
    pendentes=Pagamento.query.filter_by(status='pendente').count()
    return render_template('admin/pagamentos.html', pagamentos=pagamentos, total=total, aprovados=aprovados, rejeitados=rejeitados, pendentes=pendentes)
def organizar_resposta(resposta):
    partes = {
        'nota': '',
        'competencias': [],
        'erros': [],
        'sugestoes': []
    }

    linhas = resposta.split('\n')
    secao = None

    for linha in linhas:
        linha_limpa = linha.strip().lower()

        # detectar seções (mais flexível)
        if "nota geral" in linha_limpa:
            partes['nota'] = linha.split(':')[-1].strip()
            continue

        elif "compet" in linha_limpa:
            secao = 'competencias'
            continue

        elif "erro" in linha_limpa:
            secao = 'erros'
            continue

        elif "sugest" in linha_limpa:
            secao = 'sugestoes'
            continue

        # adicionar conteúdo
        if linha.strip():
            if secao == 'competencias':
                partes['competencias'].append(linha.strip())

            elif secao == 'erros':
                partes['erros'].append(linha.strip())

            elif secao == 'sugestoes':
                partes['sugestoes'].append(linha.strip())

    return partes

def corrigir_redacao(texto,tema):
    prompt = f"""
Você é um corretor especialista do ENEM e também um professor.

Analise profundamente a redação.

⚠️ Seja exigente, mas didático.

RETORNE APENAS JSON VÁLIDO:

{{
  "nota": 0,
  "competencias": [
    {{
      "nome": "C1 - Norma culta",
      "nota": 0,
      "analise": "explicação detalhada"
    }},
    {{
      "nome": "C2 - Tema",
      "nota": 0,
      "analise": "explicação"
    }},
    {{
      "nome": "C3 - Argumentação",
      "nota": 0,
      "analise": "explicação"
    }},
    {{
      "nome": "C4 - Coesão",
      "nota": 0,
      "analise": "explicação"
    }},
    {{
      "nome": "C5 - Intervenção",
      "nota": 0,
      "analise": "explicação"
    }}
  ],
  "erros": [
    {{
      "trecho": "parte do texto",
      "explicacao": "erro explicado",
      "correcao": "forma correta"
    }}
  ],
  "sugestoes": [
    {{
      "titulo": "Melhore sua introdução",
      "descricao": "como melhorar",
      "exemplo": "exemplo prático",
      
    }}
  ],
  "repertorio": [
    "filme/livro/dado que pode usar",
    "outro repertório relevante"
  ],
  "modelo_nota_1000": "reescreva um parágrafo melhorado da redação"
}}

REGRAS:
- analise a redação corretamente e aos poucos para evitar erros
- ignore a quantia de linhas se for acima de 15 pois a redação pode ser grande no caderno mas curta no input 
- Nota total = soma das competências
- NÃO invente coisas fora do texto
- ignore erros de espaços pequenos no meio do texto entre palavras ou vírgulas,mas corrija erros gritantes de ortografia e gramática
- Seja específico
- de o valor correto para cada competência sem erros, se a redação tiver um bom repertório mas uma argumentação fraca, a competência de repertório deve ser alta e a de argumentação baixa
- dê notas baixas para redações que não cumprem o tema mesmo que tenham uma boa escrita, e explique isso na análise da competência 2
- seja rigido mas nao ao extremo 
- ignore o tamanho do texto ,pois o modelo pode analisar textos grandes mesmo que o input seja pequeno,então analise o texto como um todo e não se prenda ao tamanho do input ou a quantia de caracteres ou linhas
- analise corretamente antes de da a nota das competencias e de as notas corretamente sem nenhum erro literalmente nenhum nas notas das 5 competencias 
- analise paragrafo por paragrafo linha por linha para dar a nota nas competências corretamente
- Dê exemplos reais
- de 3 ou mais sugestões práticas de melhorias 
- de 3 ou mais repertórios relacionados ao tema
- de 3 ou mias erros específicos encontrados no texto
- podem ser mais que 3 mas não menos que 3,nas sugestões,erros e repertório
- no modelo nota 1000 diga se o parágrafo é de introdução,desenvolvimento ou conclusão
- nas competências, explique detalhadamente o motivo da nota dada, citando trechos específicos do texto para justificar a avaliação

Redação:
{tema}
{texto}
"""
    for _ in range(2):  # tenta 2 vezes
        resposta = model.generate_content(prompt)
        try:
            dados = json.loads(resposta.text)
            if validar_schema(dados):
                 return dados
        except:
            continue

    return {"erro": "Falha ao gerar correção válida"}

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
@app.errorhandler(404)
def pagina_nao_encontrada(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def erro_interno(e):
    return render_template('500.html'), 500

@app.route('/enviar_comprovante', methods=['GET', 'POST'])
@login_required
def enviar_comprovante():
    if request.method == 'POST':
        arquivo = request.files.get('comprovante')

        if not arquivo or arquivo.filename == '':
            return render_template('comprovante.html', erro='Selecione um arquivo')

        if not allowed_file(arquivo.filename):
            return render_template('comprovante.html', erro='Apenas PNG, JPG ou PDF são aceitos')

        # verifica se já tem pagamento pendente
        pendente = Pagamento.query.filter_by(
            usuario_id=current_user.id,
            status='pendente'
        ).first()
        if pendente:
            return render_template('comprovante.html', erro='Você já tem um pagamento aguardando aprovação')

        # salva o arquivo com nome seguro
        extensao = arquivo.filename.rsplit('.', 1)[1].lower()
        nome_arquivo = secure_filename(f"comprovante_{current_user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{extensao}")
        caminho = os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo)
        arquivo.save(caminho)

        novo = Pagamento(
            usuario_id=current_user.id,
            usuario_nome=current_user.username,
            valor=5.90,
            status='pendente',
            metodo='pix',
            comprovante=nome_arquivo  # salva o nome do arquivo
        )
        db.session.add(novo)
        db.session.commit()

        return render_template('comprovante.html', sucesso=True)

    return render_template('comprovante.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('homepage'))
@app.route('/api/corretor', methods=['POST'])
@login_required
@limiter.limit("3 per month", error_message="Limite de correções atingido. Faça upgrade para premium ou aguarde o próximo mês.")
@csrf.exempt
def api_corretor():
    user = db.session.get(Usuarios, current_user.id)
    if not user.premium and user.correcoes >= 3:
            return jsonify({'erro': 'limite atingido',
                            'upgrade': True}), 403

    data = request.get_json() or {}
    texto = data.get('texto', '').strip()
    tema=data.get('tema','').strip()
    if not user.premium:
        pass
    
    if not texto:
        return jsonify({'erro': 'Texto é obrigatório'}), 400

    if len(texto) < 100:
        return jsonify({'erro': 'Redação muito curta'}), 400

    if len(texto) > 5000:
        return jsonify({'erro': 'Texto muito longo'}), 400

    dados = corrigir_redacao(texto,tema)
    if not user.premium:
        user.correcoes += 1
    if not validar_schema(dados):
        return jsonify({"erro":"resposta invalida na IA"}),500
    
    if not user.premium:
        dados.pop('repertorio', None)
        dados.pop('modelo_nota_1000', None)
        
    
    novo=Redacao(
        texto=texto,
        tema=tema,
        nota=int(dados.get('nota',0)),
        competencias=json.dumps(dados.get("competencias")),
        erros=json.dumps(dados.get("erros",[])),
        sugestoes=json.dumps(dados.get("sugestoes",[])),
        usuario_id=current_user.id)
    db.session.add(novo)
    db.session.commit()
    return jsonify(dados)

def validar_schema(dados):
    try:
        assert isinstance(dados, dict)

        # campos obrigatórios
        campos = ["nota", "competencias", "erros", "sugestoes", "repertorio", "modelo_nota_1000"]
        for c in campos:
            assert c in dados

        assert isinstance(dados["nota"], int)
        assert 0 <= dados["nota"] <= 1000

        # competências
        assert len(dados["competencias"]) == 5

        for c in dados["competencias"]:
            assert isinstance(c, dict)
            assert "nome" in c and "nota" in c and "analise" in c

            assert isinstance(c["nome"], str)
            assert isinstance(c["nota"], int)
            assert isinstance(c["analise"], str)

            assert 0 <= c["nota"] <= 200

        # erros
        for e in dados["erros"]:
            assert "trecho" in e
            assert "explicacao" in e
            assert "correcao" in e

        # sugestões
        for s in dados["sugestoes"]:
            assert "titulo" in s
            assert "descricao" in s
            assert "exemplo" in s
        # repertório
        assert isinstance(dados["repertorio"], list)

        # modelo
        assert isinstance(dados["modelo_nota_1000"], str)

        # validar soma da nota
        soma = sum(c["nota"] for c in dados["competencias"])
        dados["nota"] = soma  # força consistência

        return True

    except Exception as e:
        print("Erro de validação:", e)
        return False

@app.route('/')
def homepage():
    return render_template('home page.html',usuario=current_user.username if current_user.is_authenticated else"")
def gerar_tema():
    prompt = """
Você é um elaborador oficial de temas do ENEM.

Crie uma proposta COMPLETA e REALISTA no estilo do INEP.

Retorne APENAS JSON VÁLIDO:

{
  "titulo": "",
  "textos": [
    "",
    "",
    ""
  ],
  "proposta": ""
}

REGRAS:

- O tema deve ser social, filosófico, político ou tecnológico
- Deve parecer um tema REAL do ENEM
- Os textos motivadores devem:
  - ter dados
  - contextualização
  - opiniões diferentes
  - linguagem formal
- A proposta deve seguir o estilo oficial do ENEM
- NÃO use markdown
- NÃO explique nada fora do JSON
- Gere textos longos e ricos
- Não repita temas famosos do ENEM
"""

    resposta = model.generate_content(prompt)

    try:
        return json.loads(resposta.text)

    except:
        return {
            "titulo":"Erro ao gerar tema",
            "textos":[],
            "proposta":""
        }
@app.route('/api/gerar_tema', methods=["GET"])
@login_required
def gerar():
    user= db.session.get(Usuarios, current_user.id)
    if not user.premium:
        return jsonify({'erro': 'Apenas para usuários premium'}), 403
    
    return jsonify(gerar_tema())
@app.route('/corretor')
@login_required
def corretor():
    return render_template('corretor.html',corrigido=None,premium=current_user.premium,tema='',texto='',erros=[],sugestoes=[],repertorio=[],competencias=[],usuario=current_user.username if current_user.is_authenticated else 'visitante')
@app.route("/dashboard")
@login_required
def dashboard():
    
    if current_user.premium:
        redacoes = Redacao.query.filter_by(usuario_id=current_user.id).all()
    else:
        # free só vê as últimas 3
        redacoes = Redacao.query.filter_by(
            usuario_id=current_user.id
        ).order_by(Redacao.criada_em.desc()).limit(3).all()
  
    for r in redacoes:
        r.erros=json.loads(r.erros) if r.erros else[]
        r.sugestoes=json.loads(r.sugestoes) if r.sugestoes else[]
        r.competencias=json.loads(r.competencias) if r.competencias else[]  
    redacoes_json=[
        {"nota":r.nota}
        for r in redacoes
    ]
    
    total=len(redacoes)
    media=round(sum(r.nota for r in redacoes) / total,1 ) if total> 0 else 0
    melhor= max([r.nota for r in redacoes],default=0)
    restante=max(0,3 - current_user.correcoes)
    return render_template("dashboard.html",redacoes=redacoes,
                           total=total,
                           media=media,
                           melhor=melhor,
                           redacoes_json=redacoes_json,
                           restantes=restante,
                           usuario=current_user.username if current_user.is_authenticated else"",
                           premium=current_user.premium)

@app.route('/premium')
@login_required
def premium():
    return render_template('premium.html',usuario=current_user.username if current_user.is_authenticated else"")


@app.route('/deletar_redacao/<int:id>',methods=["POST"])
@login_required
def deletar(id):
    redacao=Redacao.query.get_or_404(id)
    
    if redacao.usuario_id != current_user.id:
        return "acesso negado",403
    db.session.delete(redacao)
    db.session.commit()
    
    return redirect(url_for("dashboard"))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        
        usuario = request.form.get('usuario','').strip()
        
        senha= request.form.get('senha','')
        
        user=db.session.query(Usuarios).filter_by(username=usuario).first()
        
        erro=verificaçoeslogin(usuario,senha)
        if erro:
            return render_template('login.html',erro=erro)
        if not user:
            return render_template('login.html',erro='Usuário não encontrado')
        login_user(user)        
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/cadastrar',methods=['GET','POST'])
@limiter.limit("10 per minute")        
def cadastrar():
    
    if request.method=='POST':
        gmail=request.form['emailform']
        user=request.form.get('usuarioform','').strip()
        key=request.form.get('senhaform','')
        confirmar=request.form['confirmarsenhaform']
        hashsenha=bcrypt.hashpw(key.encode('utf-8'), bcrypt.gensalt())
        
        erro=verificaçoes(gmail,user,key,confirmar)
        if erro:
            return render_template('cadastro.html',erro=erro)
    
        novo_usuario=Usuarios(email=gmail,username=user,senha=hashsenha)
        db.session.add(novo_usuario)
        db.session.commit()
        login_user(novo_usuario)
        return redirect(url_for('dashboard'))
    return render_template('cadastro.html')

def verificaçoeslogin(user,key):
    
    if not user or not key:
        return 'Preencha todos os campos'
    user_db=db.session.query(Usuarios).filter_by(username=user).first()
    
    if not user_db:
        return 'digite o nome de usuario correto '    
    
    if not bcrypt.checkpw(key.encode('utf-8'),user_db.senha):
        return 'Usuário ou senha inválidos'
def verificaçoes(gmail,user,key,confirmar):
    if db.session.query(Usuarios).filter_by(username=user).first():
        return 'Usuário indisponível'
    if key != confirmar:
        return 'As senhas não coincidem'
    if not key or not user or not gmail:
        return 'Preencha todos os campos'
    if len(key) < 4:
        return 'A senha deve conter pelo menos 4 caracteres'
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', gmail):
        return 'Email inválido'

    if len(user) <4:
        return 'O nome de usuário deve conter pelo menos 4 caracteres'
    
    if db.session.query(Usuarios).filter_by(email=gmail).first():
        return 'Email indisponível'
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        csrf.init_app(app)
        app.run(debug=True)
