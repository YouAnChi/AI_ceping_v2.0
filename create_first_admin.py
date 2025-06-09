from app import create_app, db
from app.models import User
import os

app = create_app()

with app.app_context():
    # 检查是否已经存在管理员用户
    admin_exists = User.query.filter_by(is_admin=True).first()
    if admin_exists:
        print("已存在管理员用户，无需创建新的管理员。")
    else:
        # 从环境变量或直接设置管理员用户名和密码
        admin_username = os.environ.get('FLASK_ADMIN_USERNAME', 'lpd123456')
        admin_password = os.environ.get('FLASK_ADMIN_PASSWORD', '123456')
        admin_email = os.environ.get('FLASK_ADMIN_EMAIL', 'admin@example.com')

        new_admin = User(username=admin_username, email=admin_email, is_admin=True)
        new_admin.set_password(admin_password)
        db.session.add(new_admin)
        db.session.commit()
        print(f"成功创建第一个管理员用户：用户名 '{admin_username}', 密码 '{admin_password}'")