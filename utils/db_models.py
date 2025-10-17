import os
import enum
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    script_path = Column(String(1000), nullable=False)
    script_type = Column(String(10), nullable=False)
    args = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), default="system")

    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    modified_by = Column(String(100), default="system")

    def __repr__(self):
        return f"<Job(id={self.id}, name='{self.name}', type={self.script_type.value})>"


# --- Database setup ---
def get_engine(db_path="sqlite:///scheduler.db"):
    """Return a SQLAlchemy engine for SQLite DB."""
    return create_engine(db_path, echo=False, future=True)


def get_session(db_path="sqlite:///scheduler.db"):
    """Return a session factory."""
    engine = get_engine(db_path)
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    """Create all tables if not already created."""
    os.makedirs("data", exist_ok=True)

    db_path = "sqlite:///data/scheduler.db"

    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    print(f"✅ Database and tables created successfully at {db_path}")
