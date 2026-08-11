import os
import re

# Move from spiris_rag to spiris_adapter
with open('parser/spiris_rag.py', 'r', encoding='utf-8') as f:
    rag_content = f.read()

# Extract the functions
pattern = r'(def hamta_prislistor.*?return res\n\n\ndef hamta_rabattavtal.*?return res\n\n\ndef hamta_etiketter.*?return res\n)'
match = re.search(pattern, rag_content, re.DOTALL)
if not match:
    # Try slightly different formatting
    pattern = r'(def hamta_prislistor.*?return res\n\n\ndef hamta_rabattavtal.*?return res\n\n\ndef hamta_etiketter.*?return res\n)'
    match = re.search(pattern, rag_content, re.DOTALL)

if match:
    functions_code = match.group(1)
    # Remove from spiris_rag
    rag_content = rag_content.replace(functions_code, "")
    with open('parser/spiris_rag.py', 'w', encoding='utf-8') as f:
        f.write(rag_content)
        
    # Append to spiris_adapter
    with open('parser/spiris_adapter.py', 'a', encoding='utf-8') as f:
        f.write("\n\n" + functions_code)

# Replace in mcp_server/server.py
with open('mcp_server/server.py', 'r', encoding='utf-8') as f:
    server_content = f.read()
server_content = server_content.replace("spiris_rag.hamta_prislistor", "spiris_adapter.hamta_prislistor")
server_content = server_content.replace("spiris_rag.hamta_rabattavtal", "spiris_adapter.hamta_rabattavtal")
server_content = server_content.replace("spiris_rag.hamta_etiketter", "spiris_adapter.hamta_etiketter")
# Add import
server_content = server_content.replace("import parser.spiris_rag as spiris_rag", "import parser.spiris_rag as spiris_rag\nimport parser.spiris_adapter as spiris_adapter")
with open('mcp_server/server.py', 'w', encoding='utf-8') as f:
    f.write(server_content)

# Replace in tests/test_etapp16_strukturer.py
test_file = 'tests/test_etapp16_strukturer.py'
if os.path.exists(test_file):
    with open(test_file, 'r', encoding='utf-8') as f:
        tc = f.read()
    tc = tc.replace("from parser.spiris_rag import hamta_prislistor, hamta_rabattavtal, hamta_etiketter", "from parser.spiris_adapter import hamta_prislistor, hamta_rabattavtal, hamta_etiketter")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(tc)

print("U7.1 moved.")
