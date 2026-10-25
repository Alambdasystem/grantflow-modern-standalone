"""Fresh synthetic Chromium profile only; no original session is loaded."""
import asyncio
import json
import os
from pathlib import Path
import sys
from playwright.async_api import async_playwright

path=Path(os.environ['GFM_BROWSER_PROFILE_DIR']);assert path==Path('/data/browser-profile');path.mkdir(exist_ok=True)
phase=sys.argv[1]
async def main():
    async with async_playwright() as p:
        context=await p.chromium.launch_persistent_context(str(path),headless=True)
        if phase=='write':await context.add_cookies([{'name':'synthetic_probe','value':'portable-profile','url':'http://identity:8000','expires':2000000000}])
        else:assert any(c['name']=='synthetic_probe' and c['value']=='portable-profile' for c in await context.cookies('http://identity:8000'))
        await context.close()
    print(json.dumps({'feature':'Fresh browser-profile volume '+phase,'result':'PASS','scope':'Synthetic cookie only; not a real portal session'}))
asyncio.run(main())
