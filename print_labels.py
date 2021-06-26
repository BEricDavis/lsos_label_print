import argparse
from reportlab.platypus.doctemplate import NextPageTemplate
from selenium import webdriver
from selenium.webdriver.common import action_chains, keys
import datetime as dt
import requests
from requests.cookies import RequestsCookieJar
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
                        default='July',
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

def get_customersv1(url, page_info, apikey, full_customer_list):
    logger = logging.getLogger(__name__)
    cache = page_info
    r = requests.get(url)
    body_json = r.json()
    logger.debug(body_json)
    link_header = r.headers.get('Link')
    logger.info(f'LINK: {link_header}')
    full_customer_list.append(body_json['customers'])
    for _ in link_header.split(','):
        if _.find('next') > 0:
            #url = _.split(';')[0].strip('<>').replace('https://', f'https://{apikey}@') + "?limit=250"
            page_info = _.split(';')[0].strip('<>').split('page_info=')[1]
            print(page_info)

    if cache != page_info:
        return get_customers(url, page_info, apikey, full_customer_list)

    return None

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

def get_customers(url, apikey, page_info='', limit='', full_customer_list='' ):
    """Fetch products recursively."""
    logger = logging.getLogger(__name__)
    cache = page_info.strip()
    logger.info(f'url: {url}')
    # GET https://{shop}.myshopify.com/admin/api/2019-07/products.json?page_info=hijgklmn&limit=3
    logger.info(f'cache: {cache}')
    r = requests.get(url)
    body_json = r.json()
    link_header = r.headers.get('Link')
    logger.info(f'LINK: {link_header}')
    full_customer_list.append(body_json['customers'])

    # products = shopify.Product.find(limit=limit, page_info=page_info)
    # cursor = shopify.ShopifyResource.connection.response.headers.get('Link')
    for _ in link_header.split(','):
        if _.find('next') > 0:
            page_info = _.split(';')[0].strip('<>').split('page_info=')[1]
            logger.info(f'page_info: {page_info}')
    #print('chunk fetched: %s' % chunk)
    if cache != page_info:
        logger.info(f'cache != page_info: {cache != page_info}')
        return get_customers(url, apikey, page_info, limit=limit, full_customer_list=full_customer_list)
    return None    


def download_report(url, apikey, full_customer_list):
    logger = logging.getLogger(__name__)

    rel = ''
    logger.info(url)
    r = requests.get(url)
    logger.debug(f'Headers: {r.headers}')
    body_json = r.json()
    logger.info(body_json)
    # customer_data is a list of dicts containing customer info
    customer_data = body_json['customers']
    full_customer_list.append(customer_data)

    link_header = r.headers.get('Link')
    next_page_url, rel = link_header.split(';')
    next_page_url = next_page_url.lstrip('<').rstrip('>').replace('https://', f'https://{apikey}@') + "?limit=250"
    logger.info(next_page_url)
    logger.info(rel)

    while rel:
        logger.info('calling download_report')
        download_report(next_page_url, apikey, full_customer_list)

    print(f'{full_customer_list}')


def write_customer_data(customer_data, local_filename):
    logger = logging.getLogger(__name__)
    with open(local_filename, 'w', newline='') as data_file:
        csv_writer = writer(data_file)
        count = 0
        for customer in customer_data:
            bday = 0
            logger.debug(f'CUSTOMER: customer')
            for tag in customer['tags'].split(','):
                if tag in months:
                    bday = tag
                else:
                    logger.debug(f'{customer} has invalid birthday: {bday}')
            if bday == args.month:
                for address in customer['addresses']:
                    if address['default'] is True:
                        if count == 0:
                            header = address.keys()
                            csv_writer.writerow(header)
                            count += 1
                        csv_writer.writerow(address.values())
    # sys.exit(0)

def parse_file(args, skipped, pdf_name, output_pdf, local_filename):
    logger = logging.getLogger(__name__)
    logger.info('Reading file: {}'.format(local_filename))

    address_list = []

    try:
        with open(local_filename, newline="") as csvfile:
            address_input = reader(csvfile)
            headers = next(address_input)[0:]

            # shopify

            lastname_index = headers.index('last_name')
            firstname_index = headers.index('first_name')
            address_index = headers.index('address1')
            city_index = headers.index('city')
            state_index = headers.index('province_code')
            zip_index = headers.index('zip')

            for row in address_input:

                # If there is no name, skip it
                if row[firstname_index] in (None, "") and row[lastname_index] in (None, ""):
                    skipped.write('{:20}: {}'.format('MISSING NAME', format_row(row)))
                    continue
                # if there is no address, skip it
                if row[address_index] in (None, ""):
                    skipped.write('{:20}: {}'.format('NO ADDRESS', format_row(row)))
                    continue
                # if there is no city, skip it
                if row[city_index] in (None, ""):
                    skipped.write('{:20}: {}'.format('NO CITY', format_row(row)))
                    continue
                # if there is no state skip it
                if row[state_index] in (None, ""):
                    skipped.write('{:20}: {}'.format('NO STATE', format_row(row)))
                    continue
                # if there is no zip, we don't have a valid address
                if row[zip_index] in (None, ""):
                    skipped.write('{:20}: {}'.format('NO ZIP', format_row(row)))
                    continue

                address_dict = {key: value for key, value in zip(headers, row)}
                logger.debug(address_dict)
                mailing_address = "{} {}\n{}\n{}, {} {}".format(address_dict['first_name'],
                                                                address_dict['last_name'],
                                                                address_dict['address1'],
                                                                address_dict['city'],
                                                                address_dict['province_code'],
                                                                address_dict['zip'])

                address_list.append(mailing_address)

    except Exception as e:
        logger.exception('Could not open {}: {}'.format(local_filename, e))
        print(e)
        sys.exit(1)
    logger.info('Found {} addresses'.format(len(address_list)))

    skipped.close()

    if len(address_list) == 30:
        fill_value = 0
    elif len(address_list) < 30:
        fill_value = 30 - len(address_list)
    else:
        fill_value = 30 - (len(address_list) % 30)

    logger.info('Adding {} empty cells'.format(fill_value))

    fill_list = ['' for x in range(0, fill_value)]

    address_list.extend(fill_list)
    # this breaks lists into 3
    logger.info('Chunking address list')
    chunks = [address_list[x:x+3] for x in range(0, len(address_list), 3)]

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

    logger.info('address list length: {}'.format(len(address_list)))
    num_rows = int(len(address_list)/3)
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

    # keep one backup file for troubleshooting
    try:
        logger.info(f'Backing up {local_filename}')
        shutil.copyfile(local_filename, '{}.bak'.format(local_filename))
    except Exception as e:
        logger.error('Could not create backup of {}: {}'.format(local_filename, e))

    # delete input file so the same one can be reused next month
    try:
        logger.info(f'Deleting {local_filename}')
        os.remove(local_filename)
    except Exception as e:
        logger.error('Failed to remove input file: {}'.format(e))

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
        logger.info('Retrieving file from website')
        #download_report_v1(config, local_filename)
        customer_list = fetch_customers( url=url, apikey=apikey, page_info='', customers=customers)
        logger.info(customer_list)
        sys.exit()
        #write_customer_data(args, local_filename)
    parse_file(args, skipped, pdf_name, output_pdf, local_filename)  
    finish(output_pdf)
    webbrowser.open(f'{skipped_file}')
    logger.info('FINISHED\n')

if __name__ == '__main__':
    main()