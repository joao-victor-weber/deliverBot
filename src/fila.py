from .db import get_conn
from . import pedidos as pedidos_repo
from . import recibo
from . import whatsapp


def listar_fila():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT f.*, p.numero_pedido, p.total_pedido, p.forma_entrega, p.forma_pagamento, "
            "c.nome AS cliente_nome, c.telefone AS cliente_telefone "
            "FROM fila_preparo f "
            "JOIN pedidos p ON p.id = f.pedido_id "
            "JOIN clientes c ON c.id = p.cliente_id "
            "WHERE f.status NOT IN ('RETIRADO', 'ENTREGUE') "
            "ORDER BY f.posicao"
        ).fetchall()
    return [dict(r) for r in rows]


def _proximo_status(status_atual: str, forma_entrega: str) -> str | None:
    if status_atual == "AGUARDANDO":
        return "EM_PREPARO"

    if status_atual == "EM_PREPARO":
        return "PRONTO"

    if status_atual == "PRONTO":
        if forma_entrega == "ENTREGA":
            return "SAIU_PARA_ENTREGA"
        return "RETIRADO"

    if status_atual == "SAIU_PARA_ENTREGA":
        return "ENTREGUE"

    return None


def _status_pedido(status_fila: str) -> str:
    mapa = {
        "AGUARDANDO": "CONFIRMADO",
        "EM_PREPARO": "EM_PREPARO",
        "PRONTO": "PRONTO",
        "SAIU_PARA_ENTREGA": "SAIU_PARA_ENTREGA",
        "ENTREGUE": "ENTREGUE",
        "RETIRADO": "RETIRADO",
    }
    return mapa[status_fila]


def avancar_status(pedido_id: int) -> dict:
    """Avança o pedido e notifica automaticamente o cliente."""

    with get_conn() as conn:
        registro = conn.execute(
            """
            SELECT f.*, p.forma_entrega
            FROM fila_preparo f
            JOIN pedidos p ON p.id = f.pedido_id
            WHERE f.pedido_id = ?
            """,
            (pedido_id,),
        ).fetchone()

        if registro is None:
            raise ValueError("Pedido não encontrado na fila de preparo.")

        proximo = _proximo_status(
            registro["status"],
            registro["forma_entrega"],
        )

        if proximo is None:
            raise ValueError(
                f"Pedido já está no status final ({registro['status']})."
            )

        novo_status_pedido = _status_pedido(proximo)

        conn.execute(
            """
            UPDATE fila_preparo
            SET status = ?, atualizado_em = datetime('now')
            WHERE pedido_id = ?
            """,
            (proximo, pedido_id),
        )

        conn.execute(
            """
            UPDATE pedidos
            SET status = ?, atualizado_em = datetime('now')
            WHERE id = ?
            """,
            (novo_status_pedido, pedido_id),
        )

    pedido = pedidos_repo.obter_pedido(pedido_id)

    mensagem = recibo.montar_mensagem_status(
        pedido,
        novo_status_pedido,
    )

    whatsapp.enviar_mensagem(
        pedido["cliente_telefone"],
        mensagem,
    )

    pedidos_repo.registrar_mensagem(
        pedido["cliente_telefone"],
        "SAIDA",
        mensagem,
    )

    return pedido
