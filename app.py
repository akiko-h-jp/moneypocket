import json
import os
import sqlite3
from datetime import datetime
from typing import Dict

from flask import Flask, redirect, render_template, request, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

from db import (
    add_category,
    create_user,
    delete_category,
    delete_transaction,
    fetch_balance,
    fetch_category_totals,
    fetch_transaction_by_id,
    fetch_transactions_by_month,
    get_all_categories,
    get_category_label,
    get_user_by_id,
    get_user_by_username,
    init_db,
    insert_transaction,
    reset_all_data,
    update_category,
    update_transaction,
    verify_password,
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Flask-Loginの設定
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'ログインが必要です。'


# Userモデル
class User(UserMixin):
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    user_data = get_user_by_id(int(user_id))
    if user_data:
        return User(user_data['id'], user_data['username'])
    return None


init_db()


@app.route('/test')
def test():
    return 'Server is working!'


@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            if not username or not password:
                flash('ユーザー名とパスワードを入力してください。', 'error')
                return render_template('login.html')
            
            user_data = get_user_by_username(username)
            if user_data and verify_password(user_data['password_hash'], password):
                user = User(user_data['id'], user_data['username'])
                login_user(user)
                return redirect(url_for('home'))
            else:
                flash('ユーザー名またはパスワードが正しくありません。', 'error')
        
        return render_template('login.html')
    except Exception as e:
        return f'Error: {str(e)}', 500


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        
        if not username or not password:
            flash('ユーザー名とパスワードを入力してください。', 'error')
            return render_template('register.html')
        
        if password != password_confirm:
            flash('パスワードが一致しません。', 'error')
            return render_template('register.html')
        
        if len(password) < 4:
            flash('パスワードは4文字以上にしてください。', 'error')
            return render_template('register.html')
        
        user_id = create_user(username, password)
        if user_id:
            flash('登録が完了しました。ログインしてください。', 'success')
            return redirect(url_for('login'))
        else:
            flash('このユーザー名は既に使用されています。', 'error')
    
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def home():
    balance = fetch_balance(current_user.id)
    return render_template('home.html', balance=balance)


@app.route('/transaction', methods=['GET', 'POST'])
@login_required
def transaction():
    user_id = current_user.id
    balance = fetch_balance(user_id)
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
                    valid_categories = [cat['id'] for cat in get_all_categories(user_id)]
                    if category not in valid_categories:
                        error_message = 'カテゴリの選択が正しくありません。'
                    elif amount > balance:
                        error_message = '残金より大きい出金はできません。'

        if error_message is None:
            insert_transaction(
                user_id=user_id,
                movement=movement,
                amount=amount,
                category=category if movement == 'decrease' else None,
                memo=memo,
            )
            return redirect(url_for('home'))

    categories = get_all_categories(user_id)
    return render_template(
        'transaction.html',
        balance=balance,
        error_message=error_message,
        form_values=form_values,
        categories=categories,
    )


@app.route('/history')
@login_required
def history():
    user_id = current_user.id
    selected_month = request.args.get('month')
    if not selected_month:
        selected_month = datetime.today().strftime('%Y-%m')
    else:
        try:
            datetime.fromisoformat(f'{selected_month}-01')
        except ValueError:
            selected_month = datetime.today().strftime('%Y-%m')

    transactions = fetch_transactions_by_month(user_id, selected_month)
    entries = [
        {
            'id': t.id,
            'display_date': t.occurred_at.strftime('%m/%d'),
            'movement': t.movement,
            'amount': t.amount,
            'category_label': get_category_label(user_id, t.category) if t.category else 'おこづかい',
            'memo': t.memo,
            'sign': '+' if t.movement == 'increase' else '-',
        }
        for t in transactions
    ]

    category_totals = fetch_category_totals(user_id, selected_month)
    categories = get_all_categories(user_id)
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
@login_required
def edit_transaction(transaction_id: int):
    user_id = current_user.id
    transaction = fetch_transaction_by_id(user_id, transaction_id)
    if transaction is None:
        return redirect(url_for('history'))

    balance = fetch_balance(user_id)
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
                    valid_categories = [cat['id'] for cat in get_all_categories(user_id)]
                    if category not in valid_categories:
                        error_message = 'カテゴリの選択が正しくありません。'
                    elif amount > balance_without_this:
                        error_message = '残金より大きい出金はできません。'

        if error_message is None:
            update_transaction(
                user_id,
                transaction_id,
                movement=movement,
                amount=amount,
                category=category if movement == 'decrease' else None,
                memo=memo,
            )
            return redirect(url_for('history', month=transaction.occurred_at.strftime('%Y-%m')))

    categories = get_all_categories(user_id)
    return render_template(
        'edit_transaction.html',
        transaction_id=transaction_id,
        balance=balance_without_this,
        error_message=error_message,
        form_values=form_values,
        categories=categories,
    )


@app.route('/transaction/<int:transaction_id>/delete', methods=['POST'])
@login_required
def delete_transaction_route(transaction_id: int):
    user_id = current_user.id
    transaction = fetch_transaction_by_id(user_id, transaction_id)
    if transaction is not None:
        delete_transaction(user_id, transaction_id)
        return redirect(url_for('history', month=transaction.occurred_at.strftime('%Y-%m')))
    return redirect(url_for('history'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user_id = current_user.id
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'reset_all':
            reset_all_data(user_id)
            return redirect(url_for('home'))
        
        elif action == 'add_category':
            category_id = request.form.get('category_id', '').strip()
            label = request.form.get('label', '').strip()
            if category_id and label:
                try:
                    add_category(user_id, category_id, label)
                except sqlite3.IntegrityError:
                    pass  # 既に存在する場合は無視
            return redirect(url_for('settings'))
        
        elif action == 'update_category':
            category_id = request.form.get('category_id')
            new_label = request.form.get('label', '').strip()
            if category_id and new_label:
                update_category(user_id, category_id, new_label)
            return redirect(url_for('settings'))
        
        elif action == 'delete_category':
            category_id = request.form.get('category_id')
            if category_id:
                delete_category(user_id, category_id)
            return redirect(url_for('settings'))
    
    categories = get_all_categories(user_id)
    return render_template('settings.html', categories=categories)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development' or True  # 開発中は常にデバッグモード
    app.run(host='0.0.0.0', port=port, debug=debug)
