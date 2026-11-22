from flask import Flask, render_template_string, request, redirect, url_for, jsonify
import sqlite3
import os
import requests
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler
from google import genai

app = Flask(__name__)
DB_NAME = "cobrancas.db"

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

    for item in SERVICOS_INICIAIS:
        cursor.execute("""
            INSERT OR IGNORE INTO catalogo_servicos
            (nome, segmento, palavras_chave, como_e_feito, perguntas_graduais)
            VALUES (?, ?, ?, ?, ?)
        """, item)

    conexao.commit()
    conexao.close()


def registrar_mensagem_conversa(phone, role, message):
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        INSERT INTO conversas_whatsapp (phone, role, message)
        VALUES (?, ?, ?)
    """, (phone, role, message))
    conexao.commit()
    conexao.close()


def buscar_historico_conversa(phone, limite=14):
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT role, message FROM conversas_whatsapp
        WHERE phone = ?
        ORDER BY id DESC
        LIMIT ?
    """, (phone, limite))
    linhas = cursor.fetchall()
    conexao.close()
    return list(reversed(linhas))


def resumir_dados_ja_informados(historico_anterior, msg_atual):
    """Identifica o que já foi dito na conversa para evitar repetir perguntas ou prolongar."""
    falas_cliente = " ".join(
        [m for r, m in historico_anterior if r == "cliente"] + [msg_atual]
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


@app.route("/", methods=["GET", "POST"])
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

                saudacoes_iniciais = {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "oii", "oie"}
                if len(historico_anterior) == 0 and msg_recebida.lower() in saudacoes_iniciais:
                    registrar_mensagem_conversa(numero_cliente, "assistente", MENSAGEM_BOAS_VINDAS_SERVICOS)
                    enviar_whatsapp_api(numero_cliente, MENSAGEM_BOAS_VINDAS_SERVICOS)
                    return jsonify({"status": "recebido"}), 200

                servicos_achados = buscar_servicos_relevantes(msg_recebida)
                if not servicos_achados and historico_anterior:
                    contexto_msg = " ".join([m for _, m in historico_anterior[-6:]])
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
                    for r, m in historico_anterior
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
