from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'money_pocket.db'


DEFAULT_CATEGORIES = [
    ('food', '食べ物'),
    ('fun', '遊び'),
    ('stationery', '文具'),
    ('oshikatsu', '推し活'),
    ('other', 'その他'),
]


@dataclass
class Transaction:
    id: int
    occurred_at: datetime
    movement: str
    amount: int
    category: str | None
    memo: str | None

    @property
    def category_label(self) -> str:
        if self.category is None:
            return 'おこづかい'
        label = get_category_label(self.category)
        return label if label else 'その他'


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                movement TEXT NOT NULL CHECK(movement IN ('increase', 'decrease')),
                amount INTEGER NOT NULL CHECK(amount > 0),
                category TEXT,
                memo TEXT
            );
            CREATE TABLE IF NOT EXISTS categories (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                display_order INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.commit()
        
        # デフォルトカテゴリを初期化
        existing = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if existing == 0:
            for idx, (cat_id, label) in enumerate(DEFAULT_CATEGORIES):
                conn.execute(
                    "INSERT INTO categories (id, label, display_order) VALUES (?, ?, ?)",
                    (cat_id, label, idx),
                )
            conn.commit()


def insert_transaction(*, movement: str, amount: int, category: str | None, memo: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO transactions (occurred_at, movement, amount, category, memo)
            VALUES (?, ?, ?, ?, ?)
            """,
            (datetime.now().isoformat(timespec='seconds'), movement, amount, category, memo),
        )
        conn.commit()


def fetch_balance() -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN movement = 'increase' THEN amount ELSE -amount END), 0) AS balance
            FROM transactions
            """,
        ).fetchone()
        return row['balance'] if row else 0


def fetch_transactions_by_month(month: str) -> List[Transaction]:
    start = datetime.fromisoformat(f"{month}-01")
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, occurred_at, movement, amount, category, memo
            FROM transactions
            WHERE occurred_at >= ? AND occurred_at < ?
            ORDER BY occurred_at ASC
            """,
            (start.isoformat(timespec='seconds'), end.isoformat(timespec='seconds')),
        ).fetchall()

    transactions: List[Transaction] = []
    for row in rows:
        transactions.append(
            Transaction(
                id=row['id'],
                occurred_at=datetime.fromisoformat(row['occurred_at']),
                movement=row['movement'],
                amount=row['amount'],
                category=row['category'],
                memo=row['memo'],
            )
        )
    return transactions


def fetch_category_totals(month: str) -> dict[str, int]:
    # 全てのカテゴリを取得
    categories = get_all_categories()
    totals = {cat['id']: 0 for cat in categories}

    start = datetime.fromisoformat(f"{month}-01")
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM transactions
            WHERE movement = 'decrease'
              AND occurred_at >= ? AND occurred_at < ?
            GROUP BY category
            """,
            (start.isoformat(timespec='seconds'), end.isoformat(timespec='seconds')),
        ).fetchall()

    for row in rows:
        key = row['category'] or 'other'
        if key not in totals:
            totals[key] = 0
        totals[key] = row['total']
    return totals


def fetch_transaction_by_id(transaction_id: int) -> Transaction | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, occurred_at, movement, amount, category, memo
            FROM transactions
            WHERE id = ?
            """,
            (transaction_id,),
        ).fetchone()

        if row is None:
            return None

        return Transaction(
            id=row['id'],
            occurred_at=datetime.fromisoformat(row['occurred_at']),
            movement=row['movement'],
            amount=row['amount'],
            category=row['category'],
            memo=row['memo'],
        )


def update_transaction(
    transaction_id: int,
    *,
    movement: str,
    amount: int,
    category: str | None,
    memo: str | None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE transactions
            SET movement = ?, amount = ?, category = ?, memo = ?
            WHERE id = ?
            """,
            (movement, amount, category, memo, transaction_id),
        )
        conn.commit()


def delete_transaction(transaction_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM transactions
            WHERE id = ?
            """,
            (transaction_id,),
        )
        conn.commit()


def get_category_label(category_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT label FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        return row['label'] if row else None


def get_all_categories() -> List[dict[str, str | int]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, label, display_order FROM categories ORDER BY display_order, id"
        ).fetchall()
        return [{'id': row['id'], 'label': row['label'], 'display_order': row['display_order']} for row in rows]


def add_category(category_id: str, label: str) -> None:
    with get_connection() as conn:
        max_order = conn.execute("SELECT COALESCE(MAX(display_order), -1) FROM categories").fetchone()[0]
        conn.execute(
            "INSERT INTO categories (id, label, display_order) VALUES (?, ?, ?)",
            (category_id, label, max_order + 1),
        )
        conn.commit()


def update_category(category_id: str, new_label: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE categories SET label = ? WHERE id = ?",
            (new_label, category_id),
        )
        conn.commit()


def delete_category(category_id: str) -> None:
    with get_connection() as conn:
        # このカテゴリを使用しているトランザクションを「その他」に変更
        conn.execute(
            "UPDATE transactions SET category = 'other' WHERE category = ?",
            (category_id,),
        )
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        conn.commit()


def reset_all_data() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM transactions")
        conn.commit()
