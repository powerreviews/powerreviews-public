# Copyright (c) 2021 PowerReviews, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# N/A
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import logging
import math
import time

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

# Variables used to get an OAuth token
oauth_url = 'https://enterprise-api.powerreviews.com/oauth2/token'
oauth_headers = {
    'Content-Type': 'application/x-www-form-urlencoded'
}
oauth_params = {
    'grant_type': 'client_credentials'
}
client_id = ''
client_secret = ''

# Variables used to make requests to EAPI
gateway_headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}
gateway_url = 'https://enterprise-api.powerreviews.com/v1/reviews'
gateway_params = {
    'include_media': 'true',
    'include_syndication': 'true',
    'pwr_publication_status': 'Approved',
    'updated_date': '1588876227000'
}

# Constants
MAX_PAGES = math.ceil(math.pow(2, 18))
MAX_LIMIT = 100
BACKOFF_TIME_LIMIT = 256

# Globals used for calculating aggregates for end of script reporting
page_count = 1
total_review_count = 0
timeout_count = 0
min_limit_reached = 100

# Globals used for changing url parameters
next_page_id = None

# Logging
logging.basicConfig(filename='EAPI_paging.log', level=logging.INFO)
logger = logging.getLogger('test_paging')
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


def get_access_token():
    if client_id == '' or client_secret == '':
        raise Exception('Set the client id and secret.')
    logger.info(f'Get OAuth token url: {oauth_url}')
    # logger.info(f'Get OAuth token headers: {oauth_headers}')
    r = requests.post(oauth_url, params=oauth_params, headers=oauth_headers,
                      auth=HTTPBasicAuth(client_id, client_secret))
    logger.info(f'Get OAuth token status code: {r.status_code}')
    body = r.json()
    if r.status_code != 200:
        raise Exception(body)
    return body['access_token']


def read_reviews():
    s = requests.Session()
    s.mount('https://', HTTPAdapter(pool_connections=1, pool_maxsize=1))
    logger.info(f'gateway_url: {gateway_url}')
    # logger.info(f'gateway_headers: {gateway_headers}')
    global aggregate_time, page_count, access_token, total_review_count, \
        next_page_id, timeout_count, min_limit_reached
    retry_count = 0
    backoff_time_sec = 1
    limit = MAX_LIMIT

    while page_count <= MAX_PAGES:
        if next_page_id is not None:
            gateway_params['next_page'] = str(next_page_id)
        gateway_params['limit'] = str(limit)
        start = time.time()
        logger.info(f'PAGE {page_count} call url: {gateway_url} with params {gateway_params}')
        # logger.info(f'PAGE {page_count} headers: {gateway_headers}')
        r = s.get(gateway_url, params=gateway_params, headers=gateway_headers)
        logger.info(f'PAGE {page_count} status_code: {r.status_code}')
        if r.status_code == 401:
            gateway_headers['Authorization'] = get_access_token()
            continue
        elif r.status_code != 200 and backoff_time_sec < BACKOFF_TIME_LIMIT:
            retry_count += 1
            timeout_count += 1
            backoff_time_sec *= 2
            limit = math.ceil(limit / 2)
            min_limit_reached = min(min_limit_reached, limit)
            logger.info(
                f'PAGE {page_count} 504 TIMEOUT retrying in {backoff_time_sec}s with limit {limit} '
                f'| retry count {retry_count}')
            time.sleep(backoff_time_sec)
            continue
        elif backoff_time_sec >= BACKOFF_TIME_LIMIT:
            raise Exception(f'Backoff time limit {BACKOFF_TIME_LIMIT} reached')
        backoff_time_sec = 1
        retry_count = 0
        if limit < MAX_LIMIT:
            limit = math.ceil(limit * 2)
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT
        body = r.json()
        # logger.info(body)
        # Here is where you would process the response body
        review_count = body['count']
        total_review_count += review_count
        logger.info(f'PAGE {page_count} review_count: {review_count}')
        logger.info(f'PAGE {page_count} total review_count: {total_review_count}')
        end = time.time()
        timing = end - start
        logger.info(f'PAGE {page_count} time to complete response: {timing}s')
        page_count += 1
        aggregate_time += timing
        if r.status_code != 200:
            raise Exception(body)
        if 'next_page' not in body:
            # Completed paging
            break
        next_page_id = body['next_page']
        # logger.info(f'next_page={next_page_start_id}')
    page_count -= 1


access_token = get_access_token()
# logger.info(access_token)
gateway_headers['Authorization'] = access_token
aggregate_time = 0
read_reviews()
logger.info(f'Total time: {aggregate_time}s')
logger.info(f'Average time per request: {aggregate_time / page_count}s')
logger.info(f'Total pages retrieved: {page_count}')
logger.info(f'Total reviews retrieved: {total_review_count}')
logger.info(f'Total timeouts: {timeout_count}')
logger.info(f'Minimum limit reached: {min_limit_reached}')
