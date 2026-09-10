from app.services.extraction_service import (
    extract_search_fields,
    normalize_search_fields,
)
from app.services.llm_service import LLMService


def test_extract_search_fields():
    out = extract_search_fields("Busco alquilar 2 o 3 ambientes en Caballito hasta 800 mil. Tengo un perro y me mudo en octubre.")
    assert out["operation"] == "alquiler"
    assert out["neighborhoods"] == ["Caballito"]
    assert out["rooms_min"] == 2
    assert out["rooms_max"] == 3
    assert out["budget_max"] == 800000
    assert out["pets"] is True
    assert out["move_date"] == "octubre"


def test_negative_pets_rule():
    out = extract_search_fields("Busco 2 ambientes en Palermo. No tengo mascotas.")
    assert out["pets"] is False


def test_normalize_rejects_invalid_values():
    out = normalize_search_fields({
        "operation": "ALQUILER",
        "neighborhoods": ["Palermo", "Palermo", "  Caballito  ", 123],
        "rooms_min": "3",
        "rooms_max": "2",
        "budget_max": "900000",
        "currency": "ars",
        "pets": True,
        "invented": "no debe pasar",
    })
    assert out["operation"] == "alquiler"
    assert out["neighborhoods"] == ["Palermo", "Caballito"]
    assert out["rooms_min"] == 2
    assert out["rooms_max"] == 3
    assert out["budget_max"] == 900000
    assert out["currency"] == "ARS"
    assert "invented" not in out


def test_llm_service_uses_rules_without_api_key():
    service = LLMService()
    service.provider = "mock"
    out, source = service.extract_search_fields("Quiero alquilar en Villa Crespo, 2 ambientes hasta 700 mil")
    assert source == "rules"
    assert out["operation"] == "alquiler"
    assert out["neighborhoods"] == ["Villa Crespo"]
    assert out["rooms_min"] == 2
