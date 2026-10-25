"""Visible synthetic login and dashboard check inside the isolated Linux network."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.goto('http://gateway:8080/auth/login')
    page.get_by_role('heading', name='Grantflow Docker lab').wait_for()
    results.append({'check': 'Synthetic login screen visible', 'passed': True})
    with page.expect_response(lambda r: '/gfm-app/api/analytics/dashboard' in r.url and r.status == 200):
        page.get_by_role('button', name='Enter as synthetic administrator').click()
        page.get_by_role('heading', name='Mission Control Dashboard').wait_for(timeout=30000)
    results.append({'check': 'Visible login reaches dashboard with successful authenticated analytics', 'passed': True})
    page.screenshot(path='/evidence/dashboard.png', full_page=True)
    browser.close()
Path('/evidence/browser-checks.json').write_text(json.dumps(results, indent=2))
print(json.dumps({'browser_checks_passed': len(results)}))
