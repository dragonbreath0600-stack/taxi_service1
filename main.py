import asyncio
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from auth import (create_token, get_current_user, get_user_sse, hash_password,
                  require_driver, require_passenger, verify_password)
from database import Base, engine, get_db
from models import Offer, Order, User
from sse import broker

Base.metadata.create_all(engine)
app = FastAPI(title="Сервис такси")


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=72)
    role: Literal["passenger", "driver"]


class LoginIn(BaseModel):
    username: str
    password: str


class OrderIn(BaseModel):
    origin: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)
    price: float = Field(gt=0)


class OfferIn(BaseModel):
    price: float = Field(gt=0)
    eta_minutes: int = Field(ge=1, le=1440)


def offer_out(offer):
    return {"id": offer.id, "driver": offer.driver.username, "price": offer.price,
            "eta_minutes": offer.eta_minutes, "status": offer.status}


def order_out(order, driver_id=None):
    data = {"id": order.id, "passenger": order.passenger.username, "origin": order.origin,
            "destination": order.destination, "price": order.price, "status": order.status,
            "selected_offer_id": order.selected_offer_id}
    if driver_id is None:
        data["offers"] = [offer_out(o) for o in order.offers]
    else:
        mine = [offer_out(o) for o in order.offers if o.driver_id == driver_id]
        data["my_offer"] = mine[0] if mine else None
    return data


def orders_query(db):
    return db.query(Order).options(
        selectinload(Order.offers).selectinload(Offer.driver), selectinload(Order.passenger))


def get_order(db, order_id):
    order = orders_query(db).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Заказ не найден")
    return order


def get_own_order(db, order_id, user):
    order = get_order(db, order_id)
    if order.passenger_id != user.id:
        raise HTTPException(403, "Это не ваш заказ")
    return order


def token_out(user):
    return {"access_token": create_token(user), "role": user.role}


@app.post("/api/auth/register", status_code=201)
async def register(data: RegisterIn, db: Session = Depends(get_db)):
    user = User(username=data.username.strip(), password_hash=hash_password(data.password), role=data.role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(409, "Это имя уже занято")
    return token_out(user)


@app.post("/api/auth/login")
async def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username.strip()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Неверный логин или пароль")
    return token_out(user)


@app.get("/api/me")
async def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}


@app.post("/api/orders", status_code=201)
async def create_order(data: OrderIn, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    order = Order(passenger_id=user.id, origin=data.origin.strip(),
                  destination=data.destination.strip(), price=data.price)
    db.add(order)
    db.commit()
    order = get_order(db, order.id)
    broker.send("order_created", {"order": order_out(order, 0)}, role="driver")
    return order_out(order)


@app.get("/api/orders/my")
async def my_orders(user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    orders = orders_query(db).filter(Order.passenger_id == user.id).order_by(Order.id.desc()).all()
    return [order_out(o) for o in orders]


@app.get("/api/orders/available")
async def available_orders(user: User = Depends(require_driver), db: Session = Depends(get_db)):
    orders = orders_query(db).filter(Order.status == "open").order_by(Order.id.desc()).all()
    return [order_out(o, user.id) for o in orders]


@app.get("/api/driver/trips")
async def driver_trips(user: User = Depends(require_driver), db: Session = Depends(get_db)):
    orders = (orders_query(db).join(Offer, Offer.id == Order.selected_offer_id)
              .filter(Offer.driver_id == user.id).order_by(Order.id.desc()).all())
    return [order_out(o, user.id) for o in orders]


@app.post("/api/orders/{order_id}/offers", status_code=201)
async def create_offer(order_id: int, data: OfferIn, user: User = Depends(require_driver),
                       db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order.status != "open":
        raise HTTPException(409, "Заказ уже занят или отменён")
    if any(o.driver_id == user.id for o in order.offers):
        raise HTTPException(409, "Вы уже откликались на этот заказ")
    offer = Offer(order_id=order.id, driver_id=user.id, price=data.price, eta_minutes=data.eta_minutes)
    db.add(offer)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(409, "Вы уже откликались на этот заказ")
    broker.send("offer_created", {"order_id": order.id, "offer": offer_out(offer)}, user_id=order.passenger_id)
    return offer_out(offer)


@app.post("/api/orders/{order_id}/offers/{offer_id}/select")
async def select_offer(order_id: int, offer_id: int, user: User = Depends(require_passenger),
                       db: Session = Depends(get_db)):
    order = get_own_order(db, order_id, user)
    offer = next((o for o in order.offers if o.id == offer_id), None)
    if not offer:
        raise HTTPException(404, "Отклик не найден")
    if order.status != "open":
        raise HTTPException(409, "Заказ уже не открыт")
    order.status = "assigned"
    order.selected_offer_id = offer.id
    for o in order.offers:
        o.status = "accepted" if o.id == offer.id else "rejected"
    db.commit()
    order = get_order(db, order_id)
    broker.send("offer_accepted", {"order": order_out(order, offer.driver_id)}, user_id=offer.driver_id)
    broker.send("order_closed", {"order_id": order.id, "reason": "taken"}, role="driver", skip=offer.driver_id)
    return order_out(order)


@app.post("/api/orders/{order_id}/cancel")
async def cancel_order(order_id: int, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    order = get_own_order(db, order_id, user)
    if order.status not in ("open", "assigned"):
        raise HTTPException(409, "Заказ уже нельзя отменить")
    was_open = order.status == "open"
    selected = next((o for o in order.offers if o.id == order.selected_offer_id), None)
    order.status = "cancelled"
    db.commit()
    order = get_order(db, order_id)
    if was_open:
        broker.send("order_closed", {"order_id": order.id, "reason": "cancelled"}, role="driver")
    elif selected:
        broker.send("order_cancelled", {"order": order_out(order, selected.driver_id)}, user_id=selected.driver_id)
    return order_out(order)


@app.post("/api/orders/{order_id}/complete")
async def complete_order(order_id: int, user: User = Depends(require_driver), db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    selected = next((o for o in order.offers if o.id == order.selected_offer_id), None)
    if not selected or selected.driver_id != user.id:
        raise HTTPException(403, "Это не ваша поездка")
    if order.status != "assigned":
        raise HTTPException(409, "Поездку нельзя завершить")
    order.status = "completed"
    db.commit()
    broker.send("order_completed", {"order_id": order.id}, user_id=order.passenger_id)
    return {"status": "completed"}


@app.get("/api/events")
async def events(request: Request, user: User = Depends(get_user_sse)):
    queue = broker.connect(user.id, user.role)

    async def stream():
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            broker.disconnect(queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.mount("/", StaticFiles(directory=Path(__file__).parent / "Site", html=True), name="site")
