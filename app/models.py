import datetime as dt
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, LargeBinary, Text
from sqlalchemy.orm import relationship
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    generations = relationship("Generation", back_populates="user", cascade="all, delete-orphan")

class Generation(Base):
    __tablename__ = "generations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    breed = Column(String(128), nullable=True)
    status = Column(String(32), default="processing", nullable=False)  # processing|done|error
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="generations")
    images = relationship("ImageAsset", back_populates="generation", cascade="all, delete-orphan")

class ImageAsset(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True)
    generation_id = Column(Integer, ForeignKey("generations.id"), index=True, nullable=False)

    kind = Column(String(32), nullable=False)  # original|t1|t2|dog
    mime_type = Column(String(64), default="image/png", nullable=False)
    data = Column(LargeBinary, nullable=False)  # store bytes directly in DB
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    generation = relationship("Generation", back_populates="images")
