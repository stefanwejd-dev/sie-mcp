import asyncio
import runpy

import mcp.server.fastmcp as fastmcp


def test_alla_verktyg_registrerade_nar_servern_startar(monkeypatch):
    """Startblocket måste ligga sist i server.py.

    mcp.run() återvänder aldrig. Ett verktyg som definieras efter anropet
    registreras därför bara vid import — alltså i testsviten — och aldrig när
    servern faktiskt kör. Felet är osynligt för varje annat test i sviten,
    eftersom de importerar modulen i stället för att köra den.
    """
    fangat = {}

    def fejkad_run(self, *args, **kwargs):
        fangat["vid_start"] = len(asyncio.run(self.list_tools()))
        fangat["server"] = self

    monkeypatch.setattr(fastmcp.FastMCP, "run", fejkad_run)
    runpy.run_module("mcp_server.server", run_name="__main__")

    server = fangat["server"]
    efter = len(asyncio.run(server.list_tools()))
    assert fangat["vid_start"] == efter, (
        f"{efter - fangat['vid_start']} verktyg definieras efter mcp.run() och "
        "når aldrig en klient. Flytta startblocket sist i server.py."
    )


def test_alla_resurser_registrerade_nar_servern_startar(monkeypatch):
    """Startblocket måste ligga sist i server.py (för resurser)."""
    fangat = {}

    def fejkad_run(self, *args, **kwargs):
        fangat["vid_start_res"] = len(asyncio.run(self.list_resources()))
        fangat["vid_start_tmpl"] = len(asyncio.run(self.list_resource_templates()))
        fangat["server"] = self

    monkeypatch.setattr(fastmcp.FastMCP, "run", fejkad_run)
    runpy.run_module("mcp_server.server", run_name="__main__")

    server = fangat["server"]
    efter_res = len(asyncio.run(server.list_resources()))
    efter_tmpl = len(asyncio.run(server.list_resource_templates()))
    
    assert fangat["vid_start_res"] == efter_res, "Resurser definieras efter mcp.run()"
    assert fangat["vid_start_tmpl"] == efter_tmpl, "Resursmallar definieras efter mcp.run()"


def test_alla_prompter_registrerade_nar_servern_startar(monkeypatch):
    """Startblocket måste ligga sist i server.py (för prompter)."""
    fangat = {}

    def fejkad_run(self, *args, **kwargs):
        fangat["vid_start"] = len(asyncio.run(self.list_prompts()))
        fangat["server"] = self

    monkeypatch.setattr(fastmcp.FastMCP, "run", fejkad_run)
    runpy.run_module("mcp_server.server", run_name="__main__")

    server = fangat["server"]
    efter = len(asyncio.run(server.list_prompts()))
    assert fangat["vid_start"] == efter, "Prompter definieras efter mcp.run()"
