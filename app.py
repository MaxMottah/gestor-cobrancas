from flask import Flask, render_template_string, request, redirect, url_for
import sqlite3
import urllib.parse
import os
from google import genai

app = Flask(__name__)
DB_NAME = "cobrancas.db"

# Inicializa o cliente do Gemini usando a variável de ambiente GEMINI_API_KEY
client = genai.Client()

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
        # Fallback caso ocorra algum erro na API
        return (
            f"Olá, {client_name}! Tudo bem? Aqui é do setor financeiro da Serate Serviços. "
            f"Passando para lembrar da fatura referente ao serviço de *{service_desc}*, "
            f"no valor de *R$ {amount:.2f}*, com vencimento para {due_date}.\n\n"
            f"Chave Pix: `{pix_key}`\nObrigado!"
        )

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gestor de Cobranças com IA</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        h2 { color: #2c3e50; text-align: center; }
        label { font-weight: bold; display: block; margin-top: 10px; font-size: 14px; }
        input, button { width: 100%; padding: 10px; margin-top: 5px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; font-size: 16px; }
        button { background-color: #27ae60; color: white; border: none; font-weight: bold; margin-top: 20px; cursor: pointer; }
        button:hover { background-color: #219653; }
        .btn-danger { background-color: #e74c3c; margin-top: 10px; }
        .btn-danger:hover { background-color: #c0392b; }
        .card { background: #fff; border-left: 5px solid #3498db; padding: 15px; margin-top: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-radius: 4px; }
        .msg-box { background: #f8f9fa; border: 1px dashed #cbd5e1; padding: 10px; font-size: 13px; margin-top: 8px; border-radius: 4px; white-space: pre-wrap; }
        .btn-zap { display: block; background-color: #25D366; color: white; text-align: center; padding: 8px; margin-top: 10px; border-radius: 5px; text-decoration: none; font-weight: bold; font-size: 14px; }
        .btn-zap:hover { background-color: #1EBE5D; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🤖 Gestor de Cobranças com IA</h2>
        <form method="POST">
            <input type="hidden" name="acao" value="cadastrar">
            <label>Nome do Cliente:</label>
            <input type="text" name="client_name" required placeholder="Ex: Carlos Silva">

            <label>WhatsApp (com DDI e DDD):</label>
            <input type="text" name="client_phone" required placeholder="Ex: 5591999998888">

            <label>Descrição do Serviço:</label>
            <input type="text" name="service_desc" required placeholder="Ex: Manutenção de Ar">

            <label>Valor (R$):</label>
            <input type="number" step="0.01" name="amount" required placeholder="Ex: 250.00">

            <label>Data de Vencimento:</label>
            <input type="date" name="due_date" required>

            <label>A sua Chave Pix:</label>
            <input type="text" name="pix_key" required placeholder="Ex: sua-chave-pix">

            <button type="submit">Gerar Mensagem com IA</button>
        </form>

        <form method="POST" onsubmit="return confirm('Tem a certeza que deseja apagar todas as faturas?');">
            <input type="hidden" name="acao" value="apagar_tudo">
            <button type="submit" class="btn-danger">🗑️ Apagar Todas as Faturas</button>
        </form>

        <div style="margin-top: 30px;">
            <h3>📋 Faturas Registadas</h3>
            {% for f in faturas %}
            <div class="card">
                <strong>Cliente:</strong> {{ f[1] }}<br>
                <strong>Serviço:</strong> {{ f[2] }} | <strong>Valor:</strong> R$ {{ "%.2f"|format(f[3]) }}<br>
                <strong>Vencimento:</strong> {{ f[4] }} | <strong>Status:</strong> {{ f[5] }}<br>

                <div class="msg-box"><b>Texto Criado pela IA:</b><br>{{ f[6] }}</div>

                <a class="btn-zap" href="{{ f[7] }}" target="_blank">📲 Enviar Mensagem no WhatsApp</a>
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

    cursor.execute("SELECT id, client_name, service_desc, amount, due_date, status, client_phone, pix_key, ai_message FROM faturas ORDER BY id DESC")
    dados_brutos = cursor.fetchall()
    conexao.close()

    faturas = []
    for f in dados_brutos:
        link = f"https://api.whatsapp.com/send?phone={f[6]}&text={urllib.parse.quote(f[8])}"
        faturas.append((f[0], f[1], f[2], f[3], f[4], f[5], f[8], link))

    return render_template_string(HTML_TEMPLATE, faturas=faturas)

if __name__ == "__main__":
    criar_tabelas()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
