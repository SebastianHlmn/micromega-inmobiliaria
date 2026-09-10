from sqlalchemy import select
from .db import Base, engine, SessionLocal
from .models import Property

SAMPLE_PROPERTIES = [
    dict(code="MM-001", operation="alquiler", neighborhood="Caballito", address="Av. Rivadavia 5200", rooms=2, price=650000, currency="ARS", expenses=120000, pets_allowed=True, description="Demo: 2 ambientes luminoso."),
    dict(code="MM-002", operation="alquiler", neighborhood="Caballito", address="Acoyte 700", rooms=3, price=780000, currency="ARS", expenses=150000, pets_allowed=True, description="Demo: 3 ambientes con balcón."),
    dict(code="MM-003", operation="alquiler", neighborhood="Villa Crespo", address="Juan B. Justo 3100", rooms=2, price=720000, currency="ARS", expenses=135000, pets_allowed=False, description="Demo: 2 ambientes."),
    dict(code="MM-004", operation="alquiler", neighborhood="Almagro", address="Medrano 600", rooms=3, price=740000, currency="ARS", expenses=110000, pets_allowed=True, description="Demo: 3 ambientes."),
    dict(code="MM-005", operation="alquiler", neighborhood="Palermo", address="Soler 4200", rooms=2, price=890000, currency="ARS", expenses=180000, pets_allowed=True, description="Demo: 2 ambientes."),
    dict(code="MM-006", operation="alquiler", neighborhood="Flores", address="Carabobo 300", rooms=3, price=610000, currency="ARS", expenses=95000, pets_allowed=True, description="Demo: 3 ambientes."),
    dict(code="MM-007", operation="alquiler", neighborhood="Colegiales", address="Federico Lacroze 3000", rooms=2, price=820000, currency="ARS", expenses=140000, pets_allowed=None, description="Demo: 2 ambientes."),
    dict(code="MM-008", operation="alquiler", neighborhood="Villa Urquiza", address="Olazabal 5000", rooms=3, price=790000, currency="ARS", expenses=125000, pets_allowed=True, description="Demo: 3 ambientes."),
    dict(code="MM-009", operation="venta", neighborhood="Caballito", address="Pedro Goyena 900", rooms=3, price=145000, currency="USD", expenses=160000, pets_allowed=True, description="Demo: venta 3 ambientes."),
    dict(code="MM-010", operation="venta", neighborhood="Belgrano", address="Mendoza 2400", rooms=2, price=165000, currency="USD", expenses=175000, pets_allowed=True, description="Demo: venta 2 ambientes."),
    dict(code="MM-011", operation="venta", neighborhood="Villa Crespo", address="Araoz 900", rooms=2, price=118000, currency="USD", expenses=100000, pets_allowed=True, description="Demo: venta 2 ambientes."),
    dict(code="MM-012", operation="venta", neighborhood="Palermo", address="Gorriti 4600", rooms=3, price=210000, currency="USD", expenses=190000, pets_allowed=False, description="Demo: venta 3 ambientes."),
    dict(code="MM-013", operation="alquiler", neighborhood="Boedo", address="Estados Unidos 3500", rooms=2, price=590000, currency="ARS", expenses=90000, pets_allowed=True, description="Demo: 2 ambientes."),
    dict(code="MM-014", operation="alquiler", neighborhood="Chacarita", address="Dorrego 1200", rooms=1, price=510000, currency="ARS", expenses=85000, pets_allowed=True, description="Demo: monoambiente."),
    dict(code="MM-015", operation="alquiler", neighborhood="Belgrano", address="Amenabar 1800", rooms=3, price=950000, currency="ARS", expenses=210000, pets_allowed=True, description="Demo: 3 ambientes."),
]


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.scalar(select(Property).limit(1)):
            print("La base ya contiene propiedades. No se agregó el seed nuevamente.")
            return
        db.add_all([Property(**p) for p in SAMPLE_PROPERTIES])
        db.commit()
        print(f"Seed listo: {len(SAMPLE_PROPERTIES)} propiedades demo.")


if __name__ == "__main__":
    main()
