from sqlalchemy import Column, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    passenger_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String, default="open", nullable=False)
    selected_offer_id = Column(Integer)

    passenger = relationship("User")
    offers = relationship("Offer", back_populates="order", order_by="Offer.id")


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("order_id", "driver_id"),)

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    price = Column(Float, nullable=False)
    eta_minutes = Column(Integer, nullable=False)
    status = Column(String, default="pending", nullable=False)

    order = relationship("Order", back_populates="offers")
    driver = relationship("User")
