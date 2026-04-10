from .db import Base, SessionLocal, engine
from .models import User
from .security import hash_password


def init_admin(user_id: int = 1, name: str = "admin", password: str = "admin123"):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user:
            return
        db.add(
            User(
                id=user_id,
                role="admin",
                name=name,
                student_no=f"admin-{user_id}",
                password_hash=hash_password(password),
            )
        )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    init_admin()
    print("Admin initialized: id=1, account=admin-1, password=admin123")
