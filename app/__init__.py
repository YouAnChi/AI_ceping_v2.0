from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bootstrap import Bootstrap
import logging
from logging.handlers import RotatingFileHandler
import os

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login' # 指定登录视图的路由
login_manager.login_message_category = 'info' # 设置 flash 消息的类别
bootstrap = Bootstrap()

def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bootstrap.init_app(app)

    # Define and create UPLOADS_FOLDER if it doesn't exist
    app.config['UPLOADS_FOLDER'] = os.path.join(app.instance_path, 'uploads')
    if not os.path.exists(app.config['UPLOADS_FOLDER']):
        os.makedirs(app.config['UPLOADS_FOLDER'])

    # Define and create PROCESSED_FILES_FOLDER if it doesn't exist
    app.config['PROCESSED_FILES_FOLDER'] = os.path.join(app.instance_path, 'processed_files')
    if not os.path.exists(app.config['PROCESSED_FILES_FOLDER']):
        os.makedirs(app.config['PROCESSED_FILES_FOLDER'])

    # 创建实例文件夹 (如果上面没有创建instance_path的话)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # 配置日志
    log_file = app.config['LOG_FILE']
    handler = RotatingFileHandler(log_file, maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    return app

from app import models # 导入 models 模块，确保在 db 对象创建后导入，以便模型能够注册到 SQLAlchemy