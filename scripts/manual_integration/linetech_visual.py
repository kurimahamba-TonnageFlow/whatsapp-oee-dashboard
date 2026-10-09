"""Exercise actual React components with the isolated synthetic preview entry.
Start Vite on 127.0.0.1:5178, then run this module with Playwright available.
"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

OUT = Path('docs/linetech-preview')
BASE = 'http://127.0.0.1:5178/linetech-preview.html'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width':1280,'height':900}, device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def tap(label):
            page.get_by_role('button',name=label,exact=True).click()
        def nav(label):
            page.get_by_role('navigation',name='Preview scenarios').get_by_role('button',name=label,exact=True).click()
        def shot(name):
            page.screenshot(path=str(OUT/name),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), name
        page.goto(BASE+'?view=before')
        page.get_by_role('heading',name='Report to Engineer — Rovema').wait_for()
        shot('00-before-fault-screen.png')
        nav('Active');shot('01-active-run-landscape.png')
        nav('Fault');shot('02-fault-machines.png')
        tap('SBS / Bagger');tap('BV1');tap('Film');tap('Film Torn');shot('03-fault-actions.png')
        tap('Resolved by LineTech');page.get_by_label('Production has restarted now').check();shot('04-restart-confirmation.png')
        tap('Save resolved downtime');page.get_by_text('✓ Resolved downtime recorded',exact=True).wait_for();checks.append('LineTech-resolved preset with explicit restart, no required comment')
        nav('Fault');tap('Case Packer');tap('Faults');tap('Infeed jam');tap('Report to Engineer')
        page.get_by_text('✓ Reported to Engineering',exact=True).wait_for();shot('05-engineering-escalation.png');checks.append('Engineering escalation acknowledgement')
        nav('Planned');tap('Film Change');tap('BV2');shot('06-planned-confirmation.png');tap('Confirm planned stop')
        page.get_by_role('heading',name='Planned Downtime — Film Change / BV2').wait_for();tap('End Planned Downtime');tap('Yes, End Downtime');checks.append('Planned stop start, component and explicit end; no automatic CCP pass')
        for kind,value in [('Product','Brown Basmati'),('Format','1 kg x 8'),('Size','0.5 kg')]:
            nav('Changeover');page.get_by_role('button',name=kind,exact=True).wait_for();tap(kind);tap(value);shot(f'07-{kind.lower()}-changeover.png');tap('Confirm Changeover')
            if kind!='Product':
                page.get_by_role('heading',name='Waiting for Engineering').wait_for()
                nav('Engineering');tap('Accept changeover')
                page.get_by_label('Work completed and settings changed').fill('Preview fixture: guides set, program selected and checked against setup sheet.')
                shot(f'08-{kind.lower()}-engineering.png')
                tap('Engineering work complete');tap('Confirm work complete')
                page.get_by_text('Ready',exact=True).wait_for();nav('Stoppage')
            tap('Confirm physical changeover complete')
            page.get_by_text('Record verification',exact=True).wait_for()
            for label in ['First-off approved','Label checked','Date code checked','CCP check passed']:
                page.get_by_label(label,exact=True).check()
            page.get_by_label('QA record reference').fill('SYNTHETIC-QA-001')
            if kind=='Format':shot('09-verification.png')
            tap('Save verification');page.get_by_role('button',name='Enter New Run Details').wait_for()
            shot(f'10-{kind.lower()}-ready.png');tap('Enter New Run Details')
            page.get_by_text('Preview: verification passed.',exact=False).wait_for()
            checks.append(f'{kind}: configured selection, required Engineering workflow, verification and separate restart setup')
        nav('Management');page.get_by_text('Enable LineTech navigation on this line',exact=True).wait_for();shot('12-management-setup.png');checks.append('Management configuration uses the actual setup component')
        for width,height,label in [(768,1024,'tablet-portrait'),(390,844,'mobile'),(1440,900,'desktop')]:
            page.set_viewport_size({'width':width,'height':height});nav('Fault');shot(f'11-{label}.png')
            boxes=page.locator('main .linetech-tile').first.bounding_box()
            assert boxes is not None and boxes['height']>=56
            checks.append(f'{label}: no horizontal overflow, large touch controls')
        assert not errors, errors
        browser.close()
    (OUT/'visual-checks.json').write_text(json.dumps({'checks':checks,'browser_errors':errors,'data':'Synthetic local fixtures. Actual transaction checks are in linetech_workflow.py.'},indent=2),encoding='utf-8')
    print('\n'.join('PASS '+check for check in checks))

if __name__=='__main__':
    main()
