from flask import Flask, render_template_string, request, redirect, url_for, jsonify
import sqlite3
import os
import requests
from google import genai

app = Flask(__name__)
DB_NAME = "cobrancas.db"

# Inicializa o cliente do Gemini e credenciais da Meta
client = genai.Client()
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")

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
    """Gera uma abordagem profissional e humanizada utilizando o Gemini."""
    prompt = (
        f"Crie uma mensagem de cobrança educada, profissional e amigável para o cliente {client_name}. "
        f"O serviço realizado pela Serate Serviços foi '{service_desc}', no valor de R$ {amount:.2f}, "
        f"com data de vencimento para {due_date}. "
        f"Inclua a chave Pix '{pix_key}' para pagamento e solicite o envio do comprovativo."
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return (
            f"Olá, {client_name}! Tudo bem? Aqui é do setor financeiro da Serate Serviços. "
            f"Passando para lembrar da fatura referente ao serviço de *{service_desc}*, "
            f"no valor de *R$ {amount:.2f}*, com vencimento para {due_date}.\n\n"
            f"Chave Pix: `{pix_key}`\nObrigado!"
        )

def enviar_whatsapp_api(phone, message):
    """Envia a mensagem de forma automática via API Oficial do WhatsApp (Meta)."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print("Credenciais da API do WhatsApp não configuradas.")
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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gestor de Cobranças com IA - Serate Serviços</title>
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
        .status-enviado { color: #27ae60; font-weight: bold; margin-top: 10px; display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🤖 Serate Serviços - IA Autónoma</h2>
        <form method="POST">
            <input type="hidden" name="acao" value="cadastrar">
            <label>Nome do Cliente:</label>
            <input type="text" name="client_name" required placeholder="Ex: Carlos Silva">

            <label>WhatsApp (com DDI e DDD):</label>
            <input type="text" name="client_phone" required placeholder="Ex: 5591999998888">

            <label>Descrição do Serviço:</label>
            <input type="text" name="service_desc" required placeholder="Ex: Instalação de Ar Condicionado">

            <label>Valor (R$):</label>
            <input type="number" step="0.01" name="amount" required placeholder="Ex: 250.00">

            <label>Data de Vencimento:</label>
            <input type="date" name="due_date" required>

            <label>Chave Pix:</label>
            <input type="text" name="pix_key" required placeholder="Ex: 42500085000117">

            <button type="submit">Cadastrar e Enviar por WhatsApp</button>
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
                <strong>Vencimento:</strong> {{ f[4] }}<br>
                <div class="msg-box"><b>Mensagem Gemini:</b><br>{{ f[6] }}</div>
                <span class="status-enviado">🚀 Enviado automaticamente via API</span>
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

            # Gera a mensagem inteligente via Gemini
            ai_msg = gerar_mensagem_ia(client_name, service_desc, amount, due_date, pix_key)

            # Dispara automaticamente pelo WhatsApp API
            enviar_whatsapp_api(client_phone, ai_msg)

            cursor.execute("""
                INSERT INTO faturas (client_name, client_phone, service_desc, amount, due_date, pix_key, status, ai_message)
                VALUES (?, ?, ?, ?, ?, ?, 'enviado', ?)
            """, (client_name, client_phone, service_desc, amount, due_date, pix_key, ai_msg))
            conexao.commit()

        elif acao == "apagar_tudo":
            cursor.execute("DELETE FROM faturas")
            conexao.commit()

        conexao.close()
        return redirect(url_for("index"))

    cursor.execute("SELECT id, client_name, service_desc, amount, due_date, status, client_phone, pix_key, ai_message FROM faturas ORDER BY id DESC")
    faturas = cursor.fetchall()
    conexao.close()

    return render_template_string(HTML_TEMPLATE, faturas=faturas)

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    """Rota para receber as mensagens dos clientes e responder com o Gemini de forma autónoma."""
    if request.method == "GET":
        verify_token = "serate_token_secreto"
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode and token == verify_token:
            return challenge, 200
        return "Erro de verificação", 403

    elif request.method == "POST":
        data = request.json
        try:
            changes = data['entry'][0]['changes'][0]['value']
            if 'messages' in changes:
                msg_obj = changes['messages'][0]
                numero_cliente = msg_obj['from']
                msg_recebida = msg_obj['text']['body']

                # Contexto para a IA atuar como assistente financeiro da Serate Serviços
                prompt_chat = (
                    f"Você é o assistente virtual da Serate Serviços. Um cliente enviou a seguinte mensagem: '{msg_recebida}'. "
                    f"Responda de forma educada, prestativa e objetiva, tirando dúvidas sobre pagamentos, faturas ou chaves Pix."
                )
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt_chat,
                )
                resposta_ia = response.text

                # Responde de volta automaticamente ao cliente pelo WhatsApp
                enviar_whatsapp_api(numero_cliente, resposta_ia)
        except Exception as e:
            print("Erro no webhook:", e)
        return jsonify({"status": "recebido"}), 200

if __name__ == "__main__":
    criar_tabelas()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
