from flask import Flask, jsonify, redirect, render_template, request, url_for

from . import bot, cardapio, config, fila, pedidos, recibo, viacep, whatsapp
from .db import init_db
from .links import link_valido, marcar_link_usado

app = Flask(__name__, template_folder="../web/templates")


@app.before_request
def _garantir_banco():
    init_db()


# ---------------------------------------------------------------------------
# Webhook do WhatsApp (Meta Cloud API)
# ---------------------------------------------------------------------------

@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    modo = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    desafio = request.args.get("hub.challenge")

    if modo == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN:
        return desafio, 200
    return "Token de verificação inválido", 403


@app.route("/webhook", methods=["POST"])
def receber_webhook():
    payload = request.get_json(silent=True) or {}
    dados = whatsapp.extrair_mensagem_recebida(payload)

    if dados is None:
        # Pode ser um evento de status (entregue/lido) ou payload vazio; apenas confirma o recebimento.
        return jsonify({"status": "ignorado"}), 200

    telefone, texto, nome = dados["telefone"], dados["texto"], dados["nome"]
    pedidos.registrar_mensagem(telefone, "ENTRADA", texto)

    resposta = bot.processar_mensagem(telefone, texto)
    whatsapp.enviar_mensagem(telefone, resposta)
    pedidos.registrar_mensagem(telefone, "SAIDA", resposta)

    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# Webhook do WAHA (WhatsApp HTTP API self-hosted via Docker, login por QR)
# Configure no WAHA: POST /api/sessions -> config.webhooks.url = SEU_DOMINIO/webhook/waha
# ---------------------------------------------------------------------------

@app.route("/webhook/waha", methods=["POST"])
def receber_webhook_waha():
    payload = request.get_json(silent=True) or {}
    dados = whatsapp.extrair_mensagem_recebida_waha(payload)

    if dados is None:
        # Outros eventos do WAHA (session.status, message.ack, etc.) são ignorados aqui.
        return jsonify({"status": "ignorado"}), 200

    telefone, texto, nome = dados["telefone"], dados["texto"], dados["nome"]
    pedidos.registrar_mensagem(telefone, "ENTRADA", texto)

    resposta = bot.processar_mensagem(telefone, texto)
    whatsapp.enviar_mensagem(telefone, resposta)
    pedidos.registrar_mensagem(telefone, "SAIDA", resposta)

    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# API interna usada pelo workflow do N8N (veja n8n/deliverybot-waha.json).
# O N8N recebe o webhook do WAHA, chama este endpoint para saber o que
# responder (usa a MESMA regra de negócio do bot.py, sem duplicar nada) e
# então manda a resposta pro WAHA por conta própria.
# ---------------------------------------------------------------------------

@app.route("/api/bot/mensagem", methods=["POST"])
def api_processar_mensagem():
    dados = request.get_json(silent=True) or {}
    telefone = whatsapp._numero_limpo(dados.get("telefone", ""))
    texto = (dados.get("texto") or "").strip()
    nome = dados.get("nome") or "Cliente"

    if not telefone:
        return jsonify({"erro": "telefone é obrigatório"}), 400

    pedidos.registrar_mensagem(telefone, "ENTRADA", texto)
    resposta = bot.processar_mensagem(telefone, texto)
    pedidos.registrar_mensagem(telefone, "SAIDA", resposta)

    return jsonify({"telefone": telefone, "resposta": resposta})


# ---------------------------------------------------------------------------
# Atalho só para TESTE LOCAL: simula o cliente digitando "2" no WhatsApp,
# sem precisar de credenciais da Meta nem do webhook real. Gera um link único
# de verdade e já redireciona pra ele, pra você mesmo escolher os itens.
# ---------------------------------------------------------------------------

@app.route("/testar", methods=["GET"])
def testar_localmente():
    telefone_teste = request.args.get("telefone", "5547999990000")
    resposta = bot.processar_mensagem(telefone_teste, "2")
    pedidos.registrar_mensagem(telefone_teste, "SAIDA", resposta)
    link = resposta.replace("Faça o seu pedido em ", "").strip()
    token = link.rsplit("/", 1)[-1]
    return redirect(url_for("pagina_pedido", token=token))


# ---------------------------------------------------------------------------
# Link único de pedido: GET mostra o cardápio, POST cria o pedido
# ---------------------------------------------------------------------------

@app.route("/m/<token>", methods=["GET"])
def pagina_pedido(token):
    ok, mensagem, link = link_valido(token)
    if not ok:
        return render_template("link_invalido.html", mensagem=mensagem), 410

    produtos = cardapio.listar_produtos_ativos()
    grupos = cardapio.agrupar_por_categoria(produtos)
    return render_template(
        "pedido.html",
        token=token,
        grupos=grupos,
        nome_restaurante=config.NOME_RESTAURANTE,
        taxa_entrega=config.TAXA_ENTREGA,
    )


@app.route("/m/<token>", methods=["POST"])
def enviar_pedido(token):
    ok, mensagem, link = link_valido(token)
    if not ok:
        return render_template("link_invalido.html", mensagem=mensagem), 410

    telefone = link["telefone"]
    nome_cliente = request.form.get("nome", "Cliente").strip() or "Cliente"
    forma_pagamento = request.form.get("forma_pagamento", "Dinheiro")
    forma_entrega = request.form.get("forma_entrega", "RETIRADA BALCAO")
    cep = request.form.get("cep", "").strip()

    endereco = ""
    if forma_entrega == "ENTREGA":
        ok_cep, msg_cep, dados_cep = viacep.validar_area_entrega(cep, config.CIDADES_ATENDIDAS)
        if not ok_cep:
            produtos = cardapio.listar_produtos_ativos()
            grupos = cardapio.agrupar_por_categoria(produtos)
            return render_template(
                "pedido.html",
                token=token,
                grupos=grupos,
                nome_restaurante=config.NOME_RESTAURANTE,
                taxa_entrega=config.TAXA_ENTREGA,
                erro=msg_cep,
            ), 400
        endereco = viacep.endereco_formatado(dados_cep)

    itens = []
    for chave, valor in request.form.items():
        if chave.startswith("qtd_") and valor and int(valor) > 0:
            produto_id = int(chave.replace("qtd_", ""))
            itens.append({"produto_id": produto_id, "quantidade": int(valor)})

    if not itens:
        produtos = cardapio.listar_produtos_ativos()
        grupos = cardapio.agrupar_por_categoria(produtos)
        return render_template(
            "pedido.html",
            token=token,
            grupos=grupos,
            nome_restaurante=config.NOME_RESTAURANTE,
            taxa_entrega=config.TAXA_ENTREGA,
            erro="Selecione ao menos um item antes de enviar o pedido.",
        ), 400

    pedido = pedidos.criar_pedido(
        telefone=telefone,
        nome_cliente=nome_cliente,
        itens=itens,
        forma_pagamento=forma_pagamento,
        forma_entrega=forma_entrega,
        cep=cep,
        endereco=endereco,
    )
    marcar_link_usado(token, pedido["id"])

    mensagem_confirmacao = recibo.montar_mensagem_confirmacao(pedido)
    cupom = recibo.montar_recibo(pedido)
    whatsapp.enviar_mensagem(telefone, mensagem_confirmacao)
    whatsapp.enviar_mensagem(telefone, cupom)
    pedidos.registrar_mensagem(telefone, "SAIDA", mensagem_confirmacao)
    pedidos.registrar_mensagem(telefone, "SAIDA", cupom)

    mensagem_status = recibo.montar_mensagem_status(pedido, "CONFIRMADO")
    whatsapp.enviar_mensagem(telefone, mensagem_status)
    pedidos.registrar_mensagem(telefone, "SAIDA", mensagem_status)

    return render_template("pedido_sucesso.html", pedido=pedido)


# ---------------------------------------------------------------------------
# Painel da cozinha / fila de preparo
# ---------------------------------------------------------------------------

@app.route("/cozinha", methods=["GET"])
def painel_cozinha():
    return render_template("cozinha.html", fila=fila.listar_fila())


@app.route("/cozinha/avancar/<int:pedido_id>", methods=["POST"])
def avancar_pedido(pedido_id):
    try:
        fila.avancar_status(pedido_id)
    except ValueError as e:
        return str(e), 400
    return redirect(url_for("painel_cozinha"))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)

