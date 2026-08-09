import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'parser'))

from dotenv import load_dotenv
import saker_lagring
load_dotenv(saker_lagring.artefakt_sokvag(None, kategori="secret", namn=".env"))

if os.environ.get("SIE_MCP_SPIRIS_CLIENT_ID"):
    os.environ["SPIRIS_CLIENT_ID"] = os.environ.get("SIE_MCP_SPIRIS_CLIENT_ID")
if os.environ.get("SIE_MCP_SPIRIS_CLIENT_SECRET"):
    os.environ["SPIRIS_CLIENT_SECRET"] = os.environ.get("SIE_MCP_SPIRIS_CLIENT_SECRET")


from spiris_session import bygg_klient
try:
    klient = bygg_klient()
    print("Klient bygd OK")
    
        
    invoices = klient.hamta_alla("/supplierinvoices")
    print(f"Hittade {len(invoices)} leverantörsfakturor.")

    import json
    with open('dummy.png.b64', 'r') as f:
        dummy_content = f.read()
    try:
        url = "https://eaccountingapi.vismaonline.com/v2/attachments"
        payload = {
            "FileName": "kvitto.png",
            "ContentType": "image/png",
            "Data": dummy_content
        }
        res = klient._anrop("POST", url, kropp=json.dumps(payload))
        if res.status_code >= 400:
            print("HTTP Fel POST /attachments:", res.status_code, res.text)
            attachments = []
        else:
            att_res = res.json()
            print("Skapade bilaga:", att_res)
            attachments = [att_res]
    except Exception as e:
        print("Kunde inte skapa bilaga:", e)
        attachments = []

    
    if attachments and invoices:
        att_id = attachments[0]["Id"]
        doc_id = invoices[0]["Id"]
        print(f"Provar att koppla bilaga {att_id} till lev-faktura {doc_id}...")
        
        # Test 1: Simple object with DocumentId and AttachmentIds
        try:
            res = klient._anrop("POST", "https://eaccountingapi.vismaonline.com/v2/attachmentlinks", kropp=json.dumps({
                "DocumentId": doc_id,
                "AttachmentIds": [att_id],
                "DocumentType": "SupplierInvoice"
            }))
            print("Test 1 res:", res.status_code, res.text)
        except Exception as e:
            print("Test 1 misslyckades:", e)
            
        # Test 2: Try another structure
        try:
            res = klient._anrop("POST", "https://eaccountingapi.vismaonline.com/v2/attachmentlinks", kropp=json.dumps({
                "DocumentId": doc_id,
                "AttachmentId": att_id
            }))
            print("Test 2 res:", res.status_code, res.text)
        except Exception as e:
            print("Test 2 misslyckades:", e)

        # Test 3: /salesdocumentattachments/customerinvoice
        try:
            # For this we need a customer invoice
            cust_invoices = klient.hamta_alla("/customerinvoices")
            if cust_invoices:
                cust_doc_id = cust_invoices[0]["Id"]
                res = klient._anrop("POST", "https://eaccountingapi.vismaonline.com/v2/salesdocumentattachments/customerinvoice", kropp=json.dumps({
                    "CustomerInvoiceId": cust_doc_id,
                    "AttachmentId": att_id
                }))
                print("Test 3 res:", res.status_code, res.text)
            else:
                print("Inga kundfakturor.")
        except Exception as e:
            print("Test 3 misslyckades:", e)

        # Test 4: Link to a Voucher
        try:
            vouchers = klient.hamta_alla("/vouchers")
            if vouchers:
                v_doc_id = vouchers[0]["Id"]
                # create second attachment
                res2 = klient._anrop("POST", url, kropp=json.dumps(payload))
                att_id2 = res2.json()["Id"]
                
                res = klient._anrop("POST", "https://eaccountingapi.vismaonline.com/v2/attachmentlinks", kropp=json.dumps({
                    "DocumentId": v_doc_id,
                    "AttachmentIds": [att_id2],
                    "DocumentType": "Voucher"
                }))
                print("Test 4 res:", res.status_code, res.text)
            else:
                print("Inga verifikat.")
        except Exception as e:
            print("Test 4 misslyckades:", e)

except Exception as e:
    print("Error:", e)

