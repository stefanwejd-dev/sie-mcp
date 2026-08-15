import os
import time
from pathlib import Path

_ROT = Path(__file__).resolve().parent
os.environ.setdefault("QUIET_OPPEN_DATA_ROOT", str(_ROT))
from quiet_oppen_data.konfig import las as las_quiet_konfig
las_quiet_konfig(_ROT / "quiet_config.toml")
from quiet_oppen_data.index import lag_ingest
from quiet_oppen_data.lagregister import las as las_lagregister
import sqlite3

def antal_klara():
    c = sqlite3.connect(_ROT / "data" / "quiet_index.sqlite")
    n = c.execute("SELECT COUNT(DISTINCT dok_id) FROM lag_chunk").fetchone()[0]
    c.close()
    return n

TOTALT = len(las_lagregister())
for varv in range(1, 8):
    klara = antal_klara()
    print(f"--- Varv {varv}: {klara}/{TOTALT} klara ---", flush=True)
    if klara >= TOTALT:
        print("Alla forfattningar klara.")
        break
    lag_ingest.main()
    nya = antal_klara()
    if nya >= TOTALT:
        print(f"Alla {TOTALT} forfattningar klara efter varv {varv}.")
        break
    if nya == klara:
        print(f"Inga nya sedan forra varvet ({nya}/{TOTALT}) - vantar 90s innan nasta forsok.", flush=True)
    time.sleep(90)
else:
    print(f"Gav upp efter {varv} varv: {antal_klara()}/{TOTALT} klara.")
