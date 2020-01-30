import argparse
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
from csv import reader
import reportlab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Table
from reportlab.platypus import TableStyle
import shutil
import webbrowser


home_dir = os.path.expanduser('~')
# How many months out do you want labels.  1 would be standard.
months_out = 1
# determine 'next' month
next_month = (dt.date.today() + dt.timedelta(months_out * 365/12))

# try to get file from Downloads
local_path = os.path.join(home_dir, 'Downloads')
local_filename = os.path.join(f'{local_path}', '1433-edit-customers.csv')


# local_path = os.path.join(home_dir, 'Documents')
# local_filename = os.path.join(f'{local_path}', 'bulk_customers.csv')


def parse_script_args():
    logger = logging.getLogger(__name__)
    logger.info('parsing args')
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf',
                        dest='pdf_name')
    parser.add_argument('--debug',
                        action='store_true')
    parser.add_argument('--local',
                        action='store_true')
    args = parser.parse_args()
    return args

def configure_logging(args):

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
    


    # logging.basicConfig(format='%(asctime)-15s %(levelname)-5s:%(lineno)s %(message)s',
    #                 level=logging.DEBUG,
    #                 filename=os.path.join(log_path, f'birthday_labels-{next_month.year}{next_month.month:02d}.log'))


def format_row(r):
    return '{} {}, {}, {}, {}, {}\n'.format(r[2], r[1], r[7], r[8], r[9], r[10])




# TODO: make passwd a config variable
def read_config():
    logger = logging.getLogger(__name__)
    try:
        with open('lsos.conf') as f:
            config = json.load(f)
            logger.debug(config)
            passwd = config['password']
            user = config['user']

    except Exception as e:
        logger.error(f"Could not read config: {e}")

  

def download_report():
    logger = logging.getLogger(__name__)
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    try:
        driver = webdriver.Chrome('./drivers/chromedriver.exe', options=options)
        try:
            driver.get("https://www.thelittleshopofstitches.com/admin")
        except Exception as e:
            logger.error(f'Driver failed to get site: {e}')
    except Exception as e:
        logger.error(f'Failed to create driver: {e}')
        sys.exit(1)

    username = driver.find_element_by_xpath('//*[@id="username"]')
    try:
        login_button = driver.find_element_by_css_selector('#submitBtn')
        logger.info('Finding login button')
    except Exception as e:
        logger.error(f"Couldn't find the login button: {e}")
    actions = action_chains.ActionChains(driver)
    actions.send_keys(keys.Keys.F12)
    actions.move_to_element(username)
    actions.send_keys_to_element(username, user)
    actions.send_keys_to_element(username, keys.Keys.TAB)
    actions.send_keys(passwd)
    actions.send_keys(keys.Keys.ENTER)
    actions.perform()
    if 'Home' in driver.page_source:
        logger.info('Made it to the home page')
    else:
        logger.error('Failed to log in')
        sys.exit()
    # Selenium can't interact with the system dialog for file downloads, so get the cookies
    # and pass them to requests, so it can perform the download.
    # get_cookies returns an array of dicts, one per cookie
    in_cookies = driver.get_cookies()
    # pp.pprint(in_cookies)

    c = RequestsCookieJar()
    for cookie in in_cookies:
        # pp.pprint(f'cookie={cookie}')
        args = {k.lower(): cookie[k] for k in cookie if k not in ['name', 'value']}
        # httpOnly is for browsers? try rmoving it
        args.pop('httponly', None)
        # requests expects 'expires' and noy 'expiry'
        try:
            args['expires']=args['expiry']
            args.pop('expiry', None)
        except KeyError:
            pass
            # print('no expiry in this cookie.  moving on.')
        logger.debug(f'args={args}')
        c.set(cookie['name'],
            cookie['value'],
            **args
            )
    # pp.pprint(c)

    url = "https://littleshopofstitches.rainadmin.com/pos-app/customers/download-customers-csv.php"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:72.0) Gecko/20100101 Firefox/72.0'}
    r = requests.get(url,
                    headers=headers,
                    params={"type": "edit_custs"},
                    cookies=c)
    logger.debug(r.headers)
    # print(r.content)
    #local_filename = os.path.join(f'{local_path}', 'bulk_customers.csv')
    logger.info(f'Saving response to {local_filename}')
    with open(local_filename, 'w') as f:
        f.write(str(r.content.decode('utf-8')))

def parse_file(skipped, pdf_name, output_pdf):
    logger = logging.getLogger(__name__)
    logger.info('Reading file: {}'.format(local_filename))

    # sometimes LikeSew changes the report.
    # set the indices for the columns here so they're easier to change
    # address_index = 8
    # city_index = 9
    # state_index = 10
    # zip_index = 11
    # birthday_index = 13


    # list to hold the addresses
    address_list = []

    logger.info('Next month: {}'.format(next_month))
    try:
        with open(local_filename, newline="") as csvfile:
            address_input = reader(csvfile)
            headers = next(address_input)[0:]

            # see if we can set the indices based on the headers
            lastname_index = headers.index('Last Name')
            firstname_index = headers.index('First Name')
            address_index = headers.index('Address')
            city_index = headers.index('City')
            state_index = headers.index('State')
            zip_index = headers.index('Zip')
            birthday_index = headers.index('Birthday')


            for row in address_input:

                # if the birthday is null skip it
                if row[birthday_index] in (None, ''):
                    continue

                try:
                    bday = dt.datetime.strptime(row[birthday_index], '%m/%d/%Y')
                except ValueError as err:
                    logger.debug('Unexpected date format: {}'.format(row[birthday_index]))
                    logger.debug('Trying %m/%d/%y')
                    try:
                        bday = dt.datetime.strptime(row[birthday_index], '%m/%d/%y')
                    except ValueError as err:
                        logger.debug('Trying %m/%d')
                        try:
                            bday = dt.datetime.strptime(row[birthday_index], '%m/%d')
                        except:
                            logger.debug('Trying %b-%m')
                            try:
                                bday = dt.datetime.strptime(row[birthday_index], '%d-%b')
                            except ValueError as err:
                                logger.error('Skipping invalid birthday: {} {}: {}'.format(row[2], row[1], row[birthday_index]))
                                skipped.write('{:20}: {}'.format('INVALID BIRTHDAY', format_row(row)))
                            continue

                if bday.month != next_month.month:
                    # print('bday is {}, skipping'.format(bday))
                    continue

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
                mailing_address = "{} {}\n{}\n{}, {} {}".format(address_dict['First Name'],
                                                                address_dict['Last Name'],
                                                                address_dict['Address'],
                                                                address_dict['City'],
                                                                address_dict['State'],
                                                                address_dict['Zip'])

                address_list.append(mailing_address)
    except Exception as e:
        logger.error('Could not open {}: {}'.format(local_filename, e))
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

    # if not pdf_name:
    #     pdf_name = f'birthday_labels-{next_month.year}{next_month.month:02d}.pdf'
    # else:
    #     pdf_name = f'birthday_labels-{next_month.year}{next_month.month:02d}.pdf'
    logger.info(f'Output going to: {output_pdf}')
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
    args = parse_script_args()
    configure_logging(args)
    pdf_name = args.pdf_name
    if not pdf_name:
        pdf_name = f'birthday_labels-{next_month.year}{next_month.month:02d}.pdf'
    else:
        pdf_name = f'birthday_labels-{next_month.year}{next_month.month:02d}.pdf'

    output_pdf = os.path.join(local_path, pdf_name)

    logger = logging.getLogger(__name__)
    logger.info('STARTING')
    logger.info(f'user home is {home_dir}')

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

    logger.info('Using local file')    
    # if args.local:
    #     logger.info('Using local file')
    # else:
    #     logger.info('Retrieving file from website')
    #     # disabling the report download because LikeSew doesn't like it
    #     #download_report()
    parse_file(skipped, pdf_name, output_pdf)  
    finish(output_pdf)
    webbrowser.open(f'{skipped_file}')
    logger.info('FINISHED\n')

if __name__ == '__main__':
    main()