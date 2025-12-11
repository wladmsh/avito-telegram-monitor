import requests
from bs4 import BeautifulSoup
import re
import logging

def parse_avito(url, min_price=0, max_price=999999999):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Ошибка запроса к {url}: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    items = []
    for item in soup.find_all('div', {'data-marker': 'item'}):
        try:
            title_elem = item.find('h3', itemprop='name')
            price_elem = item.find('meta', itemprop='price')
            link_elem = item.find('a', itemprop='url')
            item_id = item.get('data-item-id')

            if not all([title_elem, price_elem, link_elem, item_id]):
                continue

            title = title_elem.text.strip()
            price = int(price_elem['content'])
            link = 'https://www.avito.ru' + link_elem['href']

            if price < min_price or price > max_price:
                continue

            items.append({
                'id': item_id,
                'title': title,
                'price': price,
                'link': link
            })
        except Exception as e:
            logging.error(f"Ошибка парсинга объявления: {e}")
            continue
    return items
