from curl_cffi import requests
from bs4 import BeautifulSoup

urls = [
    'https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx9-core-i7-rtx-4050-gaming-laptop-egypt',
    'https://www.compumarts.com/collections/laptop/products/asus-tuf-gaming-f16-fx607vu-rtx4050-core7-16gb-512ssd'
]

for url in urls:
    r = requests.get(url, impersonate='chrome110')
    soup = BeautifulSoup(r.text, 'html.parser')
    
    for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'noscript', 'svg']):
        tag.decompose()
        
    print('URL:', url.split('/')[-1])
    
    tables = soup.find_all('table')
    print('  Found tables:', len(tables))
    for idx, t in enumerate(tables):
        print(f'  Table {idx+1} rows:', len(t.find_all('tr')), 'text sample:', t.get_text(separator=' ', strip=True)[:100])
        
    candidates = soup.select('.pdesc-wrap, .dark-spec-wrapper, .product-description, [class*="product-details"]')
    print('  Candidate containers:', len(candidates))
    for c in candidates:
        txt = c.get_text(' ', strip=True)
        if len(txt) > 50:
            print('    Container class:', c.get('class'), 'Len:', len(txt), 'Sample:', txt[:100])
    print('='*60)
