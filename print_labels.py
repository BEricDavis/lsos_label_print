import argparse
from reportlab.platypus.doctemplate import NextPageTemplate
import datetime as dt
import requests
import os
import sys
import json
import pprint as pp
import logging

from csv import reader, writer
import reportlab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Table
from reportlab.platypus import TableStyle
import shutil
import webbrowser
# with Gooey, it appears the script has to be launched with 'python <script>'
from gooey import Gooey, GooeyParser

# How many months out do you want labels.  1 would be standard.
months_out = 1
# determine 'next' month
next_month = (dt.date.today() + dt.timedelta(months_out * 365/12))

months = ['January', 'February', 'March', 'April','May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


#@Gooey
def parse_script_args(home_dir, local_path, local_filename):
    logger = logging.getLogger(__name__)
    logger.info('parsing args')

    #parser = GooeyParser()
    parser = argparse.ArgumentParser()

    parser.add_argument('--month',
                        dest='month',
                        default='October',
                        help='Choose the month for the report.')
    parser.add_argument('--date',
                        dest='date',
                        help='Choose any date in the month for which you wosh to generate labels.',)
                        #widget='DateChooser')
    parser.add_argument('--localfile',
                        dest='localfile',
                        help='Use a file that you have manually downloaded from LikeSew.',)
                        #widget='FileChooser')
    parser.add_argument('--debug',
                        action='store_true',
                        help='Enable debug logging.')
    try:
        args = parser.parse_args()
    except Exception as e:
        print(e)
    return args

def configure_logging(args, local_path):

    log_level = 'INFO'
    if args.debug:
        log_level = 'DEBUG'
    numeric_level = getattr(logging, log_level)

    logger = logging.getLogger(__name__)
    logger.setLevel(numeric_level)

    log_path = os.path.join(local_path, 'logs')
    if not os.path.exists(log_path):
        os.makedirs(log_path)

    fh = logging.FileHandler(os.path.join(log_path, f'birthday_labels-{next_month.year}{next_month.month:02d}.log'))
    fm = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s:%(lineno)d %(message)s')
    fh.setFormatter(fm)
    logger.addHandler(fh)

def format_row(r):
    return '{} {}, {}, {}, {}, {}\n'.format(r[2], r[1], r[7], r[8], r[9], r[10])

# TODO: make passwd a config variable
def read_config():
    logger = logging.getLogger(__name__)
    try:
        with open('lsos.conf') as f:
            config = json.load(f)
            logger.debug(config)
            return config
    except Exception as e:
        logger.error(f"Could not read config: {e}")
        sys.exit(1)

def fetch_customers(url, apikey, limit=250, page_info='', chunk=1, customers = ''):
    logger = logging.getLogger(__name__)
    # cache the page_info we receive and use it for the query if we got one
    cached_page_info = page_info
    base_url = url
    logger.debug(f'Chunk {chunk}')
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
            'zip': entry['default_address']['zip'],
            'tags': entry['tags']
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

def parse_data(args, skipped, customer_list):
    logger = logging.getLogger(__name__)
    logger.info(f'Searching {len(customer_list)} customers for {args.month}')
    address_list = []
    for customer in customer_list:
        logger.debug(f'Checking: {customer}')

        for tag in customer['tags'].split(','):
            if tag == args.month:
                logger.info(f'Matched {args.month}: {customer["first_name"]} {customer["last_name"]}')

        
                if customer['first_name'] in (None, ""):
                    skipped.write('{:20}: {}\n'.format('MISSING NAME', customer))
                    logger.info(f'MISSING NAME: {customer}')
                    # customer_list.remove(customer)
                    continue

                if customer['last_name'] in (None, ""):
                    skipped.write('{:20}: {}\n'.format('MISSING NAME', customer))
                    logger.info(f'MISSING NAME: {customer}')
                    # customer_list.remove(customer)
                    continue

                if customer['address1'] in (None, ""):
                    skipped.write('{:20}: {}\n'.format('NO ADDRESS', customer))
                    logger.info(f'MISSING ADDRESS: {customer["first_name"]} {customer["last_name"]}')
                    # customer_list.remove(customer)
                    continue
                if customer['address2'] not in (None, ""):
                    customer['address1'] = f'{customer["address1"]}\n{customer["address2"]}'

                # if there is no city, skip it
                if customer['city'] in (None, ""):
                    skipped.write('{:20}: {}\n'.format('NO CITY', customer))
                    logger.info(f'MISSING CITY: {customer["first_name"]} {customer["last_name"]}')
                    # customer_list.remove(customer)
                    continue

                # if there is no state skip it
                if customer['province_code'] in (None, ""):
                    skipped.write('{:20}: {}\n'.format('NO STATE', customer))
                    logger.info(f'MISSING CITY: {customer["first_name"]} {customer["last_name"]}')
                    # customer_list.remove(customer)
                    continue

                # if there is no zip, we don't have a valid address
                if customer['zip'] in (None, ""):
                    skipped.write('{:20}: {}\n'.format('NO ZIP', customer))
                    logger.info(f'MISSING ZIP: {customer["first_name"]} {customer["last_name"]}')
                    # customer_list.remove(customer)
                    continue

                if len(customer['tags']) == 0:
                    # customer_list.remove(customer)
                    logger.info(f'NO TAGS: {customer["first_name"]} {customer["last_name"]}')
                    continue

                logger.info(f'Adding customer to mailing list: {customer}')
                mailing_address = "{} {}\n{}\n{}, {} {}".format(customer['first_name'],
                                                        customer['last_name'],
                                                        customer['address1'],
                                                        customer['city'],
                                                        customer['province_code'],
                                                        customer['zip'])

                address_list.append(mailing_address)


    logger.info(f'{len(address_list)} customers remaining')
    return address_list            

def create_pdf(customer_list, pdf_name, output_pdf):
    logger = logging.getLogger(__name__)
    if len(customer_list) == 30:
        fill_value = 0
    elif len(customer_list) < 30:
        fill_value = 30 - len(customer_list)
    else:
        fill_value = 30 - (len(customer_list) % 30)

    logger.info('Adding {} empty cells'.format(fill_value))

    fill_list = ['' for x in range(0, fill_value)]

    customer_list.extend(fill_list)
    # this breaks lists into 3
    logger.info('Chunking address list')
    chunks = [customer_list[x:x+3] for x in range(0, len(customer_list), 3)]

    # much help from https://www.blog.pythonlibrary.org/2010/09/21/reportlab-tables-creating-tables-in-pdfs-with-python/
    # doc = reportlab.platypus.SimpleDocTemplate("output/birthday_labels_{}{:02d}.pdf".format(
    # output_pdf = os.path.join(f'{local_path}',
    #                           f'birthday_labels_{next_month.year}{next_month.month:02d}.pdf')

    logger.info(f'Output going to: {output_pdf}')
    # Each printer will need to have separate configs
    # below config is for the Canon TS9100 Printer
    doc = reportlab.platypus.SimpleDocTemplate(filename=output_pdf,
                                            pagesize=letter,
                                            leftMargin=57,
                                            rightMargin=11,
                                            topMargin=11,
                                            bottomMargin=10)

    width, height = letter
    t = Table(chunks,
            rowHeights=74,
            colWidths=200)

    logger.info('address list length: {}'.format(len(customer_list)))
    num_rows = int(len(customer_list)/3)
    logger.info('rows: {}'.format(num_rows))

    logger.info('Setting Table Style')
    t.setStyle(TableStyle([('FONT', (0, 0), (2, num_rows - 1), 'Helvetica', 12)]))
    elements = [t]
    try:
        doc.build(elements)
    except Exception as e:
        logger.exception(e)
        logger.error(vars(doc))
        sys.exit(1)

def finish(output_pdf):
    logger = logging.getLogger(__name__)
    print('Finished creating PDF!')
    print('\n' * 2)
    print('#' * 40)
    print('# COMPLETED')
    print(f'# Your file is: {output_pdf}')
    print('# You can close this window now.')
    print('#' * 40)

def main():
    home_dir = os.path.expanduser('~')

    local_path = os.path.join(home_dir, 'Downloads')
    local_filename = os.path.join(f'{local_path}', '1433-edit-customers.csv')
    args = parse_script_args(home_dir, local_path, local_filename)
    with open('shopify-api-key') as f:
        apikey = f.read().rstrip()
    url = f'https://{apikey}@the-little-shop-of-stitches.myshopify.com/admin/api/2021-04/customers.json'
    customers = []
    if args.date:

        global next_month 
        next_month= args.date
        next_month = dt.datetime.strptime(next_month, '%Y-%m-%d')

    configure_logging(args, local_path)

    pdf_name = f'birthday_labels-{next_month.year}{next_month.month:02d}.pdf'

    output_pdf = os.path.join(local_path, pdf_name)

    logger = logging.getLogger(__name__)
    logger.info('STARTING')
    logger.info(f'user home is {home_dir}')

    config = read_config()

    # need to keep track of rows that are skipped
    skipped_file = os.path.join(f'{home_dir}',
                                'Downloads',
                                f'birthday_labels_skipped_{next_month.year}{next_month.month:02d}.txt')
    logger.info(f'Saving skipped customers in: {skipped_file}')

    try:
        skipped = open(skipped_file, 'w')
    except Exception as e:
        logger.error(f'Could not open {skipped_file} for write')
        sys.exit(1)


    if args.localfile:
        logger.info(f'Using local file: {args.localfile}')
        print('Using local file')
        local_filename = args.localfile
    else:
        logger.info('Fetching customers from Shopify')
        #download_report_v1(config, local_filename)
        customer_list = fetch_customers( url=url, apikey=apikey, page_info='', customers=customers)
        # logger.info(customer_list)
        # sys.exit()
        #write_customer_data(args, local_filename)
    customer_list = parse_data(args, skipped, customer_list)  
    logger.info(f'Found {len(customer_list)} customers')
    create_pdf(customer_list, pdf_name, output_pdf)
    finish(output_pdf)
    webbrowser.open(f'{skipped_file}')
    logger.info('FINISHED\n')

if __name__ == '__main__':
    main()