"""Read-only UI documentation captures from synthetic lab records only."""
from pathlib import Path
import json
import re
from playwright.sync_api import sync_playwright

out = Path('/evidence/standalone-docs')
out.mkdir(exist_ok=True)
rows = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.goto('http://gateway:8080/auth/login')
    page.screenshot(path=str(out / 'login.png'))
    page.get_by_role('button', name='Enter as synthetic administrator').click()
    page.get_by_role('heading', name='Mission Control Dashboard').wait_for()
    for route in ['dashboard', 'grants', 'applications', 'renewals', 'automation', 'ai', 'analytics', 'settings']:
        response = page.goto('http://gateway:8080/gfm-app/' + route, wait_until='networkidle')
        assert response.status == 200
        text = page.locator('body').inner_text()
        addresses = re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)
        assert all(address.endswith(('.invalid', '@example.com')) for address in addresses), 'Unexpected non-synthetic contact in capture'
        page.screenshot(path=str(out / (route + '.png')))
        rows.append({'route': route, 'synthetic_only': True})
    browser.close()
(out / 'manifest.json').write_text(json.dumps(rows, indent=2))
print('Captured nine synthetic documentation images; no production session or original endpoint used.')
