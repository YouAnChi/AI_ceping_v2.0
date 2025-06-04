from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Flask-Login 用户加载回调函数
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True, nullable=False)
    email = db.Column(db.String(120), unique=True, index=True, nullable=True) # 邮箱可以为空
    password_hash = db.Column(db.String(128), nullable=False)
    registered_on = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # 与 UserActivityLog 建立关系
    activities = db.relationship('UserActivityLog', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class UserActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    action = db.Column(db.String(128), nullable=False) # 例如 'login', 'logout', 'register', 'view_function1'
    details = db.Column(db.Text, nullable=True) # 存储额外信息，如页面URL，操作结果等
    ip_address = db.Column(db.String(45), nullable=True) # 记录用户IP地址

    def __repr__(self):
        return f'<Activity {self.action} by User {self.user_id} at {self.timestamp}>'