"""
Configuración compartida de fixtures para pruebas unitarias e integración.
Usa SQLite en memoria aislado por función para garantizar reproducibilidad total.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core.database import Base
from src.services.catalogo_service import CatalogoService


from sqlalchemy.pool import StaticPool

@pytest.fixture(scope="function")
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    CatalogoService.sembrar_reglas_laborales_base(session)
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

