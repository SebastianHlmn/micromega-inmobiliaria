from app.services.extraction_service import extract_search_fields


def test_extract_search_fields():
    out = extract_search_fields("Busco alquilar 2 o 3 ambientes en Caballito hasta 800 mil. Tengo un perro y me mudo en octubre.")
    assert out["operation"] == "alquiler"
    assert out["neighborhoods"] == ["Caballito"]
    assert out["rooms_min"] == 2
    assert out["rooms_max"] == 3
    assert out["budget_max"] == 800000
    assert out["pets"] is True
    assert out["move_date"] == "octubre"
