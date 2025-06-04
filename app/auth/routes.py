from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.auth import bp
from app.auth.forms import LoginForm, RegistrationForm
from app.models import User, UserActivityLog
from datetime import datetime

def log_user_activity(user_id, action, details=None):
    """辅助函数，用于记录用户活动。"""
    try:
        ip_address = request.remote_addr
        activity = UserActivityLog(
            user_id=user_id,
            action=action,
            details=details,
            ip_address=ip_address,
            timestamp=datetime.utcnow()
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error logging user activity: {e}")
        db.session.rollback() # 出错时回滚

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            user = User(username=form.username.data, email=form.email.data if form.email.data else None)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            # 注册成功后立即记录活动，此时 user.id 已生成
            log_user_activity(user.id, 'register', f'User {user.username} registered.')
            flash('恭喜您，注册成功！现在可以登录了。', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error during registration: {e}")
            flash('注册过程中发生错误，请稍后重试。', 'danger')
    return render_template('auth/register.html', title='注册', form=form)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('用户名或密码无效。', 'danger')
            # 记录失败的登录尝试，但不暴露过多信息
            log_user_activity(None, 'login_failed', f'Failed login attempt for username: {form.username.data}')
            return redirect(url_for('auth.login'))
        
        login_user(user, remember=form.remember_me.data)
        user.last_login = datetime.utcnow() # 更新最后登录时间
        db.session.commit()
        log_user_activity(user.id, 'login', f'User {user.username} logged in.')
        
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('main.index')
        flash(f'欢迎回来, {user.username}!', 'success')
        return redirect(next_page)
    return render_template('auth/login.html', title='登录', form=form)

@bp.route('/logout')
@login_required
def logout():
    if current_user.is_authenticated:
        log_user_activity(current_user.id, 'logout', f'User {current_user.username} logged out.')
    logout_user()
    flash('您已成功退出登录。', 'info')
    return redirect(url_for('main.index'))