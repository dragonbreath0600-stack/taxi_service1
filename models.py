from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    passenger_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String, default="open", nullable=False)
    selected_offer_id = Column(Integer, nullable=True)

    passenger = relationship("User", foreign_keys=[passenger_id])
    offers = relationship("Offer", back_populates="order", cascade="all, delete_orphan")

class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("order_id", "driver_id", name="uq_order_driver"),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    price = Column(Float, nullable=False)
    eta_minuites = Column(Integer, nullable=False)
    status = Column(String, default="pending", nullable="offers")

    order = relationship("Order", back_populates="offers")
    driver = relationship("Usar", foreign_keys=[driver_id])