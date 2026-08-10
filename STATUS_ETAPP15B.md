# Status Etapp 15b (Kvittning av leverantörskredit)

## Utfört arbete
- Implementerat verktyget `forbered_kvittning` i `mcp_server/server.py`.
- Lade till hämtning och validering av kvittningskandidater mot den begärda listan av `DebitInvoiceIds` (fail-closed, kontrolleras både i verktyget och vid utförandet i adaptern).
- Implementerade `skapa_kvittning` i `parser/spiris_adapter.py` som skickar in offset till Spiris via `POST /supplierinvoices/{id}/offset`.
- Infört strikt check (endast nycklarna `DebitInvoiceIds` och `VoucherDate` tillåts i requesten).
- Lade till test suite för fail-closed hantering i `tests/test_etapp15b_kvittning.py`.
- Uppdaterade metatesterna i `tests/test_mcp_villkorssparr.py` för att innefatta `forbered_kvittning`.
- Fixat gamla buggar kring `spiris_kvittningskandidater` (RAG-kompatibilitet) i `test_etapp5.py`.

## Kvarstående arbete
- Utföra Etapp 16 (Prislistor, rabattavtal och etiketter).
