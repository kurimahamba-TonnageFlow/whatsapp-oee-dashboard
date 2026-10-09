"""Capture the localhost-only synthetic preview; requires an existing Vite server."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

OUTPUT=Path('docs/intelligence-preview')

def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        for name,width,height in [('desktop-1920',1920,1080),('laptop-1440',1440,900),('tablet-landscape',1180,820),('tablet-portrait',820,1180)]:
            page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:5178/intelligence-preview.html')
            page.get_by_role('heading',name='Operational Intelligence').wait_for()
            page.screenshot(path=str(OUTPUT/f'{name}.png'),full_page=False)
            page.screenshot(path=str(OUTPUT/f'{name}-full.png'),full_page=True)
            size=page.evaluate('({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight})')
            assert size['scrollWidth']<=width,(name,size)
            assert not errors,errors
            # Detailed notes may extend below the principal dashboard.
            results.append(dict(name=name,viewport=[width,height],**size,browser_errors=errors))
            if width==1920:
                triggers=page.get_by_role('button',name=__import__('re').compile('Phase 2 financial preview')).all()
                assert len(triggers)==20
                for trigger in triggers:
                    trigger.click()
                    assert page.get_by_role('dialog').is_visible()
                    page.keyboard.press('Escape')
                    assert not page.get_by_role('dialog').count()
                    assert trigger.evaluate('(el)=>document.activeElement===el')
                page.get_by_role('button',name='Cost per Tonne: Phase 2 financial preview',exact=True).click()
                page.get_by_role('dialog').wait_for()
                page.screenshot(path=str(OUTPUT/'phase-2-modal.png'),full_page=False)
                page.get_by_role('button',name='Continue Viewing Dashboard').click()
                for state in ['empty','unscheduled','stale']:
                    page.get_by_role('button',name=state,exact=True).click()
                    page.screenshot(path=str(OUTPUT/f'state-{state}.png'),full_page=True)
                    assert page.evaluate('document.documentElement.scrollWidth')<=width
            page.close()
        browser.close()
    (OUTPUT/'verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results))

if __name__=='__main__':main()
