from server.hashing_utils import get_password_hash
from server.sql_schemas import User
from server.user_database import Base, SessionLocal, engine

# Ensure the database tables are created
Base.metadata.create_all(bind=engine)


def delete_user(username: str):
    db = SessionLocal()
    try:
        # Look up the user by username
        user_to_delete = db.query(User).filter(User.username == username).first()

        if user_to_delete:
            # Delete the user if they exist
            db.delete(user_to_delete)
            db.commit()
            print(f"User {username} deleted successfully.")
        else:
            print(f"User {username} does not exist.")
    except Exception as e:
        print(f"Failed to delete user {username}: {e}")
        db.rollback()  # Rollback in case of any errors
    finally:
        db.close()


def add_user(username: str, email: str, full_name: str, password: str, disabled: bool = False):
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            print(f"User {username} already exists.")
            return

        hashed_password = get_password_hash(password)
        db_user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            disabled=disabled,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        print(f"User {username} added successfully.")
    except Exception as e:
        print(f"Failed to add user {username}: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(
        "Import add_user/delete_user from server.db_users; "
        "do not place credentials in source code."
    )
