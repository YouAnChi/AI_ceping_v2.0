import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key'
    LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'app.log')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REGISTRATION_KEY = os.environ.get('REGISTRATION_KEY') or 'zhengrong'