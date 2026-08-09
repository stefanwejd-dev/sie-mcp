import pytest
from datetime import date
from decimal import Decimal
import inspect
import sys
sys.path.append('parser')

from parser import snabbvyer
from parser.snabbvyer import Vydata

# Hitta alla funktioner i snabbvyer som returnerar Snabbvyresultat (eller som tar Vydata)
def hitta_publik_bygg_funktioner():
    funktioner = []
    for namn, func in inspect.getmembers(snabbvyer, inspect.isfunction):
        if namn.startswith("bygg_"):
            # Kolla om den tar Vydata
            sig = inspect.signature(func)
            if "data" in sig.parameters and sig.parameters["data"].annotation == "Vydata":
                funktioner.append(func)
    return funktioner

@pytest.mark.parametrize("bygg_func", hitta_publik_bygg_funktioner())
def test_harkomst_tackning(bygg_func):
    """Varje publik bygg_*-funktion i snabbvyer.py returnerar ett Vyresultat med satt harkomst."""
    
    vydata = Vydata(
        idag=date(2026, 8, 5),
        kundreskontra=[],
        leverantorsreskontra=[],
        kundbetalbeteende={}
    )
    
    res = bygg_func(vydata)
        
    assert res is not None
    assert hasattr(res, 'harkomst')
    assert res.harkomst is not None
    from stil import HARKOMST_LOKAL
    assert res.harkomst == HARKOMST_LOKAL
