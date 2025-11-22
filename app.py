import json
import sqlite3
from datetime import datetime
from typing import Dict

from flask import Flask, redirect, render_template, request, url_for

from db import (
    add_category,
    delete_category,
    delete_transaction,
    fetch_balance,
    fetch_category_totals,
    fetch_transaction_by_id,
    fetch_transactions_by_month,
    get_all_categories,
    init_db,
    insert_transaction,
    reset_all_data,
    update_category,
    update_transaction,
)

app = Flask(__name__)
init_db()


@app.route('/')
def home():
    balance = fetch_balance()
    return render_template('home.html', balance=balance)


@app.route('/transaction', methods=['GET', 'POST'])
def transaction():
    balance = fetch_balance()
    error_message = None
    form_values = {
        'amount': '',
        'movement': 'increase',
        'category': 'food',
        'memo': '',
    }

    if request.method == 'POST':
        amount_raw = request.form.get('amount', '').strip()
        movement = request.form.get('movement')
        category = request.form.get('category') if movement == 'decrease' else None
        memo = request.form.get('memo', '').strip() or None

        form_values.update(
            amount=amount_raw,
            movement=movement,
            category=category or 'food',
            memo=request.form.get('memo', ''),
        )

        try:
            amount = int(amount_raw)
        except ValueError:
            error_message = '金額は数字で入力してね。'
        else:
            if amount <= 0:
                error_message = '金額は1円以上を入力してね。'
            elif movement not in ('increase', 'decrease'):
                error_message = 'お金の動きを選んでね。'
            elif movement == 'decrease':
                if not category:
                    error_message = '出金のときはカテゴリを選んでね。'
                else:
                    valid_categories = [cat['id'] for cat in get_all_categories()]
                    if category not in valid_categories:
                        error_message = 'カテゴリの選択が正しくありません。'
                    elif amount > balance:
                        error_message = '残金より大きい出金はできません。'

        if error_message is None:
            insert_transaction(
                movement=movement,
                amount=amount,
                category=category if movement == 'decrease' else None,
                memo=memo,
            )
            return redirect(url_for('home'))

    categories = get_all_categories()
    return render_template(
        'transaction.html',
        balance=balance,
        error_message=error_message,
        form_values=form_values,
        categories=categories,
    )


@app.route('/history')
def history():
    selected_month = request.args.get('month')
    if not selected_month:
        selected_month = datetime.today().strftime('%Y-%m')
    else:
        try:
            datetime.fromisoformat(f'{selected_month}-01')
        except ValueError:
            selected_month = datetime.today().strftime('%Y-%m')

    transactions = fetch_transactions_by_month(selected_month)
    entries = [
        {
            'id': t.id,
            'display_date': t.occurred_at.strftime('%m/%d'),
            'movement': t.movement,
            'amount': t.amount,
            'category_label': t.category_label,
            'memo': t.memo,
            'sign': '+' if t.movement == 'increase' else '-',
        }
        for t in transactions
    ]

    category_totals = fetch_category_totals(selected_month)
    categories = get_all_categories()
    chart_data: Dict[str, list] = {
        'labels': [cat['label'] for cat in categories],
        'values': [category_totals.get(cat['id'], 0) for cat in categories],
    }

    return render_template(
        'history.html',
        entries=entries,
        chart_data=json.dumps(chart_data, ensure_ascii=False),
        selected_month=selected_month,
    )


@app.route('/transaction/<int:transaction_id>/edit', methods=['GET', 'POST'])
def edit_transaction(transaction_id: int):
    transaction = fetch_transaction_by_id(transaction_id)
    if transaction is None:
        return redirect(url_for('history'))

    balance = fetch_balance()
    # 編集対象のトランザクションを除外して残高を計算
    if transaction.movement == 'increase':
        balance_without_this = balance - transaction.amount
    else:
        balance_without_this = balance + transaction.amount

    error_message = None
    form_values = {
        'amount': str(transaction.amount),
        'movement': transaction.movement,
        'category': transaction.category or 'food',
        'memo': transaction.memo or '',
    }

    if request.method == 'POST':
        amount_raw = request.form.get('amount', '').strip()
        movement = request.form.get('movement')
        category = request.form.get('category') if movement == 'decrease' else None
        memo = request.form.get('memo', '').strip() or None

        form_values.update(
            amount=amount_raw,
            movement=movement,
            category=category or 'food',
            memo=request.form.get('memo', ''),
        )

        try:
            amount = int(amount_raw)
        except ValueError:
            error_message = '金額は数字で入力してね。'
        else:
            if amount <= 0:
                error_message = '金額は1円以上を入力してね。'
            elif movement not in ('increase', 'decrease'):
                error_message = 'お金の動きを選んでね。'
            elif movement == 'decrease':
                if not category:
                    error_message = '出金のときはカテゴリを選んでね。'
                else:
                    valid_categories = [cat['id'] for cat in get_all_categories()]
                    if category not in valid_categories:
                        error_message = 'カテゴリの選択が正しくありません。'
                    elif amount > balance_without_this:
                        error_message = '残金より大きい出金はできません。'

        if error_message is None:
            update_transaction(
                transaction_id,
                movement=movement,
                amount=amount,
                category=category if movement == 'decrease' else None,
                memo=memo,
            )
            return redirect(url_for('history', month=transaction.occurred_at.strftime('%Y-%m')))

    categories = get_all_categories()
    return render_template(
        'edit_transaction.html',
        transaction_id=transaction_id,
        balance=balance_without_this,
        error_message=error_message,
        form_values=form_values,
        categories=categories,
    )


@app.route('/transaction/<int:transaction_id>/delete', methods=['POST'])
def delete_transaction_route(transaction_id: int):
    transaction = fetch_transaction_by_id(transaction_id)
    if transaction is not None:
        delete_transaction(transaction_id)
        return redirect(url_for('history', month=transaction.occurred_at.strftime('%Y-%m')))
    return redirect(url_for('history'))


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'reset_all':
            reset_all_data()
            return redirect(url_for('home'))
        
        elif action == 'add_category':
            category_id = request.form.get('category_id', '').strip()
            label = request.form.get('label', '').strip()
            if category_id and label:
                try:
                    add_category(category_id, label)
                except sqlite3.IntegrityError:
                    pass  # 既に存在する場合は無視
            return redirect(url_for('settings'))
        
        elif action == 'update_category':
            category_id = request.form.get('category_id')
            new_label = request.form.get('label', '').strip()
            if category_id and new_label:
                update_category(category_id, new_label)
            return redirect(url_for('settings'))
        
        elif action == 'delete_category':
            category_id = request.form.get('category_id')
            if category_id:
                delete_category(category_id)
            return redirect(url_for('settings'))
    
    categories = get_all_categories()
    return render_template('settings.html', categories=categories)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
