import os
from pathlib import Path

# 1. Update test_mcp_lasande_bredd.py
fpath = "tests/test_mcp_lasande_bredd.py"
content = Path(fpath).read_text(encoding="utf-8")

from_import = "spiris_etiketter,"
new_imports = "spiris_etiketter, spiris_verifikation, spiris_bankhandelse,"
content = content.replace(from_import, new_imports)

old_dict = '''    "spiris_etiketter": lambda: spiris_etiketter("kund"),
}'''
new_dict = '''    "spiris_etiketter": lambda: spiris_etiketter("kund"),
    "spiris_verifikation": lambda: spiris_verifikation("fy-1", "v-1"),
    "spiris_bankhandelse": lambda: spiris_bankhandelse("b-1", "t-1"),
}'''
content = content.replace(old_dict, new_dict)

old_hamta_en = '''        if path.startswith("/customers/"):
            return {"CustomerName": "Anna Andersson", "Email": "anna@example.com"}'''
new_hamta_en = '''        if path.startswith("/customers/"):
            return {"CustomerName": "Anna Andersson", "Email": "anna@example.com"}
        if path.startswith("/vouchers/"):
            return {
                "Id": "v-1", "VoucherDate": "2026-07-06", "VoucherText": "En verifikation med Anna Andersson",
                "Rows": [
                    {"AccountNumber": 1930, "DebitAmount": 1000, "CreditAmount": 0, "TransactionText": "Radtext"},
                    {"AccountNumber": 3000, "DebitAmount": 0, "CreditAmount": 1000, "TransactionText": ""},
                ],
                "NumberAndNumberSeries": "A12", "NumberSeries": "A", "VoucherType": 1,
                "CreatedUtc": "2026-07-06T10:00:00.00Z", "ModifiedUtc": "2026-07-06T10:00:00.00Z"
            }
        if path.startswith("/banktransactions/"):
            return {
                "Id": "t-1", "BankAccountId": "b-1", "Amount": 100.5, "TransactionDate": "2026-08-10T12:00:00",
                "Description": "Test betalning", "Reference": "INV-123", "MatchId": "m-1"
            }'''
content = content.replace(old_hamta_en, new_hamta_en)

Path(fpath).write_text(content, encoding="utf-8")


# 2. Update test_mcp_villkorssparr.py
fpath2 = "tests/test_mcp_villkorssparr.py"
content2 = Path(fpath2).read_text(encoding="utf-8")

old_args = '''    "spiris_etiketter": ("kund",),
}'''
new_args = '''    "spiris_etiketter": ("kund",),
    "spiris_verifikation": ("fy-1", "v-1"),
    "spiris_bankhandelse": ("b-1", "t-1"),
}'''
content2 = content2.replace(old_args, new_args)

old_funcs = '''    "spiris_etiketter": server_modul.spiris_etiketter,
}'''
new_funcs = '''    "spiris_etiketter": server_modul.spiris_etiketter,
    "spiris_verifikation": server_modul.spiris_verifikation,
    "spiris_bankhandelse": server_modul.spiris_bankhandelse,
}'''
content2 = content2.replace(old_funcs, new_funcs)

Path(fpath2).write_text(content2, encoding="utf-8")
