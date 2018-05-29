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

def format_row(r):
    return '{} {}, {}, {}, {}, {}\n'.format(r[2], r[1], r[7], r[8], r[9], r[10])

# How many months out do you want labels.  1 would be standard.
months_out = 1
# determine 'next' month
next_month = (dt.date.today() + dt.timedelta(months_out * 365/12))
home_dir = os.path.expanduser('~')
local_path = f'{home_dir}/Documents'

log_path = f'{local_path}/logs'
if not os.path.exists(log_path):
    os.makedirs(log_path)

logging.basicConfig(format='%(asctime)-15s %(levelname)-5s %(message)s',
                    level=logging.INFO,
                    filename='{}/birthday_labels_{}{:02d}.log'.format(log_path,
                                                                      next_month.year,
                                                                      next_month.month))
logging.info('STARTING')

logging.info('user home is {}'.format(home_dir))

# need to keep track of rows that are skipped
skipped_file = '{}/Documents/birthday_labels_skipped_{}{:02d}.txt'.format(home_dir,
                                                                          next_month.year,
                                                                          next_month.month)
try:
    skipped = open(skipped_file, 'w')
except Exception as e:
    logging.error('Could not open skipped file for write'.format(skipped_file))

# TODO: make passwd a config variable
try:
    with open('lsos.conf') as f:
        config = json.load(f)
        logging.debug(config)
        passwd = config['password']
        user = config['user']

except Exception as e:
    logging.error(f"Could not read config: {e}")

options = webdriver.ChromeOptions()
options.add_argument('headless')
driver = webdriver.Chrome('./drivers/chromedriver.exe', chrome_options=options)
driver.get("https://www.thelittleshopofstitches.com/admin")

username = driver.find_element_by_xpath('//*[@id="username"]')
try:
    login_button = driver.find_element_by_css_selector('#submitBtn')
    logging.info('Finding login button')
except Exception as e:
    logging.error(f"Couldn't find the login button: {e}")
actions = action_chains.ActionChains(driver)
actions.send_keys(keys.Keys.F12)
actions.move_to_element(username)
actions.send_keys_to_element(username, user)
actions.send_keys_to_element(username, keys.Keys.TAB)
actions.send_keys(passwd)
actions.send_keys(keys.Keys.ENTER)
actions.perform()
if 'Home' in driver.page_source:
    logging.info('Made it to the home page')
else:
    logging.error('Failed to log in')
    sys.exit()
# Selenium can't interact with the system dialog for file downloads, so get the cookies
# and pass them to requests, so it can perform the download.
# get_cookies returns an array of dicts, one per cookie
in_cookies = driver.get_cookies()
#pp.pprint(in_cookies)

c = RequestsCookieJar()
for cookie in in_cookies:
    #pp.pprint(f'cookie={cookie}')
    args = {k.lower(): cookie[k] for k in cookie if k not in ['name', 'value']}
    # httpOnly is for browsers? try rmoving it
    args.pop('httponly', None)
    # requests expects 'expires' and noy 'expiry'
    try:
        args['expires']=args['expiry']
        args.pop('expiry', None)
    except KeyError:
        pass
        #print('no expiry in this cookie.  moving on.')
    logging.debug(f'args={args}')
    c.set(cookie['name'],
          cookie['value'],
          **args
          )
#pp.pprint(c)


url = "https://littleshopofstitches.rainadmin.com/pos-app/customers/download-customers-csv.php"
r = requests.get(url,
                 params={"type": "edit_custs"},
                 cookies=c)
logging.debug(r.headers)
#print(r.content)
local_filename = f'{local_path}/bulk_customers.csv'
with open(local_filename, 'w') as f:
    f.write(str(r.content.decode('utf-8')))


logging.info('Reading file: {}'.format(local_filename))

# list to hold the addresses
address_list = []

logging.info('Next month: {}'.format(next_month))
try:
    with open(local_filename, newline="") as csvfile:
        address_input = reader(csvfile)
        headers = next(address_input)[0:]
        for row in address_input:

            # if the birthday is null skip it
            if row[12] in (None, ''):
                continue

            try:
                bday = dt.datetime.strptime(row[12], '%m/%d/%Y')
            except ValueError as err:
                logging.debug('Unexpected date format: {}'.format(row[12]))
                logging.debug('Trying %m/%d/%y')
                try:
                    bday = dt.datetime.strptime(row[12], '%m/%d/%y')
                except ValueError as err:
                    logging.debug('Trying %m/%d')
                    try:
                        bday = dt.datetime.strptime(row[12], '%m/%d')
                    except:
                        logging.error('Skipping invalid birthday: {} {}: {}'.format(row[2], row[1], row[12]))
                        skipped.write('{:20}: {}'.format('INVALID BIRTHDAY', format_row(row)))
                        continue

            if bday.month != next_month.month:
                # print('bday is {}, skipping'.format(bday))
                continue

            # if there is no address, skip it
            if row[7] in (None, ""):
                skipped.write('{:20}: {}'.format('NO ADDRESS', format_row(row)))
                continue
            # if there is no city, skip it
            if row[8] in (None, ""):
                skipped.write('{:20}: {}'.format('NO CITY', format_row(row)))
                continue
            # if there is no state skip it
            if row[9] in (None, ""):
                skipped.write('{:20}: {}'.format('NO STATE', format_row(row)))
                continue
            # if there is no zip, we don't have a valid address
            if row[10] in (None, ""):
                skipped.write('{:20}: {}'.format('NO ZIP', format_row(row)))
                continue




            address_dict = {key: value for key, value in zip(headers, row)}
            mailing_address = "{} {}\n{}\n{}, {} {}".format(address_dict['First Name'],
                                                            address_dict['Last Name'],
                                                            address_dict['Address'],
                                                            address_dict['City'],
                                                            address_dict['State'],
                                                            address_dict['Zip'])
            #print('{}\n{}\n'.format(mailing_address, bday))

            address_list.append(mailing_address)
except Exception as e:
    logging.error('Could not open {}: {}'.format(local_filename, e))
logging.info('Found {} addresses'.format(len(address_list)))

skipped.close()

if len(address_list) == 30:
    fill_value = 0
elif len(address_list) < 30:
    fill_value = 30 - len(address_list)
else:
    fill_value = 30 - (len(address_list) % 30)

logging.info('Adding {} empty cells'.format(fill_value))

fill_list = ['' for x in range(0, fill_value)]

address_list.extend(fill_list)
# this breaks lists into 3
chunks = [address_list[x:x+3] for x in range(0, len(address_list), 3)]

# much help from https://www.blog.pythonlibrary.org/2010/09/21/reportlab-tables-creating-tables-in-pdfs-with-python/
#doc = reportlab.platypus.SimpleDocTemplate("output/birthday_labels_{}{:02d}.pdf".format(
logging.info('Output going to: {}'.format(local_path))
doc = reportlab.platypus.SimpleDocTemplate("{}/birthday_labels_{}{:02d}.pdf".format(
    local_path,
    str(next_month.year), next_month.month),
                                           pagesize=letter,
                                           leftMargin=72,
                                           rightMargin=13,
                                           topMargin=16,
                                           bottomMargin=36)
width, height = letter
t = Table(chunks,
          rowHeights=72,
          colWidths=200)

logging.debug('address list length: {}'.format(len(address_list)))
num_rows = int(len(address_list)/3)
logging.debug('rows: {}'.format(num_rows))

t.setStyle(TableStyle([('FONT', (0, 0), (2, num_rows - 1), 'Helvetica', 12)]))
elements = []
elements.append(t)
doc.build(elements)

# keep one backup file for troubleshooting
try:
    shutil.copyfile(local_filename, '{}.bak'.format(local_filename))
except Exception as e:
    logging.error('Could not create backup of {}: {}'.format(local_filename, e))


# delete input file so the same one can be reused next month
try:
    os.remove(local_filename)
except Exception as e:
    logging.error('Failed to remove input file: {}'.format(e))

print('Finished creating PDF!')
print('You can close this window now.')
logging.info('FINISHED\n')


