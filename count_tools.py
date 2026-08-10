import asyncio
import mcp.server.fastmcp as fastmcp
import runpy

fangat = {}
def fejkad_run(self, *args, **kwargs):
    fangat["server"] = self

fastmcp.FastMCP.run = fejkad_run
runpy.run_module("mcp_server.server", run_name="__main__")
server = fangat["server"]
tools = asyncio.run(server.list_tools())
res = asyncio.run(server.list_resources())
tmpl = asyncio.run(server.list_resource_templates())
prompts = asyncio.run(server.list_prompts())

alias = 0
read = 0
write = 0
visa = 0

for t in tools:
    if t.name == "visa_anvandarvillkor":
        visa += 1
    elif t.name.startswith("forbered_") or t.name.startswith("kontrollera_"):
        write += 1
    elif "Alias" in (t.description or "") or "alias" in (t.description or ""):
        alias += 1
    else:
        read += 1

print(f"Total: {len(tools)}, Read: {read}, Write: {write}, Alias: {alias}, Visa: {visa}")
print(f"Res: {len(res)}, Tmpl: {len(tmpl)}, Prompts: {len(prompts)}")
