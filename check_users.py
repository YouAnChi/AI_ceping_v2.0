from app import create_app, db
from app.models import User

app = create_app()

with app.app_context():
    print("Total users:", User.query.count())
    print("Admin users:", [(u.id, u.username, u.is_admin) for u in User.query.filter_by(is_admin=True).all()])