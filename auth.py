import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import User

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-key-change-it-in-production-0123456789")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=24)
    return jwt.encode({"sub": user.username, "exp": exp}, SECRET_KEY, algorithm="HS256")


def user_from_token(token: str, db: Session) -> User:
    try:
        username = jwt.decode(token, SECRET_KEY, algorithms=["HS256"]).get("sub")
    except jwt.PyJWTError:
        raise HTTPException(401, "Недействительный токен")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    return user


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется вход")
    return user_from_token(authorization[7:], db)


def get_user_sse(token: str = Query(None), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(401, "Требуется вход")
    return user_from_token(token, db)


def require_passenger(user: User = Depends(get_current_user)) -> User:
    if user.role != "passenger":
        raise HTTPException(403, "Только для пассажира")
    return user


def require_driver(user: User = Depends(get_current_user)) -> User:
    if user.role != "driver":
        raise HTTPException(403, "Только для водителя")
    return user
