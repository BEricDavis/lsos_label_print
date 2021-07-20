#!/usr/bin/env python
# Monitor the website for The Little Shop of Stitches
# Send notifications when things are down
import boto3
import datetime
import os
import sys
import urllib3
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def configure_logging():
    logger = logging.getLogger(__name__)
    sh = logging.StreamHandler()
    fm = logging.Formatter(fmt='%(asctime)s %(levelname)s %(funcName)s: %(lineno)d %(message)s')
    sh.setFormatter(fm)
    logger.addHandler(sh)
    logger.setLevel(logging.INFO)

def main_urllib(event=None, context=None):
    lsos_url = 'https://www.thelittleshopofstitches.com'

    secondary_urls = ['https://www.rainpos.com',
                      'https://www.redroosterquilts.com',
                      'https://www.likesewwebsites.com']

    message = ''

    configure_logging()
    logger = logging.getLogger(__name__)

    http = urllib3.PoolManager()
    response = http.request('GET', lsos_url)
    if response.status == 200:
        logger.info('Success')
    else:
        publish_metric(lsos_url)
        message += '<html><table>\n'
        message += '<tr><td>{} is failing! </td><td style="background-color: palevioletred;">[{}]</td></tr>\n'.format(lsos_url, response.status)
        for url in secondary_urls:
            response = http.request('GET', url)
            if response.status == 200:
                #message += '<tr><td>{} is successful</td><td></td>&nbsp;</tr>\n'.format(url)
                print('{} is successful'.format(url))
            else:
                publish_metric(url)
                message += '<tr><td style="font-color: red;">{} is failing!</td><td>[{}]</td></tr>\n'.format(url, response.status)
        message += '</table></html>'
    if message:
        send_email(body=message)

def publish_metric(url):
    ct = datetime.datetime.utcnow()
    client = boto3.client('cloudwatch', region_name='us-east-1')

    response = client.put_metric_data(
        Namespace='LSOS',
        MetricData=[
            {
            'MetricName': 'FailedRequests',
            'Dimensions':[
                {
                    'Name': 'URL',
                    'Value': url
                }
            ],
            'Timestamp': ct,
            'Value': 1.0,
            'Unit': 'Count'
            },
        ]
    )

def publish_message(body=None):
    sns = boto3.client('sns')
    response = sns.publish(TopicArn=os.getenv('TOPIC_ARN'),
                            Message=body,
                            Subject='LSOS Outage')

def send_email(body=None):
    logger = logging.getLogger(__name__)
    logger.info('Sending email')
    logger.debug('Email Body:{}'.format(body))
    #return None
    client = boto3.client('ses')

    try:
        response = client.send_email(
            Source=os.environ.get('FROM_ADDRESS', 'feralmonkey@gmail.com'),
            Destination={
                'ToAddresses': [os.environ.get('RECIPIENTS', 'feralmonkey@gmail.com')]
                
            },
            Message={
                'Subject': {
                    'Data': 'LSOS Outage'
                },
                'Body': {
                    'Html': {
                        'Data': body
                    }
                }
            },
            ReplyToAddresses=[
                os.environ.get('FROM_ADDRESS', 'feralmonkey@gmail.com')]
            )
        logger.info(response)
    except Exception as e:
        logger.error(e)

if __name__ == "__main__":
    main_urllib()