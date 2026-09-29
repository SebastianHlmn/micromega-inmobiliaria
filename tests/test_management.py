from app.models import Category
from app.services.management_service import _fallback_category_slugs, slugify


def test_slugify_spanish_category_name():
    assert slugify("Garantías y Documentación") == "garantias_y_documentacion"


def test_fallback_category_detects_visit_and_pets():
    categories = [
        Category(name="Visita", slug="visita", active=True),
        Category(name="Mascotas", slug="mascotas", active=True),
        Category(name="Expensas", slug="expensas", active=True),
    ]
    out = _fallback_category_slugs("Tengo un perro y me gustaría coordinar una visita", categories)
    assert "mascotas" in out
    assert "visita" in out
    assert "expensas" not in out
