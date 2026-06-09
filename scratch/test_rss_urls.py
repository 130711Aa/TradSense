import requests

urls = [
    ("detik_finance", "https://finance.detik.com/rss"),
    ("kontan_investasi", "https://investasi.kontan.co.id/rss"),
    ("cnbc_market", "https://www.cnbcindonesia.com/market/rss"),
]
for name, url in urls:
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}, timeout=10)
        print(f"{name:15}: status={r.status_code}, len={len(r.content):6}, headers={r.headers.get('Content-Type', '')[:30]}")
    except Exception as e:
        print(f"{name:15}: error={e}")
