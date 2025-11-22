from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List
from werkzeug.security import generate_password_hash, check_password_hash

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


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        # ユーザーテーブルの作成
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        
        # トランザクションテーブルの作成（user_idカラム付き）
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                occurred_at TEXT NOT NULL,
                movement TEXT NOT NULL CHECK(movement IN ('increase', 'decrease')),
                amount INTEGER NOT NULL CHECK(amount > 0),
                category TEXT,
                memo TEXT
            );
            """
        )
        
        # 既存のtransactionsテーブルにuser_idカラムがない場合は追加
        try:
            conn.execute("ALTER TABLE transactions ADD COLUMN user_id INTEGER")
        except sqlite3.OperationalError:
            pass  # カラムが既に存在する場合は無視
        
        # 既存のcategoriesテーブルにuser_idカラムがない場合は追加
        try:
            # まず、既存のテーブルにuser_idカラムがあるか確認
            cursor = conn.execute("PRAGMA table_info(categories)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'user_id' not in columns:
                conn.execute("ALTER TABLE categories ADD COLUMN user_id INTEGER")
                # 既存のカテゴリのuser_idをNULLに設定（全員共通）
                conn.execute("UPDATE categories SET user_id = NULL")
        except sqlite3.OperationalError:
            pass  # エラーが発生した場合は無視
        
        # カテゴリテーブルの作成（user_idカラム付き）
        # 既存のテーブルがある場合は、CREATE TABLE IF NOT EXISTSでスキップされる
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id TEXT NOT NULL,
                user_id INTEGER,
                label TEXT NOT NULL,
                display_order INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        
        conn.commit()
        
        # デフォルトカテゴリを初期化（user_id = NULLで全員共通）
        existing = conn.execute("SELECT COUNT(*) FROM categories WHERE user_id IS NULL").fetchone()[0]
        if existing == 0:
            for idx, (cat_id, label) in enumerate(DEFAULT_CATEGORIES):
                conn.execute(
                    "INSERT INTO categories (id, user_id, label, display_order) VALUES (?, ?, ?, ?)",
                    (cat_id, None, label, idx),
                )
            conn.commit()


def insert_transaction(*, user_id: int, movement: str, amount: int, category: str | None, memo: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO transactions (user_id, occurred_at, movement, amount, category, memo)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, datetime.now().isoformat(timespec='seconds'), movement, amount, category, memo),
        )
        conn.commit()


def fetch_balance(user_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN movement = 'increase' THEN amount ELSE -amount END), 0) AS balance
            FROM transactions
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return row['balance'] if row else 0


def fetch_transactions_by_month(user_id: int, month: str) -> List[Transaction]:
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
            WHERE user_id = ? AND occurred_at >= ? AND occurred_at < ?
            ORDER BY occurred_at ASC
            """,
            (user_id, start.isoformat(timespec='seconds'), end.isoformat(timespec='seconds')),
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


def fetch_category_totals(user_id: int, month: str) -> dict[str, int]:
    # 全てのカテゴリを取得（全員共通 + ユーザー固有）
    categories = get_all_categories(user_id)
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
            WHERE user_id = ? AND movement = 'decrease'
              AND occurred_at >= ? AND occurred_at < ?
            GROUP BY category
            """,
            (user_id, start.isoformat(timespec='seconds'), end.isoformat(timespec='seconds')),
        ).fetchall()

    for row in rows:
        key = row['category'] or 'other'
        if key not in totals:
            totals[key] = 0
        totals[key] = row['total']
    return totals


def fetch_transaction_by_id(user_id: int, transaction_id: int) -> Transaction | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, occurred_at, movement, amount, category, memo
            FROM transactions
            WHERE id = ? AND user_id = ?
            """,
            (transaction_id, user_id),
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
    user_id: int,
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
            WHERE id = ? AND user_id = ?
            """,
            (movement, amount, category, memo, transaction_id, user_id),
        )
        conn.commit()


def delete_transaction(user_id: int, transaction_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM transactions
            WHERE id = ? AND user_id = ?
            """,
            (transaction_id, user_id),
        )
        conn.commit()


def get_category_label(user_id: int, category_id: str) -> str | None:
    """全員共通のカテゴリ（user_id IS NULL）とユーザー固有のカテゴリから取得"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT label FROM categories WHERE id = ? AND (user_id IS NULL OR user_id = ?)",
            (category_id, user_id),
        ).fetchone()
        return row['label'] if row else None


def get_all_categories(user_id: int) -> List[dict[str, str | int | None]]:
    """全員共通のカテゴリ（user_id IS NULL）とユーザー固有のカテゴリを取得"""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, label, display_order FROM categories
            WHERE user_id IS NULL OR user_id = ?
            ORDER BY display_order, id
            """,
            (user_id,),
        ).fetchall()
        return [{'id': row['id'], 'user_id': row['user_id'], 'label': row['label'], 'display_order': row['display_order']} for row in rows]


def add_category(user_id: int, category_id: str, label: str) -> None:
    with get_connection() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(display_order), -1) FROM categories WHERE user_id = ? OR user_id IS NULL",
            (user_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO categories (id, user_id, label, display_order) VALUES (?, ?, ?, ?)",
            (category_id, user_id, label, max_order + 1),
        )
        conn.commit()


def update_category(user_id: int, category_id: str, new_label: str) -> None:
    with get_connection() as conn:
        # 全員共通のカテゴリ（user_id IS NULL）は更新できない
        conn.execute(
            "UPDATE categories SET label = ? WHERE id = ? AND user_id = ?",
            (new_label, category_id, user_id),
        )
        conn.commit()


def delete_category(user_id: int, category_id: str) -> None:
    with get_connection() as conn:
        # 全員共通のカテゴリ（user_id IS NULL）は削除できない
        # このカテゴリを使用しているトランザクションを「その他」に変更
        conn.execute(
            "UPDATE transactions SET category = 'other' WHERE user_id = ? AND category = ?",
            (user_id, category_id),
        )
        conn.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (category_id, user_id))
        conn.commit()


def reset_all_data(user_id: int) -> None:
    """特定のユーザーのデータをリセット（トランザクションとユーザー固有のカテゴリ）"""
    with get_connection() as conn:
        conn.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM categories WHERE user_id = ?", (user_id,))
        conn.commit()


# ユーザー認証関連の関数
def create_user(username: str, password: str) -> int | None:
    """ユーザーを作成し、ユーザーIDを返す。既に存在する場合はNoneを返す。"""
    with get_connection() as conn:
        try:
            password_hash = generate_password_hash(password)
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, datetime.now().isoformat(timespec='seconds')),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None  # ユーザー名が既に存在する


def get_user_by_username(username: str) -> dict | None:
    """ユーザー名でユーザーを取得"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row:
            return {'id': row['id'], 'username': row['username'], 'password_hash': row['password_hash']}
        return None


def get_user_by_id(user_id: int) -> dict | None:
    """ユーザーIDでユーザーを取得"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row:
            return {'id': row['id'], 'username': row['username']}
        return None


def verify_password(password_hash: str, password: str) -> bool:
    """パスワードを検証"""
    return check_password_hash(password_hash, password)
