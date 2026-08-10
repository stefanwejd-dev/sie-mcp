import os
from pathlib import Path

fpath = "mcp_server/server.py"
content = Path(fpath).read_text(encoding="utf-8")

# Remove the original block
original_block = '''if __name__ == "__main__":
    mcp.run()'''

content = content.replace(original_block, "")

# Append the new block to the end of the file
new_block = '''
# Startblocket MÅSTE ligga sist i filen. mcp.run() återvänder aldrig — allt
# som definieras efter det anropet registreras aldrig när servern körs som
# __main__, bara när modulen importeras (t.ex. av testsviten). Ett verktyg som
# hamnar under den här raden är osynligt för varje riktig klient, och sviten
# blir grön ändå. Uppmätt 2026-08-10: 62 av 125 verktyg nådde klienten.
if __name__ == "__main__":
    mcp.run()
'''
content = content.rstrip() + "\n" + new_block

Path(fpath).write_text(content, encoding="utf-8")
