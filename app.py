from flask import Flask, render_template_string, request, redirect, url_for, jsonify, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import secrets
import uuid
import requests
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler
from google import genai
from google.genai import types

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

# Caminho do banco. Por enquanto continua o mesmo arquivo.
# Quando você tiver um disco/banco fixo, é só mudar a variável DB_PATH no Render.
DB_NAME = os.environ.get("DB_PATH", "cobrancas.db")

PAINEL_USUARIO = os.environ.get("PAINEL_USUARIO", "serate")
PAINEL_SENHA_HASH = generate_password_hash(os.environ.get("PAINEL_SENHA", "serate123"))

client = genai.Client()
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "serate123")
CHAVE_PIX_OFICIAL = os.environ.get("CHAVE_PIX_OFICIAL", "42.500.008/0001-17")
MP_ACCESS_TOKEN = (os.environ.get("MP_ACCESS_TOKEN") or "").strip()
MP_NOTIFICATION_URL = (os.environ.get("MP_NOTIFICATION_URL") or "").strip()
MODELOS_GEMINI = ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

# ---------------------------------------------------------------------------
# SERVIÇOS DA TELA DE COBRANÇA
# Formato: ("Nome do serviço", valor_padrao). Valor 0 = você digita na hora.
# Para mudar preço ou incluir serviço, é só editar esta lista.
# ---------------------------------------------------------------------------
CATALOGO_COBRANCA = {
    "Refrigeração": [
        ("Instalação de ar-condicionado", 350),
        ("Limpeza e manutenção de ar-condicionado", 0),
        ("Carga de gás", 0),
        ("Troca de capacitor ou placa", 0),
        ("Reparo de geladeira ou freezer", 0),
        ("Câmara fria", 0),
        ("Visita técnica", 0),
    ],
    "Elétrica": [
        ("Pontos de tomada e iluminação", 0),
        ("Troca de disjuntor ou quadro", 0),
        ("Instalação de chuveiro", 0),
        ("Instalação de ventilador", 0),
        ("Aterramento", 0),
        ("Reparo de curto ou falta de energia", 0),
        ("Visita técnica", 0),
    ],
    "Segurança": [
        ("Instalação de câmeras (CFTV)", 0),
        ("Configuração de DVR/NVR", 0),
        ("Alarme", 0),
        ("Cerca elétrica", 0),
        ("Fechadura digital", 0),
        ("Controle de acesso", 0),
        ("Interfone", 0),
    ],
    "Automação": [
        ("Portão automático", 0),
        ("Automação residencial (Alexa)", 0),
        ("Sensores e iluminação inteligente", 0),
        ("Bombas e quadros de comando", 0),
    ],
    "Outros": [
        ("Rede e cabeamento", 0),
        ("Antena coletiva", 0),
        ("Solda e grades", 0),
        ("Hidráulica e reparos gerais", 0),
        ("Gerador, transformador ou subestação", 0),
    ],
}

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


def somente_digitos(texto):
    return "".join(ch for ch in (texto or "") if ch.isdigit())


def normalizar_telefone(texto):
    """Deixa só números e coloca o 55 do Brasil se faltar (DDD + número)."""
    numero = somente_digitos(texto)
    if len(numero) in (10, 11):
        numero = "55" + numero
    return numero


def chamar_gemini(prompt, imagem_bytes=None, mime_type="image/jpeg"):
    ultimo_erro = None
    for modelo in MODELOS_GEMINI:
        try:
            if imagem_bytes:
                conteudo = [
                    types.Part.from_bytes(data=imagem_bytes, mime_type=mime_type or "image/jpeg"),
                    prompt,
                ]
            else:
                conteudo = prompt

            response = client.models.generate_content(
                model=modelo,
                contents=conteudo,
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversas_phone ON conversas_whatsapp (phone, id)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS atendimento_pausado (
            phone TEXT PRIMARY KEY,
            pausado INTEGER DEFAULT 1,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leitura_chat (
            phone TEXT PRIMARY KEY,
            ultimo_id_lido INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagamentos_pix (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id TEXT UNIQUE NOT NULL,
            fatura_id INTEGER,
            phone TEXT,
            payer_name TEXT,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            qr_code TEXT,
            ticket_url TEXT,
            notificado INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Garante coluna payer_name caso a tabela já exista
    cursor.execute("PRAGMA table_info(pagamentos_pix)")
    colunas = [c[1] for c in cursor.fetchall()]
    if "payer_name" not in colunas:
        cursor.execute("ALTER TABLE pagamentos_pix ADD COLUMN payer_name TEXT")

    # Na primeira vez, marca as conversas antigas como lidas (evita contador gigante)
    cursor.execute("SELECT COUNT(*) FROM leitura_chat")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT OR IGNORE INTO leitura_chat (phone, ultimo_id_lido)
            SELECT phone, MAX(id) FROM conversas_whatsapp GROUP BY phone
        """)

    for item in SERVICOS_INICIAIS:
        cursor.execute("""
            INSERT OR IGNORE INTO catalogo_servicos
            (nome, segmento, palavras_chave, como_e_feito, perguntas_graduais)
            VALUES (?, ?, ?, ?, ?)
        """, item)

    conexao.commit()
    conexao.close()


def extrair_nome_pagador_mp(dados_mp, fallback_nome=None):
    payer = dados_mp.get("payer") or {}
    partes = [
        (payer.get("first_name") or "").strip(),
        (payer.get("last_name") or "").strip(),
    ]
    nome_completo = " ".join(p for p in partes if p).strip()
    if nome_completo:
        return nome_completo
    if payer.get("name"):
        return str(payer.get("name")).strip()
    ident = payer.get("identification") or {}
    if ident.get("number"):
        return f"Doc {ident.get('number')}"
    return fallback_nome or "Não informado pelo MP"


def criar_pagamento_pix_mp(amount, description, payer_email="cliente@serateservicos.com.br", phone=None, fatura_id=None, payer_name=None):
    if not MP_ACCESS_TOKEN:
        raise RuntimeError("MP_ACCESS_TOKEN não configurado no ambiente.")

    partes_nome = (payer_name or "").strip().split(" ", 1)
    payer_payload = {"email": payer_email}
    if partes_nome and partes_nome[0]:
        payer_payload["first_name"] = partes_nome[0]
        if len(partes_nome) > 1 and partes_nome[1].strip():
            payer_payload["last_name"] = partes_nome[1].strip()

    payload = {
        "transaction_amount": round(float(amount), 2),
        "description": description[:140],
        "payment_method_id": "pix",
        "payer": payer_payload,
    }
    if MP_NOTIFICATION_URL:
        payload["notification_url"] = MP_NOTIFICATION_URL

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4()),
    }

    resp = requests.post(
        "https://api.mercadopago.com/v1/payments",
        headers=headers,
        json=payload,
        timeout=20,
    )
    resp.raise_for_status()
    dados = resp.json()

    payment_id = str(dados.get("id"))
    status_mp = dados.get("status") or "pending"
    tx_data = (dados.get("point_of_interaction") or {}).get("transaction_data") or {}
    qr_code = tx_data.get("qr_code") or ""
    ticket_url = tx_data.get("ticket_url") or ""
    nome_pagador = extrair_nome_pagador_mp(dados, fallback_nome=payer_name)

    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO pagamentos_pix
        (payment_id, fatura_id, phone, payer_name, amount, description, status, qr_code, ticket_url, notificado, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        payment_id,
        fatura_id,
        phone,
        nome_pagador,
        float(amount),
        description,
        status_mp,
        qr_code,
        ticket_url,
        1 if status_mp == "approved" else 0,
    ))
    conexao.commit()
    conexao.close()

    return {
        "id": payment_id,
        "status": status_mp,
        "qr_code": qr_code,
        "ticket_url": ticket_url,
        "payer_name": nome_pagador,
    }


def consultar_pagamento_mp(payment_id):
    if not MP_ACCESS_TOKEN:
        raise RuntimeError("MP_ACCESS_TOKEN não configurado no ambiente.")

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
    }
    resp = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=headers,
        timeout=20,
    )
    resp.raise_for_status()
    dados = resp.json()
    status_mp = dados.get("status") or "pending"

    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("SELECT payer_name FROM pagamentos_pix WHERE payment_id = ?", (str(payment_id),))
    atual = cursor.fetchone()
    nome_atual = atual[0] if atual else None
    nome_pagador = extrair_nome_pagador_mp(dados, fallback_nome=nome_atual)

    cursor.execute("""
        UPDATE pagamentos_pix
        SET status = ?, payer_name = ?, updated_at = CURRENT_TIMESTAMP
        WHERE payment_id = ?
    """, (status_mp, nome_pagador, str(payment_id)))
    conexao.commit()
    conexao.close()

    return dados


def processar_atualizacao_pagamento_mp(payment_id):
    dados = consultar_pagamento_mp(str(payment_id))
    status_mp = dados.get("status") or "pending"

    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT fatura_id, phone, amount, description, notificado, payer_name
        FROM pagamentos_pix
        WHERE payment_id = ?
    """, (str(payment_id),))
    row = cursor.fetchone()

    if row and status_mp == "approved":
        fatura_id, phone, amount, description, notificado, payer_name = row
        if fatura_id:
            cursor.execute("UPDATE faturas SET status = 'pago' WHERE id = ?", (fatura_id,))
        if not notificado:
            cursor.execute("UPDATE pagamentos_pix SET notificado = 1 WHERE payment_id = ?", (str(payment_id),))
            conexao.commit()
            if phone:
                quem_pagou = f"\nPagador: *{payer_name}*" if payer_name else ""
                msg_confirmacao = (
                    f"✅ *Pagamento confirmado!* Recebemos o Pix de R$ {float(amount):.2f} "
                    f"referente a *{description}* (ID #{payment_id}).{quem_pagou}\nObrigado!"
                )
                registrar_mensagem_conversa(phone, "assistente", msg_confirmacao)
                enviar_whatsapp_api(phone, msg_confirmacao)
    conexao.commit()
    conexao.close()
    return status_mp


def buscar_ultima_fatura_por_telefone(phone):
    numero_limpo = somente_digitos(phone)
    if not numero_limpo:
        return None
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT id, client_name, service_desc, amount, status
        FROM faturas
        WHERE client_phone = ?
        ORDER BY id DESC
        LIMIT 1
    """, (numero_limpo,))
    row = cursor.fetchone()
    conexao.close()
    return row


def buscar_ultimo_pix_telefone(phone):
    numero_limpo = somente_digitos(phone)
    if not numero_limpo:
        return None
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT payment_id, amount, description, status, payer_name, qr_code
        FROM pagamentos_pix
        WHERE phone = ?
        ORDER BY id DESC
        LIMIT 1
    """, (numero_limpo,))
    row = cursor.fetchone()
    conexao.close()
    return row


def baixar_midia_whatsapp(media_id):
    if not WHATSAPP_TOKEN or not media_id:
        return None, None
    meta_resp = requests.get(
        f"https://graph.facebook.com/v21.0/{media_id}",
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
        timeout=20,
    )
    meta_resp.raise_for_status()
    meta_json = meta_resp.json()
    media_url = meta_json.get("url")
    mime_type = meta_json.get("mime_type") or "image/jpeg"
    if not media_url:
        return None, mime_type

    img_resp = requests.get(
        media_url,
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
        timeout=30,
    )
    img_resp.raise_for_status()
    return img_resp.content, mime_type


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


def marcar_como_lido(phone):
    if not phone:
        return
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        INSERT INTO leitura_chat (phone, ultimo_id_lido)
        SELECT ?, COALESCE(MAX(id), 0) FROM conversas_whatsapp WHERE phone = ?
        ON CONFLICT(phone) DO UPDATE SET ultimo_id_lido = excluded.ultimo_id_lido
    """, (phone, phone))
    conexao.commit()
    conexao.close()


def nome_do_contato(phone):
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("SELECT client_name FROM faturas WHERE client_phone = ? ORDER BY id DESC LIMIT 1", (phone,))
    row = cursor.fetchone()
    conexao.close()
    return row[0] if row else None


def listar_contatos_conversa():
    """Lista de conversas já pronta para a tela (nome, tag Pago/Pendente, não lidas)."""
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT c.phone, c.message, c.role, c.created_at,
               CASE WHEN p.pausado = 1 THEN 1 ELSE 0 END,
               c.id,
               (SELECT f.client_name FROM faturas f WHERE f.client_phone = c.phone ORDER BY f.id DESC LIMIT 1),
               (SELECT x.status FROM pagamentos_pix x WHERE x.phone = c.phone ORDER BY x.id DESC LIMIT 1),
               (SELECT f2.status FROM faturas f2 WHERE f2.client_phone = c.phone ORDER BY f2.id DESC LIMIT 1),
               (SELECT COUNT(*) FROM conversas_whatsapp m
                    WHERE m.phone = c.phone AND m.role = 'cliente'
                    AND m.id > COALESCE((SELECT l.ultimo_id_lido FROM leitura_chat l WHERE l.phone = c.phone), 0))
        FROM conversas_whatsapp c
        INNER JOIN (
            SELECT phone, MAX(id) AS max_id
            FROM conversas_whatsapp
            GROUP BY phone
        ) ult ON c.id = ult.max_id
        LEFT JOIN atendimento_pausado p ON c.phone = p.phone
        ORDER BY c.id DESC
    """)
    linhas = cursor.fetchall()
    conexao.close()

    contatos = []
    for (phone, message, role, created_at, pausado, ultimo_id,
         nome, status_pix, status_fatura, nao_lidas) in linhas:
        if status_pix == "approved" or status_fatura == "pago":
            tag = "pago"
        elif status_pix == "pending" or status_fatura in ("pendente", "enviado"):
            tag = "pendente"
        else:
            tag = ""
        contatos.append({
            "phone": phone,
            "nome": nome or "",
            "message": message,
            "role": role,
            "created_at": created_at,
            "pausado": bool(pausado),
            "ultimo_id": ultimo_id,
            "tag": tag,
            "nao_lidas": nao_lidas,
        })
    return contatos


def listar_clientes_para_cobranca():
    """Clientes para escolher na tela de cobrança (de conversas e de faturas)."""
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("SELECT DISTINCT phone FROM conversas_whatsapp")
    telefones_chat = [r[0] for r in cursor.fetchall()]
    cursor.execute("SELECT client_phone, client_name FROM faturas ORDER BY id ASC")
    nomes = {}
    for fone, nome in cursor.fetchall():
        nomes[fone] = nome
    conexao.close()

    todos = list(dict.fromkeys(telefones_chat + list(nomes.keys())))
    clientes = [{"phone": f, "nome": nomes.get(f) or f} for f in todos]
    clientes.sort(key=lambda c: (c["nome"] == c["phone"], c["nome"].lower()))
    return clientes


def resumir_dados_ja_informados(historico_anterior, msg_atual):
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


def gerar_e_enviar_pix(fatura_id, nome, phone, descricao, valor):
    """Gera o Pix no Mercado Pago e manda o código no WhatsApp do cliente."""
    info = criar_pagamento_pix_mp(
        amount=valor,
        description=descricao,
        phone=phone,
        fatura_id=fatura_id,
        payer_name=nome,
    )
    if phone and info.get("qr_code"):
        msg_pix = (
            f"Segue seu código Pix da *Serate Serviços* no valor de R$ {float(valor):.2f} "
            f"({descricao}):\n\n`{info['qr_code']}`\n\n"
            f"Assim que o pagamento for confirmado, te aviso por aqui!"
        )
        registrar_mensagem_conversa(phone, "assistente", msg_pix)
        enviar_whatsapp_api(phone, msg_pix)
    return info


def verificar_e_enviar_cobrancas_diarias():
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


def verificar_pagamentos_pix_pendentes():
    if not MP_ACCESS_TOKEN:
        return
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("SELECT payment_id FROM pagamentos_pix WHERE status = 'pending'")
    pendentes = cursor.fetchall()
    conexao.close()

    for (payment_id,) in pendentes:
        try:
            processar_atualizacao_pagamento_mp(payment_id)
        except Exception as e:
            print(f"Erro ao verificar Pix {payment_id}:", repr(e), flush=True)


# ---------------------------------------------------------------------------
# VISUAL (C
