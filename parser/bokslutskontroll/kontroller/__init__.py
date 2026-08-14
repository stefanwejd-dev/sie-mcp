"""Importerar undermodulerna så att motorns register (KONTROLLER) fylls.

Motorn känner inte till någon enskild kontroll (B-3) — den vet bara att om
den här paketet importeras finns alla registrerade kontroller i
`bokslutskontroll.motor.KONTROLLER`."""

from __future__ import annotations

from . import integritet  # noqa: F401
from . import saldologik  # noqa: F401
from . import bokslutsposter  # noqa: F401
from . import kontotyper  # noqa: F401
