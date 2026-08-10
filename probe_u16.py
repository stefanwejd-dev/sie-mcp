import sys
import os
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(base_dir, "parser"))
sys.path.insert(0, base_dir)

import asyncio
import json
from mcp_server.server import bygg_klient

async def main():
    k = bygg_klient()
    
    print("Fetching /salespricelists...")
    lists = k.hamta_alla("/salespricelists")
    print(f"Got {len(lists)} lists.")
    if lists:
        print(json.dumps(lists[0], indent=2))
        
        l_id = lists[0]["Id"]
        print(f"\nFetching /salespricelists/prices/{l_id}...")
        try:
            prices = k.hamta_alla(f"/salespricelists/prices/{l_id}")
            print(f"Got {len(prices)} prices.")
            if prices:
                print(json.dumps(prices[0], indent=2, default=str))
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("No lists found.")

if __name__ == "__main__":
    asyncio.run(main())
