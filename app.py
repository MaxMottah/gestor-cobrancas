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
    conexao.commit()
    conexao.close()

def gerar_mensagem_ia(client_name, service_desc, amount, due_date, pix_key):
    """Gera uma mensagem extremamente profissional, empática e bondosa com o Gemini."""
    prompt = (
        f"Crie uma mensagem de cobrança extremamente educada, profissional, empática e com muita bondade para o cliente {client_name}. "
        f"O serviço técnico realizado pela Serate Serviços foi '{service_desc}', no valor de R$ {amount:.2f}, "
        f"com data de vencimento para hoje ({due_date}). "
        f"Inclua a chave Pix '{pix_key}' para pagamento e solicite com carinho o envio do comprovativo."
    )
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return (
            f"Olá, {client_name}! Tudo bem com o senhor(a)? Aqui é do setor financeiro da Serate Serviços. "
            f"Passando com todo carinho para lembrar da fatura referente ao serviço de *{service_desc}*, "
            f"no valor de *R$ {amount:.2f}*, com vencimento para hoje ({due_date}).\n\n"
            f"Para facilitar, segue a nossa chave Pix: `{pix_key}`\n\n"
            f"Qualquer dúvida ou caso já tenha efetuado o pagamento, por favor nos avise. Muito obrigado e tenha um excelente dia!"
        )

def enviar_whatsapp_api(phone, message):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        return False
    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
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
    return response.status_code == 200

def verificar_e_enviar_cobrancas_diarias():
    """Executado automaticamente todos os dias para disparar apenas as faturas que vencem hoje."""
    hoje = date.today().isoformat()
    print(f"[{hoje}] A verificar faturas pendentes para envio automático...")
    
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
            print(f"Cobrança humanizada enviada com sucesso para {client_name}!")
        else:
            print(f"Falha ao enviar cobrança para {client_name}.")

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
            <input type="text" name="pix_key" required placeholder="Ex: 42500085000117">

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
                <div class="msg-box"><b>Mensagem Humanizada (Gemini):</b><br>{{ f[6] }}</div>
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
    """Webhook para atender clientes no chat com bondade e profissionalismo via Gemini."""
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
        data = request.json
        try:
            changes = data['entry'][0]['changes'][0]['value']
            if 'messages' in changes:
                msg_obj = changes['messages'][0]
                numero_cliente = msg_obj['from']
                msg_recebida = msg_obj['text']['body']

                prompt_chat = (
                    f"Você é o assistente virtual da Serate Serviços. Seja extremamente gentil, atencioso e profissional. "
                    f"Um cliente enviou a mensagem: '{msg_recebida}'. Responda tirando dúvidas sobre pagamentos, chaves Pix ou faturas com muita bondade e clareza."
                )
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt_chat,
                )
                resposta_ia = response.text
                enviar_whatsapp_api(numero_cliente, resposta_ia)
        except Exception as e:
            print("Erro no webhook:", e)
        return jsonify({"status": "recebido"}), 200

if __name__ == "__main__":
    criar_tabelas()
    
    # Executa a verificação diária às 08:00 da manhã
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=verificar_e_enviar_cobrancas_diarias, trigger="cron", hour=8, minute=0)
    scheduler.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
