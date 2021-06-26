import requests
import json, sys
from collections import defaultdict


def main():
    with open('shopify-api-key') as f:
        apikey = f.read().rstrip()
    base_url = f'https://{apikey}@the-little-shop-of-stitches.myshopify.com/admin/api/2021-04/customers.json'
    limit = 250
    customers = []
    full_list = fetch_customers(url=base_url, apikey=apikey, limit=limit, customers=customers)

    for entry in full_list:
        print(entry)
        sys.exit()

def fetch_customers(url, apikey, limit=250, page_info='', chunk=1, customers = ''):
    # cache the page_info we receive and use it for the query if we got one
    cached_page_info = page_info
    base_url = url
    url += f'?limit={limit}&page_info={page_info}'
    response = requests.get(f'{url}')
    response.raise_for_status()
    # customers.append(response.json()['customers'])
    for entry in response.json()['customers']:
        customer = {
            'first_name': entry['first_name'],
            'last_name': entry['last_name'],
            'address1': entry['default_address']['address1'],
            'address2': entry['default_address']['address2'],
            'city': entry['default_address']['city'],
            'province_code': entry['default_address']['province_code'],
            'zip': entry['default_address']['zip']
        }
        customers.append(customer)

    link_header = response.headers.get('Link')
    # update the page_info with the one fromr the link header
    links = link_header.split(',')
    if len(links) > 1:
        page_info = links[1].split('page_info=')[1].split(';')[0].strip('<>')
    elif 'next' in links[0]:
        page_info = links[0].split('page_info=')[1].split(';')[0].strip('<>')

    if cached_page_info != page_info:
        return fetch_customers( base_url, apikey, limit, page_info, chunk=chunk+1, customers=customers)

    return customers

if __name__ == '__main__':
    main()