"""formatering — gemensam logik för sifferformatering."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class Formateringsval:
    decimaler: int = 0
    tusentalsavgransare: str = " "
    decimalseparator: str = ","
    comma_style: bool = True

def formatera_tal(varde: Any, val: Formateringsval) -> str:
    try:
        f_varde = float(varde)
    except (ValueError, TypeError):
        return str(varde)
        
    if val.comma_style:
        bas = f"{f_varde:,.{val.decimaler}f}"
        delar = bas.split('.')
        heltal = delar[0].replace(',', val.tusentalsavgransare)
        if len(delar) > 1:
            return f"{heltal}{val.decimalseparator}{delar[1]}"
        return heltal
    else:
        bas = f"{f_varde:.{val.decimaler}f}"
        return bas.replace('.', val.decimalseparator)
