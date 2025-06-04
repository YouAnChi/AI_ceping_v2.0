from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length
from app.models import User
from flask import current_app

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(message="请输入用户名。"), Length(min=3, max=64)])
    password = PasswordField('密码', validators=[DataRequired(message="请输入密码。")])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登录')

class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(message="请输入用户名。"), Length(min=3, max=64)])
    email = StringField('邮箱 (可选)', validators=[Email(message="请输入有效的邮箱地址。"), Length(max=120)], default=None, render_kw={"placeholder": "可选"})
    password = PasswordField('密码', validators=[DataRequired(message="请输入密码。"), Length(min=6, message="密码长度至少为6位")])
    password2 = PasswordField(
        '确认密码', validators=[DataRequired(message="请再次输入密码。"), EqualTo('password', message='两次输入的密码不一致。')])
    registration_key = StringField('邀请码', validators=[DataRequired(message="请输入邀请码。")])
    submit = SubmitField('注册')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('用户名已被注册，请使用其他用户名。')

    def validate_email(self, email):
        if email.data: # 仅当用户输入了邮箱时才校验
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('该邮箱已被注册，请使用其他邮箱。')

    def validate_registration_key(self, registration_key):
        if registration_key.data != current_app.config['REGISTRATION_KEY']:
            raise ValidationError('邀请码无效。')