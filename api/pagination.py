"""Páginas de consultas cerradas con orden estable y recuento del filtro completo."""

from math import ceil

from servidor.database import fetch_all


def paginate_query(conn, query, params, *, order_by, page, page_size):
    """Cuenta y obtiene la página en una consulta; reajusta páginas que hayan quedado vacías."""
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("La página o su tamaño no son válidos.")
    # query y order_by proceden exclusivamente de consultas internas, nunca del cliente.
    sql = f"SELECT result.*, COUNT(*) OVER() AS _page_total FROM ({query}) AS result ORDER BY {order_by} LIMIT %s OFFSET %s"
    columns, rows = fetch_all(conn, sql, (*params, page_size, (page - 1) * page_size))
    total = int(rows[0][-1]) if rows else 0
    if not rows and page > 1:
        _, counts = fetch_all(conn, f"SELECT COUNT(*) FROM ({query}) AS result", params)
        total = int(counts[0][0])
        page = min(page, max(1, ceil(total / page_size)))
        if total:
            columns, rows = fetch_all(
                conn, sql, (*params, page_size, (page - 1) * page_size)
            )
    return {
        "columns": columns[:-1],
        "rows": [row[:-1] for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, ceil(total / page_size)),
    }
