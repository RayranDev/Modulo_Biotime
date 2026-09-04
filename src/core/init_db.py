"""
Inicializador de esquema de Base de Datos.
Crea todas las tablas del dominio y siembra las reglas base.
"""
from src.core.database import Base, engine, SessionLocal
import src.domain.models  # Registra todos los modelos en Base.metadata
from src.services.catalogo_service import CatalogoService


def inicializar_base_datos():
    print("Creando tablas en la base de datos...")
    Base.metadata.create_all(bind=engine)
    print("Tablas creadas exitosamente.")

    db = SessionLocal()
    try:
        print("Sembrando reglas laborales base...")
        reglas = CatalogoService.sembrar_reglas_laborales_base(db)
        print(f"Reglas laborales sembradas: {len(reglas)}")
    finally:
        db.close()


if __name__ == "__main__":
    inicializar_base_datos()
