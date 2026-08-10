# Överlämningsdokument - MCP Etapp 14

Detta dokument sammanfattar arbetet som utförts för Etapp 14 (Fakturautkastens ändringsallowlist).

## Vad som har utförts

### U14.1 — Kundfakturautkast (Ändringsallowlist)
* Lagt till ändringsallowlisten för `kundfaktura` (`CustomerInvoiceDraftApi`) i `_UTKASTANDRING` i `parser/spiris_adapter.py`.
* Endast de 28 spec-härledda fälten (såsom `Rows`, `InvoiceDate`, adressfält, referensfält) är tillåtna att uppdateras.
* Serverägda fält (som `Id`), motpartsfält (D2), valuta (D2), skattereduktioner (D2), egna resurser, och härledda summor avvisas med `SpirisKlientFel`.
* `RotReducedInvoicingType` och `EuThirdParty` stannar kvar orörda i requesten (read-modify-write funktionen behåller dem som krävdes i specen).

### U14.2 — Leverantörsfakturautkast (Ändringsallowlist)
* Lagt till ändringsallowlisten för `leverantorsfaktura` (`SupplierInvoiceDraftApi`) i `_UTKASTANDRING`.
* Endast de 11 tillåtna fälten är ändringsbara.
* Serverägda fält, motpartsfält (D2), valuta (D2), attestkedjan, periodisering, och härledda summor avvisas med `SpirisKlientFel`.
* De obligatoriska fälten `SupplierId`, `IsCreditInvoice`, och `Rows` finns garanterat kvar i requesten.

### Ändringar i MCP-servern
* Uppdaterade `forbered_utkastandring` för att tillåta argumenten `utkasttyp="kundfaktura"` och `utkasttyp="leverantorsfaktura"` (den var tidigare hårdkodad för bara "verifikat").

### Kvalitetssäkring
* Skapade `test_etapp14_utkastandring.py` med totalt **18 tester**! 
* Det finns rigorösa fail-closed tester för **varje enskild låst kategori** (serverägda, D2-motpart, D2-valuta, härledda summor, egna resurser, etc) på båda utkastslagen.
* Samtliga 18 nya tester passerar. Även alla villkorsspärrs-tester är fortsatt gröna och påverkas inte negativt.

## Återstående arbete & Beslut

**GRIND 14** är nådd. Nästa etapp enligt planen är **Etapp 15 — Order- och offertutkast**.

Jag inväntar nu inspektion/okey från dig. Säg till när du är redo för Etapp 15!
