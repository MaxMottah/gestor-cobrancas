from flask import Flask, render_template_string, request, redirect, url_for, jsonify, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import secrets
import requests
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler
from google import genai

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
DB_NAME = "cobrancas.db"

PAINEL_USUARIO = os.environ.get("PAINEL_USUARIO", "serate")
PAINEL_SENHA_HASH = generate_password_hash(os.environ.get("PAINEL_SENHA", "serate123"))

client = genai.Client()
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "serate123")
CHAVE_PIX_OFICIAL = os.environ.get("CHAVE_PIX_OFICIAL", "42.500.008/0001-17")
MODELOS_GEMINI = ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

MENSAGEM_BOAS_VINDAS_SERVICOS = (
    "Olá! Seja bem-vindo(a) à *Serate Serviços* ⚡❄️\n"
    "Trabalhamos com vários serviços para casa, comércio, condomínio e empresa:\n\n"
    "1. ⚡ *Elétrica* (residencial, predial e comercial)\n"
    "2. ❄️ *Refrigeração e Climatização* (ar-condicionado split, piso-teto, cassete, inverter, geladeiras e freezers)\n"
    "3. 🔒 *Segurança Eletrônica* (câmeras, cercas elétricas, portões e fechaduras digitais)\n"
    "4. 🏠 *Automação Residencial* (Alexa, controle pelo celular e fechaduras)\n"
    "5. 📡 *Redes de Internet e Antenas* (cabeamento, rack, patch panel e antenas coletivas)\n"
    "6. 📞 *Interfonia e Telefonia*\n"
    "7. 🔔 *Alarmes e Sistemas de Incêndio*\n"
    "8. ⚙️ *Automação Industrial, Bombas e Quadros de Comando*\n"
    "9. 🔌 *SPDA, Aterramento, Geradores, Transformadores e Subestações*\n"
    "10. 🛠️ *Outros Serviços* (solda, grades, hidráulica e reparos gerais)\n\n"
    "Olá, estou aqui pra te ajudar! O que você precisa hoje?"
)

SERVICOS_INICIAIS = [
    (
        "Elétrica Residencial, Predial e Comercial",
        "dia_a_dia",
        "eletrica, tomada, interruptor, chuveiro, iluminacao, fiao, fio, disjuntor, curto, energia, solar, 1, eletrico",
        "Fazemos desde tomadas, interruptores, chuveiros e iluminação até instalações elétricas completas e energia solar. Avaliamos a carga, a bitola dos cabos e o trajeto para evitar aquecimento ou queda de tensão.",
        "É para casa, comércio ou condomínio/prédio? Se for condomínio ou prédio, qual o bloco? Quer com material ou só a mão de obra/instalação (se quiser só instalar, passamos o que precisa para você comprar)?"
    ),
    (
        "Quadros de Distribuição e Comandos",
        "dia_a_dia",
        "quadro, disjuntor, dr, dps, barramento, comando, 6, desarmando, esquentando",
        "Montamos, organizamos e fazemos manutenção em quadros de distribuição e comandos, com separação de circuitos, proteções (DR/DPS) e testes de funcionamento.",
        "É montagem nova, organização ou troca/ajuste de disjuntores? Quer com material ou só a instalação/mão de obra?"
    ),
    (
        "Refrigeração e Ar-Condicionado",
        "dia_a_dia",
        "ar-condicionado, ar condicionado, split, piso teto, cassete, inverter, refrigeracao, geladeira, freezer, dreno, pingando, btu, 2",
        "Trabalhamos com instalação, manutenção e limpeza de split, piso-teto, cassete e centrais, além de geladeiras, freezers, dreno/tubulação e reparo de placas (incluindo linha inverter). Na instalação de ar-condicionado, a referência normal de mão de obra é R$ 350 e o material até 3 metros fica em R$ 750 (sujeito a confirmação conforme a distância e o local).",
        "Quantos BTUs e é para casa, apartamento ou condomínio (se for condomínio, qual o bloco)? Quer com material ou só a instalação/mão de obra?"
    ),
    (
        "Segurança Eletrônica e Controle de Acesso",
        "dia_a_dia",
        "camera, cftv, cerca eletrica, cerca, portao, fechadura digital, fechadura, biometria, senha, alexa fechadura, 3",
        "Instalamos e configuramos câmeras, cercas elétricas, fechaduras digitais e portões automatizados. Ajustamos posicionamento, cabeamento ou rede, travamento e testes de operação.",
        "Qual item você precisa (câmera, cerca elétrica, fechadura digital ou portão)? Quer com material ou só a instalação/mão de obra?"
    ),
    (
        "Automação Residencial",
        "dia_a_dia",
        "automacao residencial, alexa, celular, app, casa inteligente, tomada inteligente, luzes, 4",
        "Integramos iluminação, tomadas, climatização e dispositivos ao celular e à Alexa. Configuramos os módulos na rede e criamos comandos e rotinas simples para o dia a dia.",
        "O que você quer automatizar (luzes, tomadas, ar, portão etc.)? Quer com material/dispositivos ou só a instalação e configuração?"
    ),
    (
        "Redes de Internet, Cabeamento e Antenas",
        "dia_a_dia",
        "rede, internet, cabo de rede, rack, patch panel, switch, antena, antena coletiva, sinal, tv, 5",
        "Montamos e organizamos infraestrutura de rede (rack, patch panel, cabeamento e pontos de dados) e antenas coletivas. Organizamos os cabos, identificamos conexões e testamos o sinal ou a rede.",
        "É rede de internet/cabeamento ou antena coletiva? Quer com material ou só a mão de obra/instalação?"
    ),
    (
        "Interfonia e Telefonia",
        "dia_a_dia",
        "interfone, telefonia, ramal, porteiro eletronico, rele, portao interfone, 7",
        "Instalamos, ajustamos e fazemos manutenção em interfones individuais ou coletivos, telefonia/ramais e acionamento de portão. Revisamos fiação, áudio, fonte e relés.",
        "É interfone individual, coletivo ou telefonia/ramal? Se for prédio/condomínio, qual o bloco e qual o problema ou necessidade?"
    ),
    (
        "Alarmes e Sistemas de Incêndio",
        "pesado_industrial",
        "incendio, alarme de incendio, bomba de incendio, central de incendio, acionador, 8",
        "Fazemos revisão, manutenção e diagnóstico em sistemas de alarme e bombas/acionamentos ligados a incêndio, testando laços, sinalização e funcionamento.",
        "Qual é o tipo de prédio ou empresa, qual bloco (se houver) e qual a falha ou revisão necessária no sistema?"
    ),
    (
        "Automação Industrial, Bombas e Quadros",
        "pesado_industrial",
        "automacao industrial, bomba, bombas, clp, ihm, comando industrial, painel, 5, 8",
        "Fazemos automação de bombas, sistemas prediais/industriais e quadros de comando sob medida. Levantamos como o processo opera hoje, montamos a lógica de controle e testamos proteções e acionamentos.",
        "É automação de bomba, quadro de comando ou processo/máquina específico? Quer com material ou só a mão de obra/montagem?"
    ),
    (
        "SPDA, Aterramento, Geradores, Transformadores e Subestações",
        "pesado_industrial",
        "spda, aterramento, gerador, geradores, transformador, transformadores, subestacao, subestacoes, 9, 10",
        "Atuamos na execução, revisão e manutenção de aterramento/SPDA, geradores, transformadores e subestações, com inspeção, testes e execução conforme normas (sem emissão de laudo assinado).",
        "Qual equipamento ou sistema precisa de atendimento (gerador, transformador, subestação, SPDA ou aterramento) e é para instalação, manutenção preventiva ou falha?"
    ),
    (
        "Outros Serviços: Solda, Grades, Hidráulica e Reparos Gerais",
        "dia_a_dia",
        "solda, grade, grades, hidraulica, torneira, cano, vazamento, reparo, reparos gerais, 10",
        "Também avaliamos e realizamos serviços de solda, grades, ajustes hidráulicos e reparos gerais. Verificamos o local, o material e o que precisa ser corrigido para alinhar o serviço e o orçamento.",
        "O que exatamente precisa ser feito (solda, grade, hidráulica ou outro reparo)? Quer com material ou só a mão de obra?"
    ),
]


def login_obrigatorio(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        if not session.get("autenticado"):
            if request.path.startswith("/api/"):
                return jsonify({"erro": "nao_autenticado"}), 401
            return redirect(url_for("login", next=request.full_path))
        return funcao(*args, **kwargs)
    return wrapper


def chamar_gemini(prompt):
    ultimo_erro = None
    for modelo in MODELOS_GEMINI:
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=prompt,
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            ultimo_erro = e
            print(f"Aviso modelo {modelo}: {repr(e)}", flush=True)
    raise ultimo_erro if ultimo_erro else RuntimeError("Nenhum modelo Gemini respondeu.")


def criar_tabelas():
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            client_phone TEXT NOT NULL,
            service_desc TEXT NOT NULL,
            amount REAL NOT NULL,
            due_date TEXT NOT NULL,
            pix_key TEXT NOT NULL,
            status TEXT DEFAULT 'pendente',
            ai_message TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            segmento TEXT NOT NULL,
            palavras_chave TEXT NOT NULL,
            como_e_feito TEXT NOT NULL,
            perguntas_graduais TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversas_whatsapp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS atendimento_pausado (
            phone TEXT PRIMARY KEY,
            pausado INTEGER DEFAULT 1,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for item in SERVICOS_INICIAIS:
        cursor.execute("""
            INSERT OR IGNORE INTO catalogo_servicos
            (nome, segmento, palavras_chave, como_e_feito, perguntas_graduais)
            VALUES (?, ?, ?, ?, ?)
        """, item)

    conexao.commit()
    conexao.close()


def definir_pausa_ia(phone, pausado):
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    if pausado:
        cursor.execute("""
            INSERT INTO atendimento_pausado (phone, pausado, atualizado_em)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(phone) DO UPDATE SET pausado = 1, atualizado_em = CURRENT_TIMESTAMP
        """, (phone,))
    else:
        cursor.execute("DELETE FROM atendimento_pausado WHERE phone = ?", (phone,))
    conexao.commit()
    conexao.close()


def ia_esta_pausada(phone):
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("SELECT pausado FROM atendimento_pausado WHERE phone = ?", (phone,))
    row = cursor.fetchone()
    conexao.close()
    return bool(row and row[0] == 1)


def registrar_mensagem_conversa(phone, role, message):
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        INSERT INTO conversas_whatsapp (phone, role, message)
        VALUES (?, ?, ?)
    """, (phone, role, message))
    conexao.commit()
    conexao.close()


def buscar_historico_conversa(phone, limite=40):
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT id, role, message, created_at FROM conversas_whatsapp
        WHERE phone = ?
        ORDER BY id DESC
        LIMIT ?
    """, (phone, limite))
    linhas = cursor.fetchall()
    conexao.close()
    return list(reversed(linhas))


def listar_contatos_conversa():
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT c.phone, c.message, c.role, c.created_at,
               CASE WHEN p.pausado = 1 THEN 1 ELSE 0 END AS pausado,
               c.id AS ultimo_id
        FROM conversas_whatsapp c
        INNER JOIN (
            SELECT phone, MAX(id) AS max_id
            FROM conversas_whatsapp
            GROUP BY phone
        ) ult ON c.id = ult.max_id
        LEFT JOIN atendimento_pausado p ON c.phone = p.phone
        ORDER BY c.id DESC
    """)
    contatos = cursor.fetchall()
    conexao.close()
    return contatos


def resumir_dados_ja_informados(historico_anterior, msg_atual):
    """Identifica o que já foi dito na conversa para evitar repetir perguntas ou prolongar."""
    falas_cliente = " ".join(
        [m for _, r, m, *_ in historico_anterior if r == "cliente"] + [msg_atual]
    ).lower()

    ja_tem = []
    falta_avaliar = []

    if any(k in falas_cliente for k in ["instal", "manutenc", "limpeza", "consert", "repar", "troc", "mont", "alarme", "camera", "cerca", "interfone", "fechadura", "portao", "quadro", "gerador", "subestac", "solar", "rede", "solda", "grade", "hidraulic"]):
        ja_tem.append("o que precisa ser feito")
    else:
        falta_avaliar.append("o que precisa ser feito")

    if any(k in falas_cliente for k in ["com material", "sem material", "so mao de obra", "só mão de obra", "so instala", "só instala", "eu compro", "cliente compra", "vc tras", "você traz", "traz material", "kit", "nao tenho material", "não tenho material"]):
        ja_tem.append("se quer com material ou só instalação/mão de obra")
    else:
        falta_avaliar.append("se quer com material ou só a instalação/mão de obra")

    tem_condominio_ou_predio = any(k in falas_cliente for k in ["condominio", "condomínio", "predio", "prédio", "apto", "apartamento", "bloco", "torre"])
    tem_local = tem_condominio_ou_predio or any(k in falas_cliente for k in ["casa", "rua", "av", "avenida", "bairro", "numero", "número", "nº", "n ", "cabanagem", "independencia", "independência", "ananindeua", "belem", "belém"])
    if tem_local:
        ja_tem.append("local/endereço")
    else:
        falta_avaliar.append("local/endereço")

    if tem_condominio_ou_predio:
        if any(k in falas_cliente for k in ["bloco", "torre"]):
            ja_tem.append("bloco do condomínio/prédio")
        else:
            falta_avaliar.append("qual o bloco (em condomínios/prédios com vários blocos)")

    if any(k in falas_cliente for k in ["segunda", "terca", "terça", "quarta", "quinta", "sexta", "sabado", "sábado", "domingo", "manha", "manhã", "tarde", "noite", "hoje", "amanha", "amanhã", "dia "]):
        ja_tem.append("dia/período")
    else:
        falta_avaliar.append("dia/período de preferência")

    return ja_tem, falta_avaliar


def buscar_servicos_relevantes(texto_usuario):
    texto_limpo = (texto_usuario or "").lower()
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("SELECT nome, segmento, palavras_chave, como_e_feito, perguntas_graduais FROM catalogo_servicos")
    todos = cursor.fetchall()
    conexao.close()

    encontrados = []
    for nome, segmento, palavras_chave, como_e_feito, perguntas_graduais in todos:
        palavras = [p.strip().lower() for p in palavras_chave.split(",") if p.strip()]
        if any(p in texto_limpo for p in palavras):
            encontrados.append({
                "nome": nome,
                "segmento": segmento,
                "como_e_feito": como_e_feito,
                "perguntas_graduais": perguntas_graduais,
            })
    return encontrados


def gerar_mensagem_ia(client_name, service_desc, amount, due_date, pix_key):
    """Gera uma mensagem curta, educada e natural de cobrança com o Gemini."""
    chave = pix_key or CHAVE_PIX_OFICIAL
    prompt = (
        f"Crie uma mensagem curta, educada e natural (no máximo 4 linhas) de cobrança para {client_name}. "
        f"Serviço da Serate Serviços: {service_desc}, valor de R$ {amount:.2f}, vencimento hoje ({due_date}). "
        f"Informe a chave Pix {chave} e peça para enviar o comprovativo após o pagamento. "
        f"Não invente nenhuma outra informação ou chave."
    )
    try:
        return chamar_gemini(prompt)
    except Exception as e:
        print("Erro ao gerar mensagem IA:", repr(e), flush=True)
        return (
            f"Olá, {client_name}! Passando para lembrar da fatura da Serate Serviços "
            f"({service_desc}), no valor de R$ {amount:.2f}, com vencimento hoje ({due_date}).\n"
            f"Chave Pix (CNPJ): {chave}\n"
            f"Assim que pagar, por favor nos mande o comprovativo."
        )


def enviar_whatsapp_api(phone, message):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print("ERRO ENVIO: WHATSAPP_TOKEN ou WHATSAPP_PHONE_ID ausente.", flush=True)
        return False
    url = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message}
    }
    response = requests.post(url, headers=headers, json=payload)
    print("Resposta WhatsApp API:", response.status_code, response.text, flush=True)
    return response.status_code in (200, 201)


def verificar_e_enviar_cobrancas_diarias():
    """Executado automaticamente todos os dias para disparar apenas as faturas que vencem hoje."""
    hoje = date.today().isoformat()
    print(f"[{hoje}] A verificar faturas pendentes para envio automático...", flush=True)

    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("SELECT id, client_name, client_phone, service_desc, amount, due_date, pix_key, ai_message FROM faturas WHERE status = 'pendente' AND due_date = ?", (hoje,))
    faturas_vencendo_hoje = cursor.fetchall()

    for f in faturas_vencendo_hoje:
        fatura_id, client_name, client_phone, service_desc, amount, due_date, pix_key, ai_message = f

        msg = ai_message if ai_message else gerar_mensagem_ia(client_name, service_desc, amount, due_date, pix_key)
        sucesso = enviar_whatsapp_api(client_phone, msg)

        if sucesso:
            cursor.execute("UPDATE faturas SET status = 'enviado' WHERE id = ?", (fatura_id,))
            conexao.commit()
            print(f"Cobrança enviada com sucesso para {client_name}!", flush=True)
        else:
            print(f"Falha ao enviar cobrança para {client_name}.", flush=True)

    conexao.close()


LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Serate Serviços - Login</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; display: flex; align-items: center; justify-content: center; min-height: 100vh; color: #333; box-sizing: border-box; }
        .card { width: 100%; max-width: 380px; background: #fff; padding: 24px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        h2 { margin-top: 0; text-align: center; color: #075e54; }
        label { display: block; font-weight: bold; margin-top: 12px; font-size: 14px; }
        input { width: 100%; padding: 10px; margin-top: 6px; border: 1px solid #ccc; border-radius: 6px; font-size: 15px; box-sizing: border-box; }
        button { width: 100%; padding: 11px; margin-top: 18px; border: none; border-radius: 6px; background: #008069; color: #fff; font-weight: bold; font-size: 16px; cursor: pointer; }
        button:hover { background: #075e54; }
        .erro { background: #fee2e2; color: #991b1b; padding: 10px; border-radius: 6px; font-size: 13px; margin-bottom: 10px; text-align: center; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🔐 Serate Serviços</h2>
        {% if erro %}<div class="erro">{{ erro }}</div>{% endif %}
        <form method="POST">
            <input type="hidden" name="next" value="{{ next_url or '' }}">
            <label>Usuário:</label>
            <input type="text" name="usuario" required autofocus autocomplete="username">

            <label>Senha:</label>
            <input type="password" name="senha" required autocomplete="current-password">

            <button type="submit">Entrar</button>
        </form>
    </div>
</body>
</html>
"""


CHAT_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Serate Serviços - Atendimento WhatsApp</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #e5ddd5; margin: 0; color: #111b21; }
        .topbar { background: #075e54; color: #fff; padding: 12px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
        .topbar-acoes { display: flex; gap: 8px; align-items: center; }
        .topbar a { color: #fff; text-decoration: none; background: rgba(255,255,255,0.16); padding: 7px 12px; border-radius: 6px; font-size: 14px; font-weight: bold; }
        .topbar a.sair { background: rgba(239,68,68,0.85); }
        .wrap { display: flex; height: calc(100vh - 54px); max-width: 1200px; margin: 0 auto; background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,0.12); }
        .sidebar { width: 320px; border-right: 1px solid #d1d7db; display: flex; flex-direction: column; background: #fff; }
        .sidebar-head { padding: 12px; background: #f0f2f5; border-bottom: 1px solid #d1d7db; }
        .sidebar-head input { width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 8px; font-size: 14px; margin-bottom: 8px; }
        .sidebar-head button { width: 100%; padding: 8px; border: none; border-radius: 8px; background: #008069; color: #fff; font-weight: bold; cursor: pointer; font-size: 13px; }
        .contato-lista { overflow-y: auto; flex: 1; }
        .contato-item { display: block; text-decoration: none; color: inherit; padding: 12px 14px; border-bottom: 1px solid #f0f2f5; }
        .contato-item:hover { background: #f5f6f6; }
        .contato-item.ativo { background: #e7f3ef; }
        .contato-top { display: flex; justify-content: space-between; align-items: center; font-weight: bold; font-size: 14px; }
        .contato-previa { font-size: 12px; color: #54656f; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 4px; }
        .badge-pausa { background: #fde68a; color: #92400e; font-size: 11px; padding: 2px 6px; border-radius: 10px; font-weight: bold; }
        .chat-area { flex: 1; display: flex; flex-direction: column; background: #efeae2; }
        .chat-header { padding: 12px 16px; background: #f0f2f5; border-bottom: 1px solid #d1d7db; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
        .chat-mensagens { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
        .bolha { max-width: 72%; padding: 9px 12px; border-radius: 8px; font-size: 14px; line-height: 1.4; white-space: pre-wrap; box-shadow: 0 1px 1px rgba(0,0,0,0.08); }
        .bolha-cliente { align-self: flex-start; background: #fff; }
        .bolha-saida { align-self: flex-end; background: #d9fdd3; }
        .bolha-meta { font-size: 10px; color: #667781; text-align: right; margin-top: 4px; }
        .chat-form { padding: 10px 12px; background: #f0f2f5; display: flex; gap: 8px; border-top: 1px solid #d1d7db; }
        .chat-form input { flex: 1; padding: 10px 12px; border: 1px solid #ccc; border-radius: 8px; font-size: 15px; }
        .chat-form button { padding: 10px 18px; border: none; border-radius: 8px; background: #008069; color: #fff; font-weight: bold; cursor: pointer; }
        .btn-pausa { padding: 6px 10px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 12px; }
        .btn-pausar { background: #f59e0b; color: #fff; }
        .btn-retomar { background: #16a34a; color: #fff; }
        .alerta { background: #fef3c7; color: #92400e; padding: 8px 14px; font-size: 13px; border-bottom: 1px solid #fcd34d; }
        .status-ao-vivo { font-size: 11px; color: #008069; font-weight: bold; }
        @media (max-width: 768px) {
            .wrap { flex-direction: column; height: auto; min-height: calc(100vh - 54px); }
            .sidebar { width: 100%; max-height: 220px; border-right: none; border-bottom: 1px solid #d1d7db; }
            .chat-area { min-height: 420px; }
        }
    </style>
</head>
<body>
    <div class="topbar">
        <strong>💬 Serate Serviços — Painel WhatsApp</strong>
        <div class="topbar-acoes">
            <a href="{{ url_for('index') }}">📋 Cobranças IA</a>
            <a href="{{ url_for('logout') }}" class="sair">Sair</a>
        </div>
    </div>

    {% if aviso %}
    <div class="alerta">{{ aviso }}</div>
    {% endif %}

    <div class="wrap">
        <div class="sidebar">
            <div class="sidebar-head">
                <form method="GET" action="{{ url_for('chat_painel') }}">
                    <input type="text" name="phone" value="{{ phone_ativo or '' }}" placeholder="Número (ex: 5591999998888)">
                    <button type="submit">Abrir / Novo Número</button>
                </form>
            </div>
            <div class="contato-lista" id="lista-contatos">
                {% for c in contatos %}
                <a class="contato-item {% if c[0] == phone_ativo %}ativo{% endif %}" href="{{ url_for('chat_painel', phone=c[0]) }}">
                    <div class="contato-top">
                        <span>{{ c[0] }}</span>
                        {% if c[4] == 1 %}<span class="badge-pausa">IA pausada</span>{% endif %}
                    </div>
                    <div class="contato-previa">{{ 'Você/Serate: ' if c[2] != 'cliente' else '' }}{{ c[1] }}</div>
                </a>
                {% else %}
                <div style="padding: 16px; color: #667781; font-size: 13px;">Nenhuma conversa ainda. Digite um número acima ou aguarde mensagem no WhatsApp.</div>
                {% endfor %}
            </div>
        </div>

        <div class="chat-area">
            {% if phone_ativo %}
            <div class="chat-header">
                <div>
                    <strong>{{ phone_ativo }}</strong> <span class="status-ao-vivo">• Tempo real (4s)</span>
                    <div style="font-size: 12px; color: #54656f;" id="subtitulo-ia">
                        {% if pausado_ativo %}IA pausada neste número (você responde na mão){% else %}IA respondendo automaticamente{% endif %}
                    </div>
                </div>
                <form method="POST" action="{{ url_for('alternar_pausa', phone=phone_ativo) }}" style="margin: 0;">
                    {% if pausado_ativo %}
                    <button type="submit" class="btn-pausa btn-retomar">▶ Reativar IA</button>
                    {% else %}
                    <button type="submit" class="btn-pausa btn-pausar">⏸ Pausar IA</button>
                    {% endif %}
                </form>
            </div>

            <div class="chat-mensagens" id="chat-mensagens">
                {% for msg_id, role, msg, dt in mensagens %}
                <div class="bolha {% if role == 'cliente' %}bolha-cliente{% else %}bolha-saida{% endif %}">
                    <div>{{ msg }}</div>
                    <div class="bolha-meta">{{ 'Cliente' if role == 'cliente' else ('Atendente' if role == 'atendente' else 'IA Serate') }} • {{ dt or '' }}</div>
                </div>
                {% else %}
                <div style="text-align: center; color: #667781; margin-top: 40px; font-size: 14px;">Nenhuma mensagem registrada para este número ainda.</div>
                {% endfor %}
            </div>

            <form class="chat-form" method="POST" action="{{ url_for('enviar_msg_manual') }}">
                <input type="hidden" name="phone" value="{{ phone_ativo }}">
                <input type="text" name="mensagem" required placeholder="Digite sua mensagem para o cliente...">
                <button type="submit">Enviar</button>
            </form>
            {% else %}
            <div style="flex: 1; display: flex; align-items: center; justify-content: center; color: #54656f; padding: 20px; text-align: center;">
                Selecione um número na lista à esquerda ou digite um telefone com DDI + DDD para conversar.
            </div>
            {% endif %}
        </div>
    </div>

    <script>
        (function() {
            const phoneAtivo = {{ (phone_ativo or '') | tojson }};
            const chatBox = document.getElementById("chat-mensagens");
            const listaContatos = document.getElementById("lista-contatos");
            const subtituloIa = document.getElementById("subtitulo-ia");

            let ultimoIdRenderizado = {{ (mensagens[-1][0] if mensagens else 0) | tojson }};
            let ultimoEstadoContatos = "";

            function escaparHtml(texto) {
                const div = document.createElement("div");
                div.textContent = texto || "";
                return div.innerHTML;
            }

            function estaPertoDoFim(el) {
                return !el || (el.scrollHeight - el.scrollTop - el.clientHeight) < 90;
            }

            if (chatBox) {
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function renderizarContatos(contatos) {
                const assinatura = JSON.stringify(contatos);
                if (assinatura === ultimoEstadoContatos || !listaContatos) return;
                ultimoEstadoContatos = assinatura;

                if (!contatos || contatos.length === 0) {
                    listaContatos.innerHTML = '<div style="padding: 16px; color: #667781; font-size: 13px;">Nenhuma conversa ainda. Digite um número acima ou aguarde mensagem no WhatsApp.</div>';
                    return;
                }

                listaContatos.innerHTML = contatos.map(function(c) {
                    const ativo = c.phone === phoneAtivo ? "ativo" : "";
                    const badge = c.pausado ? '<span class="badge-pausa">IA pausada</span>' : "";
                    const prefixo = c.role !== "cliente" ? "Você/Serate: " : "";
                    return (
                        '<a class="contato-item ' + ativo + '" href="/chat?phone=' + encodeURIComponent(c.phone) + '">' +
                            '<div class="contato-top">' +
                                '<span>' + escaparHtml(c.phone) + '</span>' +
                                badge +
                            '</div>' +
                            '<div class="contato-previa">' + escaparHtml(prefixo + c.message) + '</div>' +
                        '</a>'
                    );
                }).join("");
            }

            function renderizarMensagens(mensagens, pausado) {
                if (subtituloIa) {
                    subtituloIa.textContent = pausado
                        ? "IA pausada neste número (você responde na mão)"
                        : "IA respondendo automaticamente";
                }
                if (!chatBox || !mensagens || mensagens.length === 0) return;

                const maiorId = mensagens[mensagens.length - 1].id;
                if (maiorId === ultimoIdRenderizado) return;
                ultimoIdRenderizado = maiorId;

                const colarEmbaixo = estaPertoDoFim(chatBox);
                chatBox.innerHTML = mensagens.map(function(m) {
                    const classeBolha = m.role === "cliente" ? "bolha-cliente" : "bolha-saida";
                    const rotulo = m.role === "cliente"
                        ? "Cliente"
                        : (m.role === "atendente" ? "Atendente" : "IA Serate");
                    const hora = m.created_at ? " • " + m.created_at : "";
                    return (
                        '<div class="bolha ' + classeBolha + '">' +
                            '<div>' + escaparHtml(m.message) + '</div>' +
                            '<div class="bolha-meta">' + rotulo + escaparHtml(hora) + '</div>' +
                        '</div>'
                    );
                }).join("");

                if (colarEmbaixo) {
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
            }

            async function atualizarTempoReal() {
                if (document.hidden) return;
                try {
                    const url = "/api/chat/mensagens" + (phoneAtivo ? ("?phone=" + encodeURIComponent(phoneAtivo)) : "");
                    const resp = await fetch(url, { cache: "no-store" });
                    if (!resp.ok) return;
                    const dados = await resp.json();
                    renderizarContatos(dados.contatos || []);
                    if (phoneAtivo) {
                        renderizarMensagens(dados.mensagens || [], Boolean(dados.pausado));
                    }
                } catch (e) {
                    console.log("Falha ao atualizar chat:", e);
                }
            }

            setInterval(atualizarTempoReal, 4000);
        })();
    </script>
</body>
</html>
"""


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Serate Serviços - Gestor de Cobranças IA</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        .nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; gap: 8px; flex-wrap: wrap; }
        .nav-links { display: flex; gap: 8px; }
        .nav a { text-decoration: none; background: #075e54; color: #fff; padding: 8px 12px; border-radius: 6px; font-size: 14px; font-weight: bold; }
        .nav a.sair { background: #dc2626; }
        h2 { color: #2c3e50; text-align: center; }
        label { font-weight: bold; display: block; margin-top: 10px; font-size: 14px; }
        input, button { width: 100%; padding: 10px; margin-top: 5px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; font-size: 16px; }
        button { background-color: #27ae60; color: white; border: none; font-weight: bold; margin-top: 20px; cursor: pointer; }
        button:hover { background-color: #219653; }
        .btn-danger { background-color: #e74c3c; margin-top: 10px; }
        .card { background: #fff; border-left: 5px solid #3498db; padding: 15px; margin-top: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-radius: 4px; }
        .msg-box { background: #f8f9fa; border: 1px dashed #cbd5e1; padding: 10px; font-size: 13px; margin-top: 8px; border-radius: 4px; white-space: pre-wrap; }
        .status-pendente { color: #e67e22; font-weight: bold; }
        .status-enviado { color: #27ae60; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <strong>Serate Serviços</strong>
            <div class="nav-links">
                <a href="{{ url_for('chat_painel') }}">💬 Chat WhatsApp</a>
                <a href="{{ url_for('logout') }}" class="sair">Sair</a>
            </div>
        </div>
        <h2>🤖 Serate Serviços - Cobranças IA</h2>
        <form method="POST">
            <input type="hidden" name="acao" value="cadastrar">
            <label>Nome do Cliente:</label>
            <input type="text" name="client_name" required placeholder="Ex: Carlos Silva">

            <label>WhatsApp (com DDI e DDD):</label>
            <input type="text" name="client_phone" required placeholder="Ex: 5591999998888">

            <label>Serviço Prestado:</label>
            <input type="text" name="service_desc" required placeholder="Ex: Manutenção de Ar Condicionado">

            <label>Valor (R$):</label>
            <input type="number" step="0.01" name="amount" required placeholder="Ex: 250.00">

            <label>Data de Vencimento:</label>
            <input type="date" name="due_date" required>

            <label>Chave Pix:</label>
            <input type="text" name="pix_key" value="42.500.008/0001-17" required placeholder="Ex: 42.500.008/0001-17">

            <button type="submit">Guardar e Agendar Fatura</button>
        </form>

        <form method="POST" onsubmit="return confirm('Apagar todas as faturas?');">
            <input type="hidden" name="acao" value="apagar_tudo">
            <button type="submit" class="btn-danger">🗑️ Apagar Tudo</button>
        </form>

        <div style="margin-top: 30px;">
            <h3>📋 Faturas Registadas</h3>
            {% for f in faturas %}
            <div class="card">
                <strong>Cliente:</strong> {{ f[1] }}<br>
                <strong>Serviço:</strong> {{ f[2] }} | <strong>Valor:</strong> R$ {{ "%.2f"|format(f[3]) }}<br>
                <strong>Vencimento:</strong> {{ f[4] }} | <strong>Status:</strong> 
                {% if f[5] == 'pendente' %}<span class="status-pendente">Aguardando o Dia do Vencimento</span>
                {% else %}<span class="status-enviado">Enviado com Sucesso</span>{% endif %}<br>
                <div class="msg-box"><b>Mensagem (Gemini):</b><br>{{ f[6] }}</div>
            </div>
            {% else %}
            <p style="text-align: center; color: #777;">Nenhuma fatura registada.</p>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    next_url = request.args.get("next") or request.form.get("next") or ""
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("index")

    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""
        if usuario == PAINEL_USUARIO and check_password_hash(PAINEL_SENHA_HASH, senha):
            session["autenticado"] = True
            return redirect(next_url)
        erro = "Usuário ou senha inválidos."

    return render_template_string(LOGIN_TEMPLATE, erro=erro, next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/chat/mensagens")
@login_obrigatorio
def api_chat_mensagens():
    phone_param = (request.args.get("phone") or "").strip()
    phone_limpo = "".join(ch for ch in phone_param if ch.isdigit())
    contatos_raw = listar_contatos_conversa()
    contatos_json = [
        {
            "phone": c[0],
            "message": c[1],
            "role": c[2],
            "created_at": c[3],
            "pausado": bool(c[4]),
            "ultimo_id": c[5],
        }
        for c in contatos_raw
    ]
    mensagens_raw = buscar_historico_conversa(phone_limpo, limite=40) if phone_limpo else []
    mensagens_json = [
        {
            "id": m[0],
            "role": m[1],
            "message": m[2],
            "created_at": m[3],
        }
        for m in mensagens_raw
    ]
    return jsonify({
        "phone": phone_limpo,
        "pausado": ia_esta_pausada(phone_limpo) if phone_limpo else False,
        "mensagens": mensagens_json,
        "contatos": contatos_json,
    })


@app.route("/chat")
@login_obrigatorio
def chat_painel():
    contatos = listar_contatos_conversa()
    phone_param = (request.args.get("phone") or "").strip()
    phone_limpo = "".join(ch for ch in phone_param if ch.isdigit())
    phone_ativo = phone_limpo or (contatos[0][0] if contatos else None)
    mensagens = buscar_historico_conversa(phone_ativo, limite=40) if phone_ativo else []
    pausado_ativo = ia_esta_pausada(phone_ativo) if phone_ativo else False
    aviso = request.args.get("aviso")

    return render_template_string(
        CHAT_TEMPLATE,
        contatos=contatos,
        phone_ativo=phone_ativo,
        mensagens=mensagens,
        pausado_ativo=pausado_ativo,
        aviso=aviso,
    )


@app.route("/chat/enviar", methods=["POST"])
@login_obrigatorio
def enviar_msg_manual():
    phone = "".join(ch for ch in (request.form.get("phone") or "") if ch.isdigit())
    mensagem = (request.form.get("mensagem") or "").strip()
    if not phone or not mensagem:
        return redirect(url_for("chat_painel", phone=phone, aviso="Informe o número e a mensagem."))

    sucesso = enviar_whatsapp_api(phone, mensagem)
    if sucesso:
        registrar_mensagem_conversa(phone, "atendente", mensagem)
        return redirect(url_for("chat_painel", phone=phone, aviso="Mensagem enviada no WhatsApp!"))
    return redirect(url_for("chat_painel", phone=phone, aviso="Falha ao enviar pela API do WhatsApp. Veja os logs."))


@app.route("/chat/pausa/<phone>", methods=["POST"])
@login_obrigatorio
def alternar_pausa(phone):
    phone_limpo = "".join(ch for ch in phone if ch.isdigit())
    if phone_limpo:
        novo_estado = not ia_esta_pausada(phone_limpo)
        definir_pausa_ia(phone_limpo, novo_estado)
    return redirect(url_for("chat_painel", phone=phone_limpo))


@app.route("/", methods=["GET", "POST"])
@login_obrigatorio
def index():
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()

    if request.method == "POST":
        acao = request.form.get("acao")

        if acao == "cadastrar":
            client_name = request.form["client_name"]
            client_phone = request.form["client_phone"]
            service_desc = request.form["service_desc"]
            amount = float(request.form["amount"])
            due_date = request.form["due_date"]
            pix_key = request.form["pix_key"]

            ai_msg = gerar_mensagem_ia(client_name, service_desc, amount, due_date, pix_key)

            cursor.execute("""
                INSERT INTO faturas (client_name, client_phone, service_desc, amount, due_date, pix_key, status, ai_message)
                VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?)
            """, (client_name, client_phone, service_desc, amount, due_date, pix_key, ai_msg))
            conexao.commit()

        elif acao == "apagar_tudo":
            cursor.execute("DELETE FROM faturas")
            conexao.commit()

        conexao.close()
        return redirect(url_for("index"))

    cursor.execute("SELECT id, client_name, service_desc, amount, due_date, status, ai_message FROM faturas ORDER BY id DESC")
    faturas = cursor.fetchall()
    conexao.close()

    return render_template_string(HTML_TEMPLATE, faturas=faturas)


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    """Webhook para atender clientes no chat de forma natural, direta e sem enrolar."""
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode and token:
            if mode == "subscribe" and token == VERIFY_TOKEN:
                return challenge, 200
            else:
                return "Erro de verificação: Token inválido", 403
        return "Parâmetros em falta", 400

    elif request.method == "POST":
        data = request.json or {}
        print("Payload webhook recebido:", data, flush=True)
        numero_cliente = None
        try:
            changes = data['entry'][0]['changes'][0]['value']
            if 'messages' in changes:
                msg_obj = changes['messages'][0]
                numero_cliente = msg_obj.get('from')
                msg_recebida = (msg_obj.get('text', {}).get('body') or "").strip()
                print(f"Mensagem de {numero_cliente}: {msg_recebida}", flush=True)

                if not numero_cliente or not msg_recebida:
                    print("Mensagem ignorada (sem texto ou remetente).", flush=True)
                    return jsonify({"status": "ignorado"}), 200

                historico_anterior = buscar_historico_conversa(numero_cliente, limite=14)
                registrar_mensagem_conversa(numero_cliente, "cliente", msg_recebida)

                if ia_esta_pausada(numero_cliente):
                    print(f"IA pausada para {numero_cliente}. Aguardando resposta manual em /chat.", flush=True)
                    return jsonify({"status": "pausado"}), 200

                saudacoes_iniciais = {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "oii", "oie"}
                if len(historico_anterior) == 0 and msg_recebida.lower() in saudacoes_iniciais:
                    registrar_mensagem_conversa(numero_cliente, "assistente", MENSAGEM_BOAS_VINDAS_SERVICOS)
                    enviar_whatsapp_api(numero_cliente, MENSAGEM_BOAS_VINDAS_SERVICOS)
                    return jsonify({"status": "recebido"}), 200

                servicos_achados = buscar_servicos_relevantes(msg_recebida)
                if not servicos_achados and historico_anterior:
                    contexto_msg = " ".join([m for _, _, m, *_ in historico_anterior[-6:]])
                    servicos_achados = buscar_servicos_relevantes(contexto_msg)

                ja_tem, falta_avaliar = resumir_dados_ja_informados(historico_anterior, msg_recebida)

                if servicos_achados:
                    base_conhecimento = "\n".join([
                        f"- {s['nome']} ({s['segmento']}): Como é feito: {s['como_e_feito']} | Orientações: {s['perguntas_graduais']}"
                        for s in servicos_achados[:3]
                    ])
                else:
                    base_conhecimento = (
                        "- Serviços da Serate Serviços: elétrica residencial/comercial/industrial, quadros e comandos, "
                        "refrigeração e ar-condicionado (split, piso-teto, cassete, inverter, geladeiras e freezers), "
                        "segurança eletrônica, automação (residencial/Alexa e industrial/bombas), redes/cabeamento/antenas, "
                        "interfonia/telefonia, alarmes/incêndio, SPDA/aterramento/geradores/transformadores/subestações "
                        "e outros serviços como solda, grades, hidráulica e reparos gerais."
                    )

                historico_texto = "\n".join([
                    f"{'Cliente' if r == 'cliente' else 'Serate'}: {m}"
                    for _, r, m, *_ in historico_anterior
                ])

                prompt_chat = (
                    "Você é o assistente da Serate Serviços no WhatsApp. "
                    "Converse como gente de verdade, de forma curta, direta e natural, sem enrolar e sem soar robô.\n"
                    "Regras fundamentais:\n"
                    "1) NUNCA repita perguntas sobre algo que já está em 'Já informado'.\n"
                    "2) Foque só no básico que falta: o que precisa ser feito, se quer com material ou só instalação/mão de obra "
                    "(se quiser só instalar, diga que passamos o que precisa e a pessoa compra), o bloco se for condomínio/prédio "
                    "com vários blocos, o local/endereço e o dia/período.\n"
                    "3) Quando o cliente pedir VALOR ou ORÇAMENTO: diga de forma simples como funciona e passe a referência de ar-condicionado "
                    "quando for o caso (instalação/mão de obra a partir de R$ 350; material até 3 metros R$ 750, podendo variar se passar de 3m "
                    "ou conforme o local), e já peça para ele mandar FOTO ou VÍDEO do local da instalação e dizer se o trajeto tem mais de "
                    "3 metros de distância para avaliação.\n"
                    "4) Faça no máximo 1 ou 2 perguntas curtas por mensagem. Assim que o cliente já tiver informado o serviço, "
                    "material/instalação, local (e bloco se for condomínio/prédio) e dia/período — e não estiver pedindo valor/orçamento "
                    "pendente — ENCERRE de forma educada e objetiva, dizendo que ficou anotado e que no local você confere tudo na prática.\n"
                    "5) Nunca invente preço fechado definitivo nem finja que fechou agenda oficial.\n"
                    f"6) SÓ mencione chave Pix ou CNPJ se o cliente falar de pagamento, cobrança, valor a pagar ou fatura. Se citar, use: CNPJ: {CHAVE_PIX_OFICIAL}.\n\n"
                    f"Já informado na conversa: {', '.join(ja_tem) if ja_tem else 'nada ainda'}.\n"
                    f"Ainda falta ver (se ainda não tiver encerrado): {', '.join(falta_avaliar) if falta_avaliar else 'tudo básico já informado -> pode encerrar bem'}.\n\n"
                    f"Referência de serviços:\n{base_conhecimento}\n\n"
                    f"Histórico recente:\n{historico_texto if historico_texto else '(início da conversa)'}\n\n"
                    f"Mensagem atual do cliente: '{msg_recebida}'."
                )

                try:
                    resposta_ia = chamar_gemini(prompt_chat)
                except Exception as erro_ia:
                    print("Erro Gemini no chat, a usar resposta padrão:", repr(erro_ia), flush=True)
                    resposta_ia = (
                        "Oi! Tudo bem? Aqui é da Serate Serviços. "
                        "Me conta o que você precisa hoje para eu te ajudar."
                    )

                registrar_mensagem_conversa(numero_cliente, "assistente", resposta_ia)
                enviar_whatsapp_api(numero_cliente, resposta_ia)
        except Exception as e:
            print("Erro no webhook:", repr(e), flush=True)
        return jsonify({"status": "recebido"}), 200


if __name__ == "__main__":
    criar_tabelas()

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=verificar_e_enviar_cobrancas_diarias, trigger="cron", hour=8, minute=0)
    scheduler.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
