"""Paged presentation of existing cards; no model calls or new prioritization."""

from math import ceil

from app.storage.database import get_connection
from app.storage.suggestions import COLUMNS, _reactivate_due, _row_to_dict

# General cards stay independent; no invented relationship between unrelated topics.
_GROUPS = """SELECT thread_id, CASE WHEN thread_id IS NULL THEN id ELSE 0 END AS single_id,
                    MAX(priority) AS priority, MIN(suggested_date) AS suggested_date,
                    MIN(created_at) AS first_created, MIN(id) AS first_id, COUNT(*) AS card_count
             FROM suggestions WHERE status = %s
             GROUP BY thread_id, CASE WHEN thread_id IS NULL THEN id ELSE 0 END"""


def list_today(*, status="open", page=1, groups_per_page=10, mark_surfaced=False):
    if status not in ("open", "deferred"):
        raise ValueError("Heute zeigt offene oder zurückgestellte Meldungen.")
    if type(page) is not int or page < 1 or type(groups_per_page) is not int or not 1 <= groups_per_page <= 50:
        raise ValueError("Seite und Seitengröße sind ungültig.")
    with get_connection() as conn:
        with conn.cursor() as cur:
            _reactivate_due(cur)
            cur.execute(f"SELECT COUNT(*), COALESCE(SUM(card_count), 0) FROM ({_GROUPS}) groups", (status,))
            group_count, total_count = map(int, cur.fetchone())
            page_count = max(1, ceil(group_count / groups_per_page))
            page = min(page, page_count)
            cur.execute(f"""SELECT g.thread_id, g.single_id, g.card_count, t.title
                            FROM ({_GROUPS}) g LEFT JOIN threads t ON t.id = g.thread_id
                            ORDER BY g.priority DESC NULLS LAST, g.suggested_date ASC NULLS LAST,
                                     g.first_created, g.first_id LIMIT %s OFFSET %s""",
                        (status, groups_per_page, (page - 1) * groups_per_page))
            groups = [{"thread_id": row[0], "single_id": row[1], "count": row[2],
                       "title": row[3], "cards": []} for row in cur.fetchall()]
            lookup = {(group["thread_id"], group["single_id"]): group for group in groups}
            thread_ids = [group["thread_id"] for group in groups if group["thread_id"] is not None]
            single_ids = [group["single_id"] for group in groups if group["thread_id"] is None]
            if groups:
                cur.execute(f"""SELECT {COLUMNS} FROM suggestions WHERE status = %s
                                AND (thread_id = ANY(%s) OR id = ANY(%s))
                                ORDER BY priority DESC NULLS LAST, suggested_date ASC NULLS LAST,
                                         created_at, id""", (status, thread_ids, single_ids))
                cards = [_row_to_dict(row) for row in cur.fetchall()]
                for card in cards:
                    key = (card["thread_id"], card["id"] if card["thread_id"] is None else 0)
                    lookup[key]["cards"].append(card)
                if mark_surfaced and status == "open":
                    ids = [card["id"] for card in cards if card["delivery_status"] == "pending"]
                    if ids:
                        cur.execute("""UPDATE suggestions SET delivery_status = 'surfaced', updated_at = NOW()
                                       WHERE id = ANY(%s) AND status = 'open' AND delivery_status = 'pending'
                                       RETURNING id, updated_at""", (ids,))
                        surfaced = dict(cur.fetchall())
                        for card in cards:
                            if card["id"] in surfaced:
                                card.update(delivery_status="surfaced", updated_at=surfaced[card["id"]])
    return {"groups": groups, "total_count": total_count, "group_count": group_count,
            "page": page, "page_count": page_count}
