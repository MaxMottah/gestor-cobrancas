from flask import Flask, render_template_string, request, redirect, url_for, jsonify, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import secrets
import uuid
import re
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
    "Olá! Tudo bem? Seja muito bem-vindo(a) à *SERATE Serviços*! ⚡❄️\n\n"
    "Vai ser um prazer te atender. Trabalhamos com soluções em elétrica, "
    "climatização, refrigeração e automação, além de outros serviços técnicos.\n\n"
    "Me conta: o que você precisa resolver? Estou à disposição para te ajudar!"
)

# Instruções permanentes de comportamento e conhecimento da atendente.
# São combinadas com o histórico, os serviços cadastrados e a mensagem atual.
INSTRUCOES_IA_SERATE = """
IDENTIDADE
Você é a assistente virtual oficial da SERATE Serviços — Soluções Elétricas,
Climatização e Automação. Atende pelo WhatsApp como uma excelente profissional
de relacionamento: humana na conversa, muito educada, respeitosa, acolhedora,
paciente, atenciosa e tecnicamente preparada. Fale sempre em português brasileiro.

PERSONALIDADE E TOM
- Seja gentil e respeitosa com qualquer pessoa, sem exceção.
- Use linguagem natural, simples e calorosa, sem parecer um robô ou um menu automático.
- Seja profissional sem ser excessivamente formal. Pode usar expressões naturais:
  "Claro!", "Entendi", "Perfeito", "Vamos ver isso", "Posso te ajudar".
- Demonstre interesse genuíno e paciência. Nunca ironize, julgue, discuta ou pressione.
- Adapte a explicação: linguagem simples para leigos e termos técnicos quando falar
  com profissionais da área.
- Responda de forma objetiva, mas aprofunde quando o cliente pedir explicações.
- Não use intimidade exagerada, apelidos, excesso de emojis ou frases artificiais.
- Não repita apresentação, catálogo ou informações que já apareceram na conversa.

CONVERSA INTELIGENTE E RESPOSTAS CURTAS
- Primeiro responda diretamente ao que o cliente perguntou. Só depois, se for
  realmente necessário, faça UMA pergunta objetiva para avançar o atendimento.
- REGRA PADRÃO: no máximo UMA pergunta por mensagem. Só faça uma segunda pergunta
  se for indispensável para evitar um risco ou esclarecer algo essencial.
- Seja breve: normalmente 1 a 3 frases curtas, preferencialmente entre 20 e 55
  palavras. Só escreva mais quando o cliente pedir explicação detalhada ou quando
  uma orientação de segurança exigir.
- Não envie textos longos, catálogos, listas de perguntas ou explicações técnicas
  extensas sem que o cliente peça.
- Não faça várias perguntas separadas por vírgulas, "e", barras ou "ou", nem
  transforme uma pergunta em várias solicitações.
- Escolha a informação mais importante que falta e pergunte somente sobre ela.
  Aguarde a resposta antes de investigar o próximo detalhe.
- Se já houver informação suficiente para responder, responda e não faça pergunta
  apenas para manter a conversa.
- Não repita na mesma mensagem o que o cliente acabou de dizer em outras palavras.
- Não transforme o atendimento em interrogatório nem envie listas enormes.
- Considere todas as mensagens anteriores. Nunca pergunte novamente algo que o
  cliente já informou.
- Entenda abreviações, erros de digitação, mensagens curtas e transcrições de áudio.
- Se a mensagem estiver ambígua, confirme educadamente o que a pessoa quis dizer.
- Se o cliente mudar de assunto, acompanhe a mudança sem perder o contexto.
- Se estiver irritado ou insatisfeito, reconheça a preocupação, peça desculpas
  quando couber e procure encaminhar uma solução, sem discutir.
- Não force venda. Ajude primeiro, explique as opções e convide para o próximo passo
  apenas quando fizer sentido.

SAUDAÇÃO
Quando receber apenas "oi", "olá", "bom dia" ou semelhante, cumprimente brevemente
e pergunte como pode ajudar. Não despeje o catálogo completo. Se a pessoa já disser
o que precisa na primeira mensagem, vá direto ao assunto.

ÁREAS DE CONHECIMENTO
Você pode conversar e orientar inicialmente sobre os seguintes campos:

1) ELÉTRICA RESIDENCIAL, PREDIAL, COMERCIAL E INDUSTRIAL:
instalações e reformas, tomadas, iluminação, circuitos, cabos e condutores,
dimensionamento, queda de tensão, sobrecarga, curto-circuito, quadros de distribuição,
disjuntores, DR, DPS, barramentos, aterramento, equipotencialização, alimentadores,
prumadas, infraestrutura, eletrocalhas, eletrodutos, manutenção e diagnóstico.

2) COMANDOS ELÉTRICOS E MOTORES:
motores monofásicos e trifásicos, contatores, relés auxiliares, relés térmicos,
temporizadores, proteção contra falta/sequência de fase, partida direta,
estrela-triângulo, reversão, intertravamentos, diagramas de força e comando,
inversores de frequência, soft starters, painéis e quadros de comando.

3) AUTOMAÇÃO RESIDENCIAL, COMERCIAL E INDUSTRIAL:
Alexa, Google Home, interruptores e tomadas inteligentes, relés Wi-Fi,
sensores de presença, abertura, nível e temperatura, iluminação, climatização,
portões, fechaduras, bombas, sistemas de recalque, CLP, Ladder, IHM, lógica de
controle, supervisão, integração e monitoramento.

4) PYTHON, SISTEMAS AUTÔNOMOS E IoT:
lógica de programação, Python, scripts, APIs, webhooks, bancos de dados,
interfaces web, integração software/hardware, ESP32, Arduino, MQTT, sensores,
Internet das Coisas, automação de tarefas e inteligência artificial aplicada.
Diferencie claramente estudos, protótipos e projetos em desenvolvimento dos
serviços efetivamente disponíveis para contratação pela SERATE. Não prometa
uma solução pronta sem confirmação.

5) REFRIGERAÇÃO E CLIMATIZAÇÃO:
ar-condicionado split, inverter, cassete, piso-teto, multi-split e sistemas centrais;
geladeiras, freezers e refrigeração comercial. Instalação, desinstalação,
reinstalação, limpeza, higienização, manutenção preventiva/corretiva e diagnóstico.
Conheça ciclo frigorífico, compressor, condensador, evaporador, capilar, válvula
de expansão, filtro secador, dreno, tubulação, vácuo, estanqueidade, vazamentos,
carga de refrigerante, superaquecimento, sub-resfriamento, sensores e placas.
Considere fluidos como R22, R32, R410A e R134a conforme aplicação e equipamento.
Não recomende apenas "completar o gás": vazamento e causa da falha precisam ser
investigados. Não dê diagnóstico definitivo sem avaliação.

6) ELETRÔNICA:
fontes lineares e chaveadas, resistores, capacitores, diodos, transistores,
MOSFETs, indutores, transformadores, relés, circuitos integrados, retificadores,
reguladores, componentes SMD, placas eletrônicas, multímetro, soldagem e
diagnóstico de placas de eletrodomésticos e equipamentos de climatização.

7) ANTENAS COLETIVAS E TELECOMUNICAÇÕES:
antenas UHF/VHF e log-periódicas, amplificadores, filtros LTE/4G/5G, divisores,
TAPs/derivadores, atenuadores, RG6, conectores, prumadas, racks, cabeamento,
distribuição de TV, perdas de sinal e medições em dB, dBm e dBµV.
Saiba diferenciar divisor de TAP e investigar se a falha ocorre em uma TV,
apartamento, andar ou em todo o condomínio.

8) SEGURANÇA ELETRÔNICA:
CFTV analógico e IP, câmeras Wi-Fi e PoE, DVR, NVR, fontes, cabeamento, rede,
armazenamento, acesso remoto, alarmes, cercas elétricas, centrais de choque,
sensores, sirenes, fechaduras elétricas/eletromagnéticas/digitais, controladoras,
RFID, biometria, interfones, vídeo porteiros e controle de acesso.

9) SPDA E PROTEÇÃO:
SPDA, captores, método Franklin, gaiola de Faraday, descidas, aterramento,
equipotencialização, inspeções, medições e DPS. Explique que SPDA e DPS têm
funções diferentes. Não prometa emissão de laudo ou assinatura técnica sem
confirmação de habilitação e contratação específica.

10) GERADORES E TRANSFERÊNCIA:
grupos geradores a diesel/gasolina, potência kVA/kW, fator de potência,
alternadores, reguladores, baterias, partida, manutenção, QTA, QTM, ATS,
chaves de transferência manual/automática, contatores, intertravamentos e
sequência de transferência entre concessionária e gerador.

11) INCÊNDIO E BOMBAS:
centrais convencionais/endereçoáveis, detectores de fumaça e temperatura,
acionadores, sinalizadores, sirenes, módulos, laços, bombas de incêndio,
quadros de comando, bombas centrífugas/submersíveis/de recalque, cisternas,
reservatórios, boias, sensores de nível, alternância e proteção contra trabalho a seco.

12) OUTROS SERVIÇOS:
infraestrutura, cabeamento, soldagem, grades, hidráulica e reparos gerais,
sempre sujeitos à confirmação de escopo e disponibilidade.

DIAGNÓSTICO E ORIENTAÇÃO
- Faça perguntas que realmente ajudem a entender o problema: equipamento,
  marca/modelo, comportamento, quando começou, código de erro, local e alcance
  da falha. Não faça todas de uma vez.
- Se receber foto, examine apenas o que for visível. Descreva dúvidas e limitações;
  não invente componentes, medições ou defeitos que a imagem não comprova.
- Explique possibilidades como hipóteses, não como diagnóstico confirmado.
- Para assuntos complexos, recomende avaliação presencial e medições adequadas.
- Não instrua leigos a abrir quadros, tocar em condutores, trabalhar energizados,
  subir em altura, manipular refrigerantes ou intervir em geradores.
- Em risco de choque, incêndio, fumaça ou acidente, priorize afastamento e
  atendimento profissional/emergencial.

ATENDIMENTO COMERCIAL
- Descubra gradualmente o serviço, tipo de imóvel/empresa, bairro/local, equipamento,
  necessidade de material ou somente mão de obra e prazo desejado, apenas quando
  essas informações forem relevantes.
- Se for condomínio, pergunte bloco/torre somente se necessário.
- Quando o cliente pedir orçamento, explique com clareza o que precisa ser avaliado.
  Solicite fotos ou vídeos quando ajudarem, sem exigir material desnecessário.
- Use o catálogo e os dados comerciais fornecidos no contexto como fonte prioritária.
- Nunca invente preço, desconto, disponibilidade, prazo, visita, garantia, forma de
  pagamento ou serviço oferecido.
- Se não houver preço cadastrado, explique educadamente que depende do escopo e
  que será necessário avaliar para passar um valor correto.
- Valores de referência não são preço final: deixe explícito quando podem variar.
- Diferencie mão de obra, material, equipamento, deslocamento e visita técnica.
- Não diga que agendou, confirmou ou fechou serviço sem uma confirmação real do sistema
  ou de um responsável da SERATE.
- Não afirme que a empresa emite laudo, ART ou documento técnico sem confirmação.

USO DO CONTEXTO DO SISTEMA
- O histórico da conversa, a seção "Já informado", o catálogo cadastrado e as
  referências comerciais são dados importantes. Use-os sem contradizer.
- O catálogo cadastrado define os serviços e descrições comerciais atuais.
  O conhecimento técnico geral ajuda a explicar, mas não autoriza prometer execução.
- Se houver conflito entre uma suposição sua e os dados cadastrados, não invente:
  peça confirmação ou informe que a equipe verificará.
- Quando o cliente pedir para pagar ou gerar Pix, use o fluxo automático do sistema:
  confirme o valor e aguarde um "sim" explícito antes de criar a cobrança.
  Nunca diga que gerou o Pix antes de o sistema confirmar a criação.
  O sistema enviará o link oficial do Mercado Pago e o código copia e cola.
  Se o cliente não tiver valor de fatura cadastrado, pergunte qual valor deseja pagar.
- Só mencione Pix, cobrança ou CNPJ quando o cliente tratar de pagamento/fatura.
  Nunca solicite pagamento antecipado sem instrução comercial explícita.
- Se não souber, diga com honestidade que precisa confirmar com a equipe técnica.

ENCERRAMENTO
Quando já entender a necessidade e tiver coletado os dados necessários, resuma
brevemente o que entendeu e informe o próximo passo de forma cordial. Não continue
fazendo perguntas sem necessidade. Agradeça a confiança e deixe o cliente à vontade
para acrescentar alguma informação.

OBJETIVO
Oferecer um atendimento humano, respeitoso, tecnicamente responsável e eficiente;
conquistar confiança; esclarecer dúvidas; identificar a necessidade real; e facilitar
o encaminhamento para avaliação, orçamento ou contratação, sem pressão e sem promessas
que a SERATE não tenha confirmado.
"""


SERVICOS_INICIAIS = [
    (
        "Elétrica Residencial, Predial e Comercial",
        "dia_a_dia",
        "eletrica, tomada, interruptor, chuveiro, iluminacao, fiao, fio, disjuntor, curto, energia, solar, 1, eletrico",
        "Realizamos serviços em tomadas, interruptores, chuveiros, iluminação e instalações elétricas completas. Também avaliamos a carga, a bitola dos cabos e o percurso dos circuitos para reduzir riscos de aquecimento e queda de tensão.",
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
        CREATE TABLE IF NOT EXISTS solicitacoes_pix_ia (
            phone TEXT PRIMARY KEY,
            amount REAL,
            description TEXT,
            payer_name TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def extrair_valor_mensagem(texto):
    """Extrai um valor monetário explícito informado pelo cliente."""
    texto = (texto or "").lower().replace("\u00a0", " ")
    padroes = [
        r"r\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)",
        r"(?:valor|pagar|pagamento)\s+(?:de\s+)?(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:reais)?",
    ]
    for padrao in padroes:
        m = re.search(padrao, texto)
        if m:
            bruto = m.group(1).replace(".", "").replace(",", ".")
            try:
                valor = float(bruto)
                if 0 < valor <= 1000000:
                    return round(valor, 2)
            except ValueError:
                pass
    return None

def salvar_solicitacao_pix(phone, amount=None, description=None, payer_name=None):
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        INSERT INTO solicitacoes_pix_ia (phone, amount, description, payer_name, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(phone) DO UPDATE SET
            amount=COALESCE(excluded.amount, solicitacoes_pix_ia.amount),
            description=COALESCE(excluded.description, solicitacoes_pix_ia.description),
            payer_name=COALESCE(excluded.payer_name, solicitacoes_pix_ia.payer_name),
            updated_at=CURRENT_TIMESTAMP
    """, (somente_digitos(phone), amount, description, payer_name))
    conexao.commit()
    conexao.close()

def buscar_solicitacao_pix(phone):
    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("SELECT amount, description, payer_name FROM solicitacoes_pix_ia WHERE phone=?", (somente_digitos(phone),))
    row = cursor.fetchone()
    conexao.close()
    return row

def excluir_solicitacao_pix(phone):
    conexao = sqlite3.connect(DB_NAME)
    conexao.execute("DELETE FROM solicitacoes_pix_ia WHERE phone=?", (somente_digitos(phone),))
    conexao.commit()
    conexao.close()

def enviar_mensagem_pix_gerado(phone, valor, descricao, pix_info):
    """Envia QR/copia-e-cola e o link oficial de pagamento do Mercado Pago."""
    partes = [f"Prontinho! Gerei seu Pix da *SERATE Serviços* no valor de *R$ {valor:.2f}*.", f"Referente a: {descricao}."]
    if pix_info.get("ticket_url"):
        partes.append(f"Para pagar com segurança, acesse o link do Mercado Pago: {pix_info['ticket_url']}")
    if pix_info.get("qr_code"):
        partes.append(f"Ou use o código Pix copia e cola:\n`{pix_info['qr_code']}`")
    partes.append("Assim que o Mercado Pago confirmar o pagamento, aviso você por aqui. 😊")
    mensagem = "\n\n".join(partes)
    registrar_mensagem_conversa(phone, "assistente", mensagem)
    enviar_whatsapp_api(phone, mensagem)

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
# VISUAL (CSS compartilhado entre as telas)
# ---------------------------------------------------------------------------
BASE_CSS = r"""
:root { --verde:#0F6E56; --verde-esc:#085041; --bg:#f0f2f5; --card:#ffffff; --txt:#111b21; --txt2:#54656f; --borda:#e1e5e8; --bolha-in:#ffffff; --bolha-out:#d9fdd3; --chat-bg:#efeae2; --campo:#f0f2f5; --ok-bg:#dcfce7; --ok-txt:#166534; --av-bg:#e6f1fb; --av-txt:#0c447c; --perigo:#dc2626; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0b141a; --card:#111b21; --txt:#e9edef; --txt2:#8696a0; --borda:#222d34; --bolha-in:#202c33; --bolha-out:#005c4b; --chat-bg:#0b141a; --campo:#202c33; --ok-bg:#064e3b; --ok-txt:#a7f3d0; --av-bg:#0c447c; --av-txt:#b5d4f4; }
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body { font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; background: var(--bg); color: var(--txt); font-size: 15px; }
a { color: inherit; text-decoration: none; }
button, input, select { font: inherit; color: inherit; }
.topo { background: var(--verde); color: #fff; padding: 12px 14px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.topo strong { font-size: 17px; font-weight: 600; }
.topo-acoes { display: flex; gap: 8px; align-items: center; }
.topo-acoes a { background: rgba(255,255,255,0.18); color: #fff; padding: 7px 12px; border-radius: 18px; font-size: 13px; }
.tag { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.tag.verde { background: #dcfce7; color: #166534; }
.tag.amar { background: #fef3c7; color: #92400e; }
.tag.verm { background: #fee2e2; color: #991b1b; }
.tag.azul { background: #dbeafe; color: #1e40af; }
.avatar { width: 44px; height: 44px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 14px; flex: none; }
"""

LOGIN_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0F6E56">
<title>Serate Serviços - Entrar</title>
<style>
/*BASE*/
body { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
.caixa { width: 100%; max-width: 380px; background: var(--card); border: 1px solid var(--borda); border-radius: 16px; padding: 28px 24px; }
.logo { width: 60px; height: 60px; border-radius: 50%; background: var(--verde); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 26px; margin: 0 auto 12px; }
h1 { margin: 0 0 4px; text-align: center; font-size: 22px; font-weight: 600; }
.sub { text-align: center; color: var(--txt2); font-size: 14px; margin-bottom: 20px; }
label { display: block; font-size: 13px; color: var(--txt2); margin: 12px 0 4px; }
input { width: 100%; padding: 12px; border: 1px solid var(--borda); background: var(--campo); border-radius: 10px; font-size: 16px; }
input:focus { outline: 2px solid var(--verde); }
button { width: 100%; margin-top: 20px; padding: 13px; border: 0; border-radius: 10px; background: var(--verde); color: #fff; font-weight: 600; font-size: 16px; cursor: pointer; }
.erro { background: #fee2e2; color: #991b1b; padding: 10px; border-radius: 8px; font-size: 13px; margin-bottom: 8px; text-align: center; }
</style>
</head>
<body>
<div class="caixa">
  <div class="logo">⚡</div>
  <h1>Serate Serviços</h1>
  <div class="sub">Painel de atendimento</div>
  {% if erro %}<div class="erro">{{ erro }}</div>{% endif %}
  <form method="POST">
    <input type="hidden" name="next" value="{{ next_url or '' }}">
    <label>Usuário</label>
    <input type="text" name="usuario" required autofocus autocomplete="username">
    <label>Senha</label>
    <input type="password" name="senha" required autocomplete="current-password">
    <button type="submit">Entrar</button>
  </form>
</div>
</body>
</html>
"""

CHAT_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0F6E56">
<title>Serate Serviços - Conversas</title>
<style>
/*BASE*/
.app { display: flex; height: 100vh; height: 100dvh; max-width: 1200px; margin: 0 auto; background: var(--card); }
.lista { width: 340px; border-right: 1px solid var(--borda); display: flex; flex-direction: column; position: relative; min-height: 0; }
.conversa { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--chat-bg); }
.busca { padding: 10px 12px 6px; }
.busca input { width: 100%; padding: 10px 14px; border: 0; background: var(--campo); border-radius: 20px; font-size: 15px; }
.filtros { display: flex; gap: 6px; padding: 6px 12px 10px; overflow-x: auto; border-bottom: 1px solid var(--borda); }
.filtros button { border: 0; background: var(--campo); color: var(--txt); border-radius: 16px; padding: 5px 12px; font-size: 13px; white-space: nowrap; cursor: pointer; }
.filtros button.ativo { background: var(--verde); color: #fff; }
.contatos { flex: 1; overflow-y: auto; }
.contato { display: flex; gap: 12px; padding: 12px; border-bottom: 1px solid var(--borda); cursor: pointer; }
.contato:hover { background: var(--campo); }
.contato.ativo { background: var(--campo); }
.contato .meio { flex: 1; min-width: 0; }
.linha1, .linha2 { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.nome { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hora { font-size: 12px; color: var(--txt2); flex: none; }
.hora.novo { color: var(--verde); font-weight: 600; }
.previa { font-size: 13px; color: var(--txt2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.contador { background: var(--verde); color: #fff; border-radius: 10px; font-size: 11px; padding: 1px 7px; flex: none; }
.etiquetas { margin-top: 4px; display: flex; gap: 6px; }
.vazio { padding: 24px 16px; color: var(--txt2); text-align: center; font-size: 14px; }
.fab { position: absolute; right: 16px; bottom: 16px; width: 52px; height: 52px; border-radius: 50%; border: 0; background: var(--verde); color: #fff; font-size: 26px; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.25); }
.nova { position: absolute; left: 0; right: 0; bottom: 0; background: var(--card); border-top: 1px solid var(--borda); padding: 14px; z-index: 5; }
.nova[hidden] { display: none; }
.nova input { width: 100%; padding: 11px; border: 1px solid var(--borda); background: var(--campo); border-radius: 10px; font-size: 16px; }
.nova .botoes { display: flex; gap: 8px; margin-top: 10px; }
.nova button { flex: 1; padding: 11px; border-radius: 10px; border: 1px solid var(--borda); background: var(--campo); cursor: pointer; }
.nova button.prim { background: var(--verde); color: #fff; border-color: var(--verde); font-weight: 600; }
.cab { background: var(--verde); color: #fff; padding: 10px 12px; display: flex; align-items: center; gap: 10px; }
.cab .info { flex: 1; min-width: 0; line-height: 1.3; }
.cab .info b { display: block; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cab .info small { font-size: 12px; opacity: 0.85; }
.cab .avatar { width: 38px; height: 38px; font-size: 13px; }
.voltar { display: none; font-size: 22px; padding: 0 4px; }
.btn-ia { border: 0; border-radius: 16px; padding: 6px 12px; font-size: 12px; cursor: pointer; background: rgba(255,255,255,0.22); color: #fff; }
.msgs { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 6px; min-height: 0; }
.dia { align-self: center; font-size: 12px; color: var(--txt2); background: var(--card); border-radius: 8px; padding: 2px 10px; margin: 6px 0; }
.bolha { max-width: 82%; padding: 7px 10px; border-radius: 12px; font-size: 15px; line-height: 1.4; box-shadow: 0 1px 1px rgba(0,0,0,0.08); word-break: break-word; }
.bolha.in { align-self: flex-start; background: var(--bolha-in); border-bottom-left-radius: 3px; }
.bolha.out { align-self: flex-end; background: var(--bolha-out); border-bottom-right-radius: 3px; }
.bolha .txt { white-space: pre-wrap; }
.bolha .meta { font-size: 11px; color: var(--txt2); text-align: right; margin-top: 3px; }
.pix { white-space: normal; margin: 8px 0 2px; background: var(--card); border: 1px solid var(--borda); border-radius: 8px; padding: 8px; }
.pix code { display: block; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11px; word-break: break-all; max-height: 54px; overflow: hidden; }
.pix button { margin-top: 6px; width: 100%; border: 0; border-radius: 6px; padding: 7px; background: var(--verde); color: #fff; font-weight: 600; cursor: pointer; }
.atalhos { display: flex; gap: 8px; padding: 8px 10px 0; background: var(--card); border-top: 1px solid var(--borda); overflow-x: auto; }
.atalhos a, .atalhos button { border: 1px solid var(--borda); background: var(--campo); border-radius: 16px; padding: 5px 12px; font-size: 13px; white-space: nowrap; cursor: pointer; }
.rapidas { background: var(--card); padding: 8px 10px 0; display: flex; flex-direction: column; gap: 6px; }
.rapidas[hidden] { display: none; }
.rapidas button { text-align: left; border: 1px solid var(--borda); background: var(--campo); border-radius: 10px; padding: 8px 10px; font-size: 14px; cursor: pointer; }
.envio { display: flex; gap: 8px; padding: 8px 10px calc(10px + env(safe-area-inset-bottom, 0px)); background: var(--card); }
.envio input { flex: 1; padding: 11px 14px; border: 0; background: var(--campo); border-radius: 22px; font-size: 16px; }
.envio button { width: 44px; height: 44px; border-radius: 50%; border: 0; background: var(--verde); color: #fff; font-size: 18px; cursor: pointer; }
.sem-conversa { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--txt2); text-align: center; padding: 20px; }
.aviso { position: fixed; left: 50%; transform: translateX(-50%); bottom: 90px; background: #111b21; color: #fff; padding: 8px 16px; border-radius: 18px; font-size: 14px; z-index: 20; }
.aviso[hidden] { display: none; }
@media (max-width: 800px) {
  .lista { width: 100%; border-right: 0; }
  .app[data-chat="1"] .lista { display: none; }
  .app[data-chat="0"] .conversa { display: none; }
  .voltar { display: inline-block; }
  .bolha { max-width: 88%; }
}
</style>
</head>
<body>
<div class="app" id="app" data-chat="{{ '1' if phone_ativo else '0' }}">

  <aside class="lista">
    <div class="topo">
      <strong>Serate Serviços</strong>
      <div class="topo-acoes">
        <a href="{{ url_for('cobrancas') }}">🧾 Cobranças</a>
        <a href="{{ url_for('logout') }}">Sair</a>
      </div>
    </div>
    <div class="busca"><input id="busca" type="search" placeholder="Buscar nome ou número"></div>
    <div class="filtros" id="filtros">
      <button type="button" data-f="todas" class="ativo">Todas</button>
      <button type="button" data-f="nao_lidas">Não lidas</button>
      <button type="button" data-f="pago">Pagas</button>
      <button type="button" data-f="pendente">Pendentes</button>
    </div>
    <div class="contatos" id="contatos"></div>
    <button class="fab" id="fab" type="button" aria-label="Nova conversa">+</button>
    <div class="nova" id="nova" hidden>
      <input id="nova-fone" type="tel" inputmode="numeric" placeholder="DDD + número, ex: 91999998888">
      <div class="botoes">
        <button type="button" id="nova-cancelar">Cancelar</button>
        <button type="button" class="prim" id="nova-abrir">Abrir conversa</button>
      </div>
    </div>
  </aside>

  <main class="conversa">
    {% if phone_ativo %}
    <div class="cab">
      <a class="voltar" href="{{ url_for('chat_painel') }}" aria-label="Voltar">←</a>
      <div class="avatar" id="cab-avatar"></div>
      <div class="info">
        <b id="cab-nome"></b>
        <small id="cab-sub"></small>
      </div>
      <form method="POST" action="{{ url_for('alternar_pausa', phone=phone_ativo) }}" style="margin:0;">
        <button type="submit" class="btn-ia" id="btn-ia">{{ '▶ Reativar IA' if pausado_ativo else '⏸ Pausar IA' }}</button>
      </form>
    </div>
    <div class="msgs" id="msgs"></div>
    <div class="atalhos">
      <a href="{{ url_for('cobrancas', phone=phone_ativo, nome=nome_ativo or '') }}">🧾 Gerar Pix</a>
      <button type="button" id="btn-rapidas">Respostas rápidas</button>
    </div>
    <div class="rapidas" id="rapidas" hidden>
      <button type="button">Olá! Tudo bem? Pode me mandar uma foto ou vídeo do local?</button>
      <button type="button">Qual o endereço e o melhor dia e horário para a visita?</button>
      <button type="button">Fica com material incluso ou só a mão de obra?</button>
      <button type="button">Qualquer dúvida é só chamar por aqui. Obrigado!</button>
    </div>
    <form class="envio" id="envio" autocomplete="off">
      <input id="texto" type="text" placeholder="Digite uma mensagem" required>
      <button type="submit" aria-label="Enviar">➤</button>
    </form>
    {% else %}
    <div class="sem-conversa">Escolha uma conversa na lista<br>ou toque em + para abrir um número novo.</div>
    {% endif %}
  </main>
</div>
<div class="aviso" id="aviso" hidden></div>

<script>
(function () {
  var PHONE = {{ phone_ativo|tojson }};
  var NOME_ATIVO = {{ (nome_ativo or '')|tojson }};
  var contatos = {{ contatos|tojson }};
  var mensagens = {{ mensagens|tojson }};
  var pausado = {{ pausado_ativo|tojson }};
  var filtro = "todas";
  var termo = "";
  var CORES = [["#e6f1fb","#0c447c"],["#eeedfe","#3c3489"],["#e1f5ee","#085041"],["#faece7","#712b13"],["#fbeaf0","#72243e"],["#faeeda","#633806"]];

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  function dataUtc(s) {
    if (!s) return null;
    var d = new Date(String(s).replace(" ", "T") + "Z");
    return isNaN(d.getTime()) ? null : d;
  }
  function mesmoDia(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }
  function fmtHora(d) { return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }); }
  function fmtLista(s) {
    var d = dataUtc(s); if (!d) return "";
    var hoje = new Date(), ontem = new Date(); ontem.setDate(hoje.getDate() - 1);
    if (mesmoDia(d, hoje)) return fmtHora(d);
    if (mesmoDia(d, ontem)) return "Ontem";
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  }
  function fmtDia(d) {
    var hoje = new Date(), ontem = new Date(); ontem.setDate(hoje.getDate() - 1);
    if (mesmoDia(d, hoje)) return "Hoje";
    if (mesmoDia(d, ontem)) return "Ontem";
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "long" });
  }
  function fmtFone(p) {
    var n = String(p || "").replace(/\D/g, "");
    if (n.length === 13 && n.indexOf("55") === 0) return "+55 " + n.slice(2, 4) + " " + n.slice(4, 9) + "-" + n.slice(9);
    if (n.length === 12 && n.indexOf("55") === 0) return "+55 " + n.slice(2, 4) + " " + n.slice(4, 8) + "-" + n.slice(8);
    if (n.length === 11) return "(" + n.slice(0, 2) + ") " + n.slice(2, 7) + "-" + n.slice(7);
    if (n.length === 10) return "(" + n.slice(0, 2) + ") " + n.slice(2, 6) + "-" + n.slice(6);
    return p;
  }
  function titulo(c) { return c.nome ? c.nome : fmtFone(c.phone); }
  function iniciais(nome, fone) {
    var limpo = String(nome || "").replace(/[^A-Za-zÀ-ÿ ]/g, "").trim();
    if (!limpo) return String(fone || "").replace(/\D/g, "").slice(-2) || "#";
    var p = limpo.split(/ +/);
    return (p[0][0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
  }
  function corDe(fone) {
    var n = parseInt(String(fone || "0").replace(/\D/g, "").slice(-3) || "0", 10);
    return CORES[n % CORES.length];
  }
  function avatarHtml(nome, fone, extra) {
    var c = corDe(fone);
    return '<div class="avatar" ' + (extra || "") + ' style="background:' + c[0] + ';color:' + c[1] + '">' + esc(iniciais(nome, fone)) + "</div>";
  }

  function fmtTexto(t) {
    var s = esc(t);
    s = s.replace(/\*([^*\n]+)\*/g, "<b>$1</b>");
    s = s.replace(/`([^`]{15,})`/g, '<div class="pix"><code>$1</code><button type="button" class="copiar">Copiar código Pix</button></div>');
    return s;
  }

  function avisar(texto) {
    var a = $("aviso"); a.textContent = texto; a.hidden = false;
    setTimeout(function () { a.hidden = true; }, 2600);
  }

  function renderContatos() {
    var box = $("contatos");
    var q = termo.toLowerCase().trim();
    var lista = contatos.filter(function (c) {
      if (filtro === "nao_lidas" && !(c.nao_lidas > 0)) return false;
      if (filtro === "pago" && c.tag !== "pago") return false;
      if (filtro === "pendente" && c.tag !== "pendente") return false;
      if (q) {
        var alvo = (c.nome + " " + c.phone + " " + fmtFone(c.phone) + " " + c.message).toLowerCase();
        if (alvo.indexOf(q) === -1) return false;
      }
      return true;
    });
    if (!lista.length) {
      box.innerHTML = '<div class="vazio">' + (contatos.length ? "Nenhuma conversa encontrada." : "Nenhuma conversa ainda. Toque em + para abrir um número ou aguarde uma mensagem no WhatsApp.") + "</div>";
      return;
    }
    box.innerHTML = lista.map(function (c) {
      var ativo = c.phone === PHONE ? " ativo" : "";
      var prefixo = c.role !== "cliente" ? "Você: " : "";
      var tag = c.tag === "pago" ? '<span class="tag verde">Pago</span>' : (c.tag === "pendente" ? '<span class="tag amar">Pendente</span>' : "");
      var pausa = c.pausado ? '<span class="tag azul">IA pausada</span>' : "";
      var cont = c.nao_lidas > 0 ? '<span class="contador">' + c.nao_lidas + "</span>" : "";
      return '<a class="contato' + ativo + '" href="/chat?phone=' + encodeURIComponent(c.phone) + '">' +
        avatarHtml(c.nome, c.phone) +
        '<div class="meio">' +
          '<div class="linha1"><span class="nome">' + esc(titulo(c)) + '</span><span class="hora' + (c.nao_lidas > 0 ? " novo" : "") + '">' + esc(fmtLista(c.created_at)) + "</span></div>" +
          '<div class="linha2"><span class="previa">' + esc(prefixo + c.message.replace(/\*|`/g, "")) + "</span>" + cont + "</div>" +
          ((tag || pausa) ? '<div class="etiquetas">' + tag + pausa + "</div>" : "") +
        "</div></a>";
    }).join("");
  }

  function renderCabecalho() {
    if (!PHONE) return;
    var atual = contatos.filter(function (c) { return c.phone === PHONE; })[0];
    var nome = (atual && atual.nome) || NOME_ATIVO || "";
    $("cab-nome").textContent = nome || fmtFone(PHONE);
    $("cab-sub").textContent = (nome ? fmtFone(PHONE) + " · " : "") + (pausado ? "IA pausada (você responde)" : "IA respondendo");
    var c = corDe(PHONE);
    var av = $("cab-avatar");
    av.textContent = iniciais(nome, PHONE);
    av.style.background = c[0]; av.style.color = c[1];
    $("btn-ia").textContent = pausado ? "▶ Reativar IA" : "⏸ Pausar IA";
  }

  var ultimoIdMsg = -1;
  function renderMensagens(forcarFim) {
    var box = $("msgs");
    if (!box) return;
    var maior = mensagens.length ? mensagens[mensagens.length - 1].id : 0;
    if (maior === ultimoIdMsg && !forcarFim) return;
    ultimoIdMsg = maior;
    var perto = (box.scrollHeight - box.scrollTop - box.clientHeight) < 120;
    if (!mensagens.length) {
      box.innerHTML = '<div class="vazio">Nenhuma mensagem com este número ainda.</div>';
      return;
    }
    var html = "", diaAnterior = null;
    mensagens.forEach(function (m) {
      var d = dataUtc(m.created_at);
      if (d && (!diaAnterior || !mesmoDia(d, diaAnterior))) {
        html += '<div class="dia">' + esc(fmtDia(d)) + "</div>";
        diaAnterior = d;
      }
      var entrada = m.role === "cliente";
      var quem = entrada ? "" : (m.role === "atendente" ? "Você · " : "IA · ");
      html += '<div class="bolha ' + (entrada ? "in" : "out") + '"><div class="txt">' + fmtTexto(m.message) + '</div><div class="meta">' + quem + (d ? esc(fmtHora(d)) : "") + "</div></div>";
    });
    box.innerHTML = html;
    if (perto || forcarFim) box.scrollTop = box.scrollHeight;
  }

  async function atualizar(forcar) {
    if (document.hidden && !forcar) return;
    try {
      var url = "/api/chat/mensagens" + (PHONE ? "?phone=" + encodeURIComponent(PHONE) : "");
      var r = await fetch(url, { cache: "no-store" });
      if (r.status === 401) { location.href = "/login"; return; }
      if (!r.ok) return;
      var d = await r.json();
      contatos = d.contatos || [];
      if (PHONE) { mensagens = d.mensagens || []; pausado = !!d.pausado; }
      renderContatos();
      renderCabecalho();
      renderMensagens(false);
    } catch (e) { console.log("Falha ao atualizar:", e); }
  }

  $("busca").addEventListener("input", function (e) { termo = e.target.value; renderContatos(); });
  $("filtros").addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    filtro = b.getAttribute("data-f");
    Array.prototype.forEach.call($("filtros").children, function (x) { x.classList.toggle("ativo", x === b); });
    renderContatos();
  });

  $("fab").addEventListener("click", function () { $("nova").hidden = false; $("nova-fone").focus(); });
  $("nova-cancelar").addEventListener("click", function () { $("nova").hidden = true; });
  function abrirNumero() {
    var n = $("nova-fone").value.replace(/\D/g, "");
    if (n.length === 10 || n.length === 11) n = "55" + n;
    if (n.length < 12) { avisar("Digite DDD + número"); return; }
    location.href = "/chat?phone=" + n;
  }
  $("nova-abrir").addEventListener("click", abrirNumero);
  $("nova-fone").addEventListener("keydown", function (e) { if (e.key === "Enter") abrirNumero(); });

  if (PHONE) {
    $("msgs").addEventListener("click", function (e) {
      var b = e.target.closest(".copiar"); if (!b) return;
      var codigo = b.parentNode.querySelector("code").textContent;
      var ok = function () { avisar("Código Pix copiado"); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(codigo).then(ok, function () { avisar("Não deu para copiar"); });
      } else {
        var t = document.createElement("textarea"); t.value = codigo; document.body.appendChild(t); t.select();
        try { document.execCommand("copy"); ok(); } catch (x) { avisar("Não deu para copiar"); }
        document.body.removeChild(t);
      }
    });

    $("btn-rapidas").addEventListener("click", function () { var r = $("rapidas"); r.hidden = !r.hidden; });
    $("rapidas").addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      $("texto").value = b.textContent; $("rapidas").hidden = true; $("texto").focus();
    });

    var enviando = false;
    $("envio").addEventListener("submit", async function (e) {
      e.preventDefault();
      var t = $("texto").value.trim();
      if (!t || enviando) return;
      enviando = true;
      try {
        var r = await fetch("/api/chat/enviar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone: PHONE, mensagem: t }) });
        var d = await r.json();
        if (d.ok) { $("texto").value = ""; await atualizar(true); renderMensagens(true); }
        else { avisar(d.erro || "Falha ao enviar. Veja os logs."); }
      } catch (x) { avisar("Falha de conexão"); }
      enviando = false;
    });

    renderCabecalho();
    renderMensagens(true);
  }

  renderContatos();
  setInterval(function () { atualizar(false); }, 4000);
})();
</script>
</body>
</html>
"""

COBRANCAS_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0F6E56">
<title>Serate Serviços - Cobranças</title>
<style>
/*BASE*/
.pagina { max-width: 640px; margin: 0 auto; padding: 0 0 40px; }
.conteudo { padding: 14px; }
.cartao { background: var(--card); border: 1px solid var(--borda); border-radius: 14px; padding: 16px; margin-bottom: 14px; }
h2 { font-size: 17px; margin: 0 0 12px; font-weight: 600; }
label { display: block; font-size: 13px; color: var(--txt2); margin: 14px 0 5px; }
input, select { width: 100%; padding: 11px 12px; border: 1px solid var(--borda); background: var(--campo); border-radius: 10px; font-size: 16px; }
input:focus, select:focus { outline: 2px solid var(--verde); }
[hidden] { display: none !important; }
.cats { display: flex; gap: 6px; overflow-x: auto; margin-bottom: 10px; }
.cats button { border: 0; background: var(--campo); border-radius: 16px; padding: 6px 14px; font-size: 13px; white-space: nowrap; cursor: pointer; }
.cats button.ativo { background: var(--verde); color: #fff; }
.servicos { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.servico { text-align: left; border: 1px solid var(--borda); background: var(--card); border-radius: 10px; padding: 10px; font-size: 14px; cursor: pointer; }
.servico small { display: block; color: var(--txt2); margin-top: 2px; }
.servico.sel { border: 2px solid var(--verde); padding: 9px; }
.servico.outro { border-style: dashed; color: var(--verde); }
.duas { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.btn { display: block; width: 100%; text-align: center; padding: 13px; border-radius: 10px; border: 1px solid var(--borda); background: var(--campo); font-size: 15px; font-weight: 600; cursor: pointer; margin-top: 10px; }
.btn.prim { background: var(--verde); border-color: var(--verde); color: #fff; }
.btn.peq { padding: 8px 12px; font-size: 13px; margin-top: 0; }
.erro { color: var(--perigo); font-size: 13px; margin-top: 10px; }
.msg-ok { background: var(--ok-bg); color: var(--ok-txt); padding: 11px 14px; border-radius: 10px; margin-bottom: 14px; font-size: 14px; }
.abas { display: flex; gap: 6px; margin-bottom: 12px; }
.abas button { flex: 1; padding: 9px; border: 0; border-radius: 10px; background: var(--campo); cursor: pointer; font-weight: 600; }
.abas button.ativo { background: var(--verde); color: #fff; }
.item { border: 1px solid var(--borda); border-radius: 12px; padding: 12px; margin-bottom: 10px; }
.item .linha { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.item .mut { color: var(--txt2); font-size: 13px; margin-top: 2px; }
.item .acoes { display: flex; gap: 8px; margin-top: 10px; }
.item .acoes form { flex: 1; margin: 0; }
.item .acoes .btn { margin-top: 0; }
.msgbox { background: var(--campo); border-radius: 8px; padding: 8px 10px; font-size: 13px; margin-top: 6px; white-space: pre-wrap; word-break: break-word; }
details summary { cursor: pointer; font-size: 13px; color: var(--txt2); margin-top: 8px; }
.perigo summary { color: var(--perigo); }
.btn.vermelho { background: var(--perigo); border-color: var(--perigo); color: #fff; }
</style>
</head>
<body>
<div class="pagina">
  <div class="topo">
    <strong>Cobranças</strong>
    <div class="topo-acoes">
      <a href="{{ url_for('chat_painel') }}">💬 Conversas</a>
      <a href="{{ url_for('logout') }}">Sair</a>
    </div>
  </div>

  <div class="conteudo">
    {% if aviso %}<div class="msg-ok">{{ aviso }}</div>{% endif %}

    <form method="POST" id="form-cob" class="cartao" autocomplete="off">
      <h2>Nova cobrança</h2>
      <input type="hidden" name="client_name" id="client_name">
      <input type="hidden" name="client_phone" id="client_phone">
      <input type="hidden" name="service_desc" id="service_desc">

      <label style="margin-top:0">Cliente</label>
      <select id="cliente_sel">
        <option value="">Escolha um cliente</option>
        {% for c in clientes %}
        <option value="{{ c.phone }}" data-nome="{{ c.nome }}" {% if c.phone == phone_pre %}selected{% endif %}>{{ c.nome }}{% if c.nome != c.phone %} · {{ c.phone }}{% endif %}</option>
        {% endfor %}
        <option value="__novo__">+ Novo cliente</option>
      </select>
      <div id="novo-cliente" hidden>
        <label>Nome do cliente</label>
        <input id="novo_nome" type="text" placeholder="Carlos Silva">
        <label>WhatsApp (DDD + número)</label>
        <input id="novo_fone" type="tel" inputmode="numeric" placeholder="91999998888">
      </div>

      <label>Serviço</label>
      <div class="cats" id="cats"></div>
      <div class="servicos" id="servicos"></div>
      <div id="outro-box" hidden>
        <label>Descreva o serviço</label>
        <input id="outro_desc" type="text" placeholder="Ex: Troca de tomada da cozinha">
      </div>

      <div class="duas">
        <div>
          <label>Valor (R$)</label>
          <input type="text" inputmode="decimal" name="amount" id="amount" placeholder="350,00">
        </div>
        <div>
          <label>Vencimento</label>
          <input type="date" name="due_date" id="due_date" value="{{ hoje }}">
        </div>
      </div>

      <div class="erro" id="erro" hidden></div>
      <button class="btn prim" type="submit" name="acao" value="enviar_pix_agora">Enviar Pix agora no WhatsApp</button>
      <button class="btn" type="submit" name="acao" value="cadastrar">Agendar lembrete de cobrança</button>
    </form>

    <div class="abas">
      <button type="button" class="ativo" data-aba="faturas">Faturas</button>
      <button type="button" data-aba="pagamentos">Pagamentos Pix</button>
    </div>

    <div id="aba-faturas">
      {% for f in faturas %}
      <div class="item">
        <div class="linha">
          <strong>{{ f[1] }}</strong>
          {% if f[5] == 'pago' %}<span class="tag verde">Pago</span>
          {% elif f[4] < hoje %}<span class="tag verm">Atrasado</span>
          {% elif f[5] == 'enviado' %}<span class="tag azul">Enviado</span>
          {% else %}<span class="tag amar">Pendente</span>{% endif %}
        </div>
        <div>{{ f[2] }}</div>
        <div class="mut">R$ {{ "%.2f"|format(f[3]) }} · vence {{ f[4][8:10] }}/{{ f[4][5:7] }}/{{ f[4][0:4] }}</div>
        {% if f[6] %}<details><summary>Ver mensagem do lembrete</summary><div class="msgbox">{{ f[6] }}</div></details>{% endif %}
        <div class="acoes">
          {% if f[5] != 'pago' %}
          <form method="POST">
            <input type="hidden" name="acao" value="gerar_pix_fatura">
            <input type="hidden" name="fatura_id" value="{{ f[0] }}">
            <button type="submit" class="btn peq prim">Gerar Pix e enviar</button>
          </form>
          {% endif %}
          <a class="btn peq" style="flex:1" href="{{ url_for('chat_painel', phone=f[7]) }}">Abrir conversa</a>
        </div>
      </div>
      {% else %}
      <div class="mut" style="text-align:center;color:var(--txt2)">Nenhuma fatura registrada.</div>
      {% endfor %}
    </div>

    <div id="aba-pagamentos" hidden>
      {% for p in pagamentos %}
      <div class="item">
        <div class="linha">
          <strong>{{ p[2] or 'Pagador não informado' }}</strong>
          {% if p[4] == 'approved' %}<span class="tag verde">Confirmado</span>{% else %}<span class="tag amar">{{ p[4] }}</span>{% endif %}
        </div>
        <div>{{ p[5] }}</div>
        <div class="mut">R$ {{ "%.2f"|format(p[3]) }} · WhatsApp {{ p[1] or '-' }} · ID {{ p[0] }}</div>
        <div class="mut">Atualizado: <span data-utc="{{ p[6] }}">{{ p[6] }}</span></div>
      </div>
      {% else %}
      <div class="mut" style="text-align:center;color:var(--txt2)">Nenhum Pix gerado ainda.</div>
      {% endfor %}
    </div>

    <details class="cartao perigo" style="margin-top:20px">
      <summary>Configurações</summary>
      <form method="POST" onsubmit="return confirm('Apagar TODAS as faturas? Isso não dá para desfazer.');">
        <input type="hidden" name="acao" value="apagar_tudo">
        <button type="submit" class="btn vermelho">Apagar todas as faturas</button>
      </form>
    </details>
  </div>
</div>

<script>
(function () {
  var CATALOGO = {{ catalogo|tojson }};
  var PRE_NOME = {{ nome_pre|tojson }};
  var categoria = Object.keys(CATALOGO)[0];
  var servicoSel = null;
  var outro = false;

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  function renderCats() {
    $("cats").innerHTML = Object.keys(CATALOGO).map(function (c) {
      return '<button type="button" data-c="' + esc(c) + '" class="' + (c === categoria ? "ativo" : "") + '">' + esc(c) + "</button>";
    }).join("");
  }
  function renderServicos() {
    var html = CATALOGO[categoria].map(function (s, i) {
      var sel = (!outro && servicoSel && servicoSel.cat === categoria && servicoSel.i === i) ? " sel" : "";
      var preco = s[1] > 0 ? "R$ " + String(s[1]).replace(".", ",") : "valor na hora";
      return '<button type="button" class="servico' + sel + '" data-i="' + i + '">' + esc(s[0]) + "<small>" + preco + "</small></button>";
    }).join("");
    html += '<button type="button" class="servico outro' + (outro ? " sel" : "") + '" data-outro="1">+ Outro serviço</button>';
    $("servicos").innerHTML = html;
    $("outro-box").hidden = !outro;
  }

  $("cats").addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    categoria = b.getAttribute("data-c"); renderCats(); renderServicos();
  });
  $("servicos").addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    if (b.getAttribute("data-outro")) { outro = true; servicoSel = null; renderServicos(); $("outro_desc").focus(); return; }
    outro = false;
    var i = parseInt(b.getAttribute("data-i"), 10);
    servicoSel = { cat: categoria, i: i };
    var preco = CATALOGO[categoria][i][1];
    if (preco > 0) $("amount").value = String(preco).replace(".", ",");
    renderServicos();
  });

  $("cliente_sel").addEventListener("change", function () {
    $("novo-cliente").hidden = this.value !== "__novo__";
  });
  if ($("cliente_sel").value === "__novo__") $("novo-cliente").hidden = false;

  function mostrarErro(t) { var e = $("erro"); e.textContent = t; e.hidden = false; }

  var enviado = false;
  $("form-cob").addEventListener("submit", function (e) {
    if (enviado) { e.preventDefault(); return; }
    var sel = $("cliente_sel"), nome = "", fone = "";
    if (sel.value === "__novo__") {
      nome = $("novo_nome").value.trim();
      fone = $("novo_fone").value.replace(/\D/g, "");
    } else if (sel.value) {
      fone = sel.value;
      nome = sel.options[sel.selectedIndex].getAttribute("data-nome") || "";
      if (nome === fone && PRE_NOME) nome = PRE_NOME;
      if (nome === fone) nome = "Cliente";
    }
    if (!fone || fone.length < 10) { e.preventDefault(); mostrarErro("Escolha o cliente (ou informe nome e WhatsApp)."); return; }
    if (!nome) { e.preventDefault(); mostrarErro("Informe o nome do cliente."); return; }
    var desc = "";
    if (outro) desc = $("outro_desc").value.trim();
    else if (servicoSel) desc = CATALOGO[servicoSel.cat][servicoSel.i][0];
    if (!desc) { e.preventDefault(); mostrarErro("Escolha o serviço."); return; }
    var valor = parseFloat($("amount").value.replace(/\./g, "").replace(",", "."));
    if (!(valor > 0)) { e.preventDefault(); mostrarErro("Informe o valor."); return; }
    if (!$("due_date").value) { e.preventDefault(); mostrarErro("Informe o vencimento."); return; }
    $("client_name").value = nome; $("client_phone").value = fone; $("service_desc").value = desc;
    $("amount").value = String(valor);
    enviado = true;
  });

  document.querySelectorAll(".abas button").forEach(function (b) {
    b.addEventListener("click", function () {
      var aba = b.getAttribute("data-aba");
      document.querySelectorAll(".abas button").forEach(function (x) { x.classList.toggle("ativo", x === b); });
      $("aba-faturas").hidden = aba !== "faturas";
      $("aba-pagamentos").hidden = aba !== "pagamentos";
    });
  });

  document.querySelectorAll("[data-utc]").forEach(function (el) {
    var d = new Date(el.getAttribute("data-utc").replace(" ", "T") + "Z");
    if (!isNaN(d.getTime())) el.textContent = d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  });

  renderCats(); renderServicos();
})();
</script>
</body>
</html>
"""

LOGIN_TEMPLATE = LOGIN_TEMPLATE.replace("/*BASE*/", BASE_CSS)
CHAT_TEMPLATE = CHAT_TEMPLATE.replace("/*BASE*/", BASE_CSS)
COBRANCAS_TEMPLATE = COBRANCAS_TEMPLATE.replace("/*BASE*/", BASE_CSS)


# ---------------------------------------------------------------------------
# ROTAS
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    next_url = request.args.get("next") or request.form.get("next") or ""
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("chat_painel")

    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""
        if usuario == PAINEL_USUARIO and check_password_hash(PAINEL_SENHA_HASH, senha):
            session["autenticado"] = True
            session.permanent = True
            return redirect(next_url)
        erro = "Usuário ou senha inválidos."

    return render_template_string(LOGIN_TEMPLATE, erro=erro, next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/pix/criar", methods=["POST"])
@login_obrigatorio
def api_pix_criar():
    dados = request.json or {}
    amount = dados.get("amount")
    description = (dados.get("description") or "Serviço Serate Serviços").strip()
    phone = somente_digitos(dados.get("phone")) or None
    fatura_id = dados.get("fatura_id")
    payer_name = (dados.get("payer_name") or "").strip() or None
    payer_email = (dados.get("payer_email") or "cliente@serateservicos.com.br").strip()

    if not amount or float(amount) <= 0:
        return jsonify({"erro": "valor_invalido"}), 400

    try:
        pix_info = criar_pagamento_pix_mp(
            amount=float(amount),
            description=description,
            payer_email=payer_email,
            phone=phone,
            fatura_id=fatura_id,
            payer_name=payer_name,
        )
        if phone and pix_info.get("qr_code"):
            enviar_mensagem_pix_gerado(phone, float(amount), description, pix_info)
        return jsonify({"status": "ok", "pix": pix_info}), 201
    except Exception as e:
        print("Erro ao criar Pix MP:", repr(e), flush=True)
        return jsonify({"erro": str(e)}), 500


@app.route("/api/pix/consultar/<payment_id>")
@login_obrigatorio
def api_pix_consultar(payment_id):
    try:
        dados = consultar_pagamento_mp(payment_id)
        status_mp = processar_atualizacao_pagamento_mp(payment_id)
        return jsonify({
            "id": str(payment_id),
            "status": status_mp,
            "payer_name": extrair_nome_pagador_mp(dados),
            "date_approved": dados.get("date_approved"),
        })
    except Exception as e:
        print("Erro ao consultar Pix MP:", repr(e), flush=True)
        return jsonify({"erro": str(e)}), 500


@app.route("/webhook/mercadopago", methods=["POST"])
def webhook_mercadopago():
    payload = request.json or {}
    print("Webhook Mercado Pago recebido:", payload, flush=True)

    payment_id = None
    data_obj = payload.get("data") or {}
    if data_obj.get("id"):
        payment_id = str(data_obj.get("id"))
    elif request.args.get("data.id"):
        payment_id = str(request.args.get("data.id"))
    elif request.args.get("id") and request.args.get("topic") == "payment":
        payment_id = str(request.args.get("id"))

    if payment_id:
        try:
            status_atual = processar_atualizacao_pagamento_mp(payment_id)
            print(f"Pix {payment_id} processado. Status atual: {status_atual}", flush=True)
        except Exception as e:
            print(f"Falha ao processar webhook MP {payment_id}:", repr(e), flush=True)

    return jsonify({"status": "recebido"}), 200


@app.route("/api/chat/mensagens")
@login_obrigatorio
def api_chat_mensagens():
    phone_limpo = somente_digitos(request.args.get("phone"))
    if phone_limpo:
        marcar_como_lido(phone_limpo)
    contatos = listar_contatos_conversa()
    mensagens_raw = buscar_historico_conversa(phone_limpo, limite=100) if phone_limpo else []
    mensagens_json = [
        {"id": m[0], "role": m[1], "message": m[2], "created_at": m[3]}
        for m in mensagens_raw
    ]
    return jsonify({
        "phone": phone_limpo,
        "pausado": ia_esta_pausada(phone_limpo) if phone_limpo else False,
        "mensagens": mensagens_json,
        "contatos": contatos,
    })


@app.route("/api/chat/enviar", methods=["POST"])
@login_obrigatorio
def api_chat_enviar():
    dados = request.json or {}
    phone = somente_digitos(dados.get("phone"))
    mensagem = (dados.get("mensagem") or "").strip()
    if not phone or not mensagem:
        return jsonify({"ok": False, "erro": "Informe o número e a mensagem."}), 400

    sucesso = enviar_whatsapp_api(phone, mensagem)
    if sucesso:
        registrar_mensagem_conversa(phone, "atendente", mensagem)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "erro": "Falha ao enviar pela API do WhatsApp. Veja os logs."}), 502


@app.route("/chat")
@login_obrigatorio
def chat_painel():
    phone_ativo = somente_digitos(request.args.get("phone")) or None
    if phone_ativo:
        marcar_como_lido(phone_ativo)
    contatos = listar_contatos_conversa()
    mensagens_raw = buscar_historico_conversa(phone_ativo, limite=100) if phone_ativo else []
    mensagens = [
        {"id": m[0], "role": m[1], "message": m[2], "created_at": m[3]}
        for m in mensagens_raw
    ]
    pausado_ativo = ia_esta_pausada(phone_ativo) if phone_ativo else False
    nome_ativo = nome_do_contato(phone_ativo) if phone_ativo else None

    return render_template_string(
        CHAT_TEMPLATE,
        contatos=contatos,
        phone_ativo=phone_ativo,
        nome_ativo=nome_ativo,
        mensagens=mensagens,
        pausado_ativo=pausado_ativo,
    )


@app.route("/chat/pausa/<phone>", methods=["POST"])
@login_obrigatorio
def alternar_pausa(phone):
    phone_limpo = somente_digitos(phone)
    if phone_limpo:
        novo_estado = not ia_esta_pausada(phone_limpo)
        definir_pausa_ia(phone_limpo, novo_estado)
    return redirect(url_for("chat_painel", phone=phone_limpo))


@app.route("/")
@login_obrigatorio
def index():
    return redirect(url_for("chat_painel"))


@app.route("/cobrancas", methods=["GET", "POST"])
@login_obrigatorio
def cobrancas():
    hoje = date.today().isoformat()

    if request.method == "POST":
        acao = request.form.get("acao")
        aviso = None
        conexao = sqlite3.connect(DB_NAME)
        cursor = conexao.cursor()

        if acao in ("cadastrar", "enviar_pix_agora"):
            try:
                client_name = (request.form.get("client_name") or "").strip()
                client_phone = normalizar_telefone(request.form.get("client_phone"))
                service_desc = (request.form.get("service_desc") or "").strip()
                amount = float((request.form.get("amount") or "0").replace(",", "."))
                due_date = request.form.get("due_date") or hoje
            except ValueError:
                conexao.close()
                return redirect(url_for("cobrancas", aviso="Valor inválido."))

            if not client_name or not client_phone or not service_desc or amount <= 0:
                conexao.close()
                return redirect(url_for("cobrancas", aviso="Preencha cliente, serviço e valor."))

            if acao == "cadastrar":
                ai_msg = gerar_mensagem_ia(client_name, service_desc, amount, due_date, CHAVE_PIX_OFICIAL)
                cursor.execute("""
                    INSERT INTO faturas (client_name, client_phone, service_desc, amount, due_date, pix_key, status, ai_message)
                    VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?)
                """, (client_name, client_phone, service_desc, amount, due_date, CHAVE_PIX_OFICIAL, ai_msg))
                conexao.commit()
                aviso = "Lembrete agendado. A mensagem sai no dia do vencimento, às 8h."
            else:
                cursor.execute("""
                    INSERT INTO faturas (client_name, client_phone, service_desc, amount, due_date, pix_key, status, ai_message)
                    VALUES (?, ?, ?, ?, ?, ?, 'enviado', '')
                """, (client_name, client_phone, service_desc, amount, due_date, CHAVE_PIX_OFICIAL))
                fatura_id = cursor.lastrowid
                conexao.commit()
                try:
                    info = gerar_e_enviar_pix(fatura_id, client_name, client_phone, service_desc, amount)
                    aviso = f"Pix gerado (ID #{info['id']}) e enviado no WhatsApp de {client_name}."
                except Exception as e:
                    print("Erro ao gerar Pix:", repr(e), flush=True)
                    aviso = f"A fatura foi salva, mas deu erro ao gerar o Pix: {e}"

        elif acao == "gerar_pix_fatura":
            fatura_id = request.form.get("fatura_id")
            cursor.execute(
                "SELECT id, client_name, client_phone, service_desc, amount FROM faturas WHERE id = ?",
                (fatura_id,),
            )
            f = cursor.fetchone()
            if f:
                f_id, c_name, c_phone, s_desc, amt = f
                try:
                    info = gerar_e_enviar_pix(f_id, c_name, c_phone, s_desc, amt)
                    aviso = f"Pix gerado (ID #{info['id']}) e enviado no WhatsApp!"
                except Exception as e:
                    print("Erro ao gerar Pix:", repr(e), flush=True)
                    aviso = f"Erro ao gerar Pix: {e}"

        elif acao == "apagar_tudo":
            cursor.execute("DELETE FROM faturas")
            conexao.commit()
            aviso = "Todas as faturas foram apagadas."

        conexao.close()
        return redirect(url_for("cobrancas", aviso=aviso or ""))

    # GET
    phone_pre = somente_digitos(request.args.get("phone"))
    nome_pre = (request.args.get("nome") or "").strip()
    aviso = request.args.get("aviso")

    clientes = listar_clientes_para_cobranca()
    if phone_pre and phone_pre not in [c["phone"] for c in clientes]:
        clientes.insert(0, {"phone": phone_pre, "nome": nome_pre or phone_pre})

    conexao = sqlite3.connect(DB_NAME)
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT id, client_name, service_desc, amount, due_date, status, ai_message, client_phone
        FROM faturas ORDER BY id DESC
    """)
    faturas = cursor.fetchall()
    cursor.execute("""
        SELECT payment_id, phone, payer_name, amount, status, description, updated_at, qr_code
        FROM pagamentos_pix
        ORDER BY id DESC
        LIMIT 25
    """)
    pagamentos = cursor.fetchall()
    conexao.close()

    return render_template_string(
        COBRANCAS_TEMPLATE,
        faturas=faturas,
        pagamentos=pagamentos,
        aviso=aviso,
        clientes=clientes,
        phone_pre=phone_pre,
        nome_pre=nome_pre,
        catalogo=CATALOGO_COBRANCA,
        hoje=hoje,
    )


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    """Webhook para atender clientes no chat, ler imagens e gerenciar Pix/pagamentos."""
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
                tipo_msg = msg_obj.get('type') or 'text'
                msg_recebida = (msg_obj.get('text', {}).get('body') or "").strip()

                imagem_bytes = None
                mime_type = "image/jpeg"
                if tipo_msg == "image":
                    img_obj = msg_obj.get("image") or {}
                    media_id = img_obj.get("id")
                    legenda = (img_obj.get("caption") or "").strip()
                    msg_recebida = legenda or "[Imagem enviada pelo cliente]"
                    if media_id:
                        imagem_bytes, mime_type = baixar_midia_whatsapp(media_id)

                print(f"Mensagem de {numero_cliente} ({tipo_msg}): {msg_recebida}", flush=True)

                if not numero_cliente or (not msg_recebida and not imagem_bytes):
                    print("Mensagem ignorada (sem conteúdo ou remetente).", flush=True)
                    return jsonify({"status": "ignorado"}), 200

                historico_anterior = buscar_historico_conversa(numero_cliente, limite=14)
                registrar_mensagem_conversa(numero_cliente, "cliente", msg_recebida)

                if ia_esta_pausada(numero_cliente):
                    print(f"IA pausada para {numero_cliente}. Aguardando resposta manual em /chat.", flush=True)
                    return jsonify({"status": "pausado"}), 200

                msg_lower = msg_recebida.lower()

                # Se perguntar se foi pago ou mandar comprovante, confere último Pix do número no Mercado Pago
                if any(p in msg_lower for p in ["foi pago", "ja paguei", "já paguei", "confirmou", "pagou", "comprovante"]) and MP_ACCESS_TOKEN:
                    ult_pix = buscar_ultimo_pix_telefone(numero_cliente)
                    if ult_pix:
                        pay_id, amt, desc, st, payer_nm, _ = ult_pix
                        try:
                            st_atual = processar_atualizacao_pagamento_mp(pay_id)
                            if st_atual == "approved":
                                resp_pago = (
                                    f"Sim! O Pix de R$ {float(amt):.2f} ({desc}, ID #{pay_id}) já consta como *APROVADO* no Mercado Pago"
                                    + (f" em nome de *{payer_nm}*." if payer_nm else ".")
                                )
                            else:
                                resp_pago = (
                                    f"Ainda consta como *pendente* no Mercado Pago o Pix de R$ {float(amt):.2f} ({desc}, ID #{pay_id}). "
                                    f"Assim que aprovar, eu te aviso na hora!"
                                )
                            registrar_mensagem_conversa(numero_cliente, "assistente", resp_pago)
                            enviar_whatsapp_api(numero_cliente, resp_pago)
                            return jsonify({"status": "status_pix_consultado"}), 200
                        except Exception as e:
                            print("Erro ao checar Pix a pedido do cliente:", repr(e), flush=True)

                # Fluxo de Pix conversacional: identifica o valor, pede confirmação explícita
                # e só então cria a cobrança no Mercado Pago.
                if MP_ACCESS_TOKEN:
                    termos_pix = ("pix", "gerar pix", "gera pix", "mandar pix", "me manda o pix", "link de pagamento", "quero pagar", "fazer pagamento", "pagar agora")
                    confirmacoes = {"sim", "confirmo", "pode gerar", "pode fazer", "pode mandar", "isso", "correto", "confirmado", "pode sim"}
                    cancelamentos = {"não", "nao", "cancela", "cancelar", "deixa", "deixa pra lá", "deixa pra la"}
                    solicitacao_atual = buscar_solicitacao_pix(numero_cliente)
                    texto_limpo = msg_lower.strip().rstrip(".!? ")

                    if solicitacao_atual and texto_limpo in cancelamentos:
                        excluir_solicitacao_pix(numero_cliente)
                        resposta = "Sem problema! Não vou gerar nenhuma cobrança. Se precisar, é só me chamar. 😊"
                        registrar_mensagem_conversa(numero_cliente, "assistente", resposta)
                        enviar_whatsapp_api(numero_cliente, resposta)
                        return jsonify({"status": "pix_cancelado"}), 200

                    if solicitacao_atual:
                        valor_pendente, descricao_pendente, nome_pendente = solicitacao_atual
                        valor_informado = extrair_valor_mensagem(msg_recebida)
                        if valor_pendente is None and valor_informado:
                            valor_pendente = valor_informado
                            descricao_pendente = descricao_pendente or "Pagamento de serviço SERATE"
                            salvar_solicitacao_pix(numero_cliente, valor_pendente, descricao_pendente, nome_pendente)
                            resposta = f"Perfeito! O valor informado é *R$ {valor_pendente:.2f}*. Confirma que posso gerar o Pix nesse valor?"
                            registrar_mensagem_conversa(numero_cliente, "assistente", resposta)
                            enviar_whatsapp_api(numero_cliente, resposta)
                            return jsonify({"status": "aguardando_confirmacao_pix"}), 200

                        if valor_pendente is not None and texto_limpo in confirmacoes:
                            try:
                                pix_info = criar_pagamento_pix_mp(
                                    amount=float(valor_pendente),
                                    description=descricao_pendente or "Pagamento de serviço SERATE",
                                    phone=numero_cliente,
                                    payer_name=nome_pendente,
                                )
                                if not pix_info.get("ticket_url") and not pix_info.get("qr_code"):
                                    raise RuntimeError("Mercado Pago não retornou link nem código Pix.")
                                excluir_solicitacao_pix(numero_cliente)
                                enviar_mensagem_pix_gerado(numero_cliente, float(valor_pendente), descricao_pendente or "Pagamento de serviço SERATE", pix_info)
                                return jsonify({"status": "pix_gerado"}), 200
                            except Exception as erro_pix:
                                print("Erro ao gerar Pix solicitado pelo cliente:", repr(erro_pix), flush=True)
                                resposta = "Tive uma dificuldade para gerar o Pix agora. Não houve cobrança confirmada; vou precisar que a equipe verifique o sistema."
                                registrar_mensagem_conversa(numero_cliente, "assistente", resposta)
                                enviar_whatsapp_api(numero_cliente, resposta)
                                return jsonify({"status": "erro_pix"}), 200

                        if valor_pendente is not None:
                            resposta = f"Só confirmando: posso gerar um Pix de *R$ {float(valor_pendente):.2f}* referente a *{descricao_pendente}*?"
                            registrar_mensagem_conversa(numero_cliente, "assistente", resposta)
                            enviar_whatsapp_api(numero_cliente, resposta)
                            return jsonify({"status": "aguardando_confirmacao_pix"}), 200

                    if any(t in msg_lower for t in termos_pix):
                        valor = extrair_valor_mensagem(msg_recebida)
                        fatura = buscar_ultima_fatura_por_telefone(numero_cliente)
                        nome_cliente = None
                        descricao = "Pagamento de serviço SERATE"
                        if fatura:
                            fatura_id, nome_cliente, desc_fatura, valor_fatura, status_fatura = fatura
                            if status_fatura == "pago":
                                resposta = "Encontrei uma fatura que já consta como paga. Você quer pagar outro serviço?"
                                registrar_mensagem_conversa(numero_cliente, "assistente", resposta)
                                enviar_whatsapp_api(numero_cliente, resposta)
                                return jsonify({"status": "fatura_ja_paga"}), 200
                            descricao = desc_fatura or descricao
                            if valor is None:
                                valor = float(valor_fatura)
                        salvar_solicitacao_pix(numero_cliente, valor, descricao, nome_cliente)
                        if valor is None:
                            resposta = "Claro! Qual valor você deseja pagar?"
                        else:
                            resposta = f"Claro! Tenho o valor de *R$ {float(valor):.2f}* para *{descricao}*. Confirma que posso gerar o Pix pelo Mercado Pago?"
                        registrar_mensagem_conversa(numero_cliente, "assistente", resposta)
                        enviar_whatsapp_api(numero_cliente, resposta)
                        return jsonify({"status": "aguardando_dados_pix" if valor is None else "aguardando_confirmacao_pix"}), 200

                saudacoes_iniciais = {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "oii", "oie"}
                if not imagem_bytes and len(historico_anterior) == 0 and msg_recebida.lower() in saudacoes_iniciais:
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
                    INSTRUCOES_IA_SERATE
                    + "\n\nREGRAS ESPECÍFICAS DESTE ATENDIMENTO:\n"
                    "1) Se o cliente enviou uma IMAGEM, analise o que aparece nela com clareza (se for comprovante, informe o que consta e lembre que a baixa oficial no sistema acontece quando o Pix é aprovado no Mercado Pago; se for equipamento, local, quadro, ar-condicionado ou defeito, ajude na avaliação técnica).\n"
                    "2) NUNCA repita perguntas sobre algo que já está em 'Já informado'.\n"
                    "3) Foque só no básico que falta: o que precisa ser feito, se quer com material ou só instalação/mão de obra "
                    "(se quiser só instalar, diga que passamos o que precisa e a pessoa compra), o bloco se for condomínio/prédio "
                    "com vários blocos, o local/endereço e o dia/período.\n"
                    "4) Quando o cliente pedir VALOR ou ORÇAMENTO: diga de forma simples como funciona e passe a referência de ar-condicionado "
                    "quando for o caso (instalação/mão de obra a partir de R$ 350; material até 3 metros R$ 750, podendo variar se passar de 3m "
                    "ou conforme o local), e já peça para ele mandar FOTO ou VÍDEO do local da instalação e dizer se o trajeto tem mais de "
                    "3 metros de distância para avaliação.\n"
                    "5) RESPOSTA CURTA: responda em 1 a 3 frases curtas (preferencialmente até 55 palavras). "
                    "Faça APENAS UMA pergunta por mensagem e espere a resposta antes de perguntar outra coisa. "
                    "Não despeje todos os dados que precisa coletar de uma vez. Escolha somente o próximo dado mais importante. "
                    "As perguntas sugeridas no cadastro do serviço são referências para etapas futuras, NÃO uma lista para enviar de uma vez. "
                    "Só escreva mais se o cliente pedir detalhes ou se for indispensável para segurança. "
                    "Assim que o cliente já tiver informado o serviço, material/instalação, local (e bloco se for condomínio/prédio) e dia/período — e não estiver pedindo valor/orçamento "
                    "pendente — ENCERRE de forma educada e objetiva, dizendo que ficou anotado e que no local você confere tudo na prática.\n"
                    "6) Nunca invente preço fechado definitivo nem finja que fechou agenda oficial.\n"
                    f"7) SÓ mencione chave Pix ou CNPJ se o cliente falar de pagamento, cobrança, valor a pagar ou fatura. Se citar, use: CNPJ: {CHAVE_PIX_OFICIAL}.\n\n"
                    f"Já informado na conversa: {', '.join(ja_tem) if ja_tem else 'nada ainda'}.\n"
                    f"Ainda falta ver (se ainda não tiver encerrado): {', '.join(falta_avaliar) if falta_avaliar else 'tudo básico já informado -> pode encerrar bem'}.\n\n"
                    f"Referência de serviços:\n{base_conhecimento}\n\n"
                    f"Histórico recente:\n{historico_texto if historico_texto else '(início da conversa)'}\n\n"
                    f"Mensagem atual do cliente: '{msg_recebida}'."
                )

                try:
                    resposta_ia = chamar_gemini(prompt_chat, imagem_bytes=imagem_bytes, mime_type=mime_type)
                except Exception as erro_ia:
                    print("Erro Gemini no chat, ao usar a resposta padrão:", repr(erro_ia), flush=True)
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
    scheduler.add_job(func=verificar_pagamentos_pix_pendentes, trigger="interval", seconds=30)
    scheduler.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
