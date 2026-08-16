"""Bygger sie-mcp/data/quiet_index.sqlite — katalogindex + lagkorpus för
parser/quiet_kalla.py (quiet_oppen_data körd i sie-mcps egen process).

Körs en gång (och sedan om vid behov, t.ex. nattligt via schemaläggning —
se quiet_chatt/src/quiet_oppen_data/index/nattlig_ingest.py för samma idé):

    python bygg_quiet_index.py

Tar ~15-20 minuter (katalogingest ~2 min, lagkorpus-embeddings resten) och
kräver nätverksåtkomst. Måste köras med sie-mcps rotmapp som arbetskatalog
— quiet_config.toml pekar på en databas-sökväg (data/quiet_index.sqlite)
som är relativ till cwd, inte till paketet.

quiet_oppen_data.konfig.las() cachar sitt resultat process-globalt vid
FÖRSTA anropet. lag_ingest.py anropar las() utan argument internt (den vet
inget om sie-mcp), så konfigurationen måste sättas här, före importen —
annars letar den efter en config.toml inne i det installerade paketet, där
ingen finns. Samma teknik som parser/quiet_kalla.py använder.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_ROT = Path(__file__).resolve().parent
# MÅSTE sättas innan quiet_oppen_data importeras första gången — register.py,
# lagregister.py och konfig.py läser den vid modulimport (kallor/, lagar/ och
# quiet_config.toml ligger här i sie-mcp, inte i det installerade paketet).
os.environ.setdefault("QUIET_OPPEN_DATA_ROOT", str(_ROT))

from quiet_oppen_data.konfig import las as las_quiet_konfig

las_quiet_konfig(_ROT / "quiet_config.toml")

from quiet_oppen_data.index import ingest, lag_ingest  # noqa: E402 — måste komma efter QUIET_OPPEN_DATA_ROOT ovan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

if __name__ == "__main__":
    (_ROT / "data").mkdir(exist_ok=True)

    print("=== Katalogingest (dataportal.se, ~2 min) ===")
    ingest.main(_ROT / "data" / "quiet_index.sqlite")

    print("\n=== Lagkorpus-ingest (62 författningar, embeddings) ===")
    lag_ingest.main()
