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
import getopt
import logging
import math
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

# Constants
PROTOCOL = 'https://'
MAX_LIMIT = 100
BACKOFF_TIME_LIMIT = 256

# Input parameters
opts: tuple = getopt.getopt(sys.argv[1:], '', [
    'client_id=',
    'client_secret=',
    'endpoint=',
    'max_pages=',
    'env=',
])[0]
client_id: str = ''
client_secret: str = ''
endpoint = ''
env = ''
max_pages = 1
for opt in opts:
    key: str = opt[0]
    value: str = opt[1]
    if 'client_id' in key:
        client_id = value
    if 'client_secret' in key:
        client_secret = value
    if 'endpoint' in key:
        endpoint = value
    if 'max_pages' in key:
        max_pages: int = int(value)
    if 'env' in key:
        env = value

if endpoint not in ['reviews', 'questions']:
    endpoint = 'reviews'
if max_pages < 0:
    max_pages = 1
if env not in ['dev', 'qa', 'prod']:
    env = 'dev'

# Logging
format_str = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(
    filename='.'.join(['_'.join([sys.argv[0][:-3], '_', env, endpoint, client_id, str(time.time_ns())]), 'log']),
    level=logging.INFO, format=format_str)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter(format_str))
logger.addHandler(ch)

if endpoint is None:
    raise Exception('No EAPI endpoint defined')

# Variables used to make requests to EAPI
domain = 'enterprise-api.powerreviews.com'
if env is not None and (env == 'dev' or env == 'qa'):
    domain = env + '-' + domain
gateway_url = PROTOCOL + domain + '/v1/' + endpoint
oauth_url = PROTOCOL + domain + '/oauth2/token'
oauth_headers = {
    'Content-Type': 'application/x-www-form-urlencoded'
}
oauth_params = {
    'grant_type': 'client_credentials'
}

# Globals used for calculating aggregates for end of script reporting
page_count = 1
total_requests = 0
total_ugc_count = 0
total_image_count = 0
total_video_count = 0
total_merchant_response_count = 0
total_answer_count = 0
timeout_count = 0
min_limit_reached = 100
min_response_time = math.ceil(math.pow(2, 31))
max_response_time = 0


def get_access_token() -> str:
    # Variables used to get an OAuth token
    # print(f'c={client_id} s={client_secret}')
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


def page_ugc(parameters: dict) -> None:
    gateway_headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': get_access_token()
    }
    s = requests.Session()
    s.mount(PROTOCOL, HTTPAdapter(pool_connections=1, pool_maxsize=1))
    logger.info(f'Getting an OAuth token from gateway_url: {gateway_url}')
    # logger.info(f'gateway_headers: {gateway_headers}')
    global aggregate_wait_time, page_count, total_ugc_count, total_image_count, \
        total_video_count, total_merchant_response_count, total_answer_count, timeout_count, \
        min_limit_reached, min_response_time, max_response_time, total_requests
    retry_count = 0
    backoff_time_sec = 1
    limit = MAX_LIMIT
    next_page_id = None

    while page_count <= max_pages:
        if next_page_id is not None:
            parameters['next_page'] = str(next_page_id)
        parameters['limit'] = str(limit)
        logger.info(f'PAGE {page_count} call url: {gateway_url} with params {parameters}')
        # logger.info(f'PAGE {page_count} headers: {gateway_headers}')
        start = time.time()
        r = s.get(gateway_url, params=parameters, headers=gateway_headers)
        if r.status_code == 401:
            gateway_headers['Authorization'] = get_access_token()
            continue
        timing = time.time() - start
        total_requests += 1
        aggregate_wait_time += timing
        logger.info(f'PAGE {page_count} status_code: {r.status_code}')
        if r.status_code >= 500 and backoff_time_sec < BACKOFF_TIME_LIMIT:
            retry_count += 1
            timeout_count += 1
            backoff_time_sec *= 2
            limit = math.ceil(limit / 2)
            min_limit_reached = min(min_limit_reached, limit)
            logger.info(
                f'PAGE {page_count} - status_code: {r.status_code} retrying in {backoff_time_sec}s with limit {limit} '
                f'| retry count {retry_count}')
            time.sleep(backoff_time_sec)
            continue
        elif backoff_time_sec >= BACKOFF_TIME_LIMIT:
            raise Exception(f'Backoff time limit {BACKOFF_TIME_LIMIT} reached')
        if r.status_code != 200:
            raise Exception(r.json())
        if timing > max_response_time:
            max_response_time = timing
        if timing < min_response_time:
            min_response_time = timing
        backoff_time_sec = 1
        retry_count = 0
        if limit < MAX_LIMIT:
            limit = math.ceil(limit * 2)
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT
        # logger.info(r.text)
        body = r.json()
        # Process the response body
        review_count = body['count']
        total_ugc_count += review_count
        child_ugc_counts: tuple = get_child_ugc_count(body['reviews'] if 'reviews' in body else body['questions'])
        total_image_count += child_ugc_counts[0]
        total_video_count += child_ugc_counts[1]
        total_merchant_response_count += child_ugc_counts[2]
        total_answer_count += child_ugc_counts[3]
        if endpoint == 'reviews':
            logger.info(f'PAGE {page_count} review count: {review_count}')
            logger.info(f'PAGE {page_count} image count: {child_ugc_counts[0]}')
            logger.info(f'PAGE {page_count} video count: {child_ugc_counts[1]}')
            logger.info(f'PAGE {page_count} merchant response count: {child_ugc_counts[2]}')
            logger.info(f'PAGE {page_count} Total image count: {total_image_count}')
            logger.info(f'PAGE {page_count} Total video count: {total_video_count}')
            logger.info(f'PAGE {page_count} Total merchant response count: {total_merchant_response_count}')
            logger.info(f'PAGE {page_count} Total review count: {total_ugc_count}')
        if endpoint == 'questions':
            logger.info(f'PAGE {page_count} question count: {review_count}')
            logger.info(f'PAGE {page_count} answer count: {child_ugc_counts[3]}')
            logger.info(f'PAGE {page_count} Total answer count: {total_answer_count}')
            logger.info(f'PAGE {page_count} Total question count: {total_ugc_count}')
        logger.info(f'PAGE {page_count} time to complete response: {timing}s')
        page_count += 1
        if 'next_page' not in body:
            # Completed paging
            break
        next_page_id = body['next_page']
        # logger.info(f'next_page={next_page_start_id}')


def get_child_ugc_count(ugcs: list) -> tuple:
    if len(ugcs) == 0:
        return 0, 0, 0, 0
    image_count = 0
    video_count = 0
    merchant_response_count = 0
    answer_count = 0
    for ugc in ugcs:
        if 'media' in ugc:
            for media in ugc['media']:
                media_type = media['type'].lower()
                if media_type == 'image':
                    image_count += 1
                if media_type == 'video':
                    video_count += 1
                if media_type == 'answer':
                    answer_count += 1
        if 'merchant_responses' in ugc:
            merchant_response_count += len(ugc['merchant_responses'])
    return image_count, video_count, merchant_response_count, answer_count


aggregate_wait_time = 0
params = {
    'include_media': 'true',
    'include_syndication': 'true',
    'include_merchant_responses': 'true',
    # 'include_upc': 'true',
    # 'pwr_publication_status': 'Approved',
    # 'client_publication_status': 'Approved',
    # 'created_date': '1325376000000',
    # 'updated_date': '1325376000000',
    # 'locale': 'en_US',
    # 'client_specific_question_new': 'true',
    # 'merchant_id': '883243',
    # 'page_id': '1341019',
    # 'user_id': '',
}
start = time.time()
page_ugc(params)
total_time = time.time() - start
logger.info(f'Total time: {total_time}s')
logger.info(
    f'Total time spent waiting for an API response: {aggregate_wait_time}s '
    f'({(aggregate_wait_time / total_time) * 100}%)')
logger.info(f'Average time per API request (including timeouts): {aggregate_wait_time / total_requests}s')
logger.info(f'Minimum response time: {min_response_time}s')
logger.info(f'Maximum response time: {max_response_time}s')
logger.info(f'Total requests made: {total_requests}')
if endpoint == 'reviews':
    logger.info(f'Total image count: {total_image_count}')
    logger.info(f'Total video count: {total_video_count}')
    logger.info(f'Total merchant response count: {total_merchant_response_count}')
    logger.info(f'Total review count: {total_ugc_count}')
if endpoint == 'questions':
    logger.info(f'Total answer count: {total_answer_count}')
    logger.info(f'Total question count: {total_ugc_count}')
logger.info(f'Total timeouts: {timeout_count}')
logger.info(f'Minimum limit param value reached on retries: {min_limit_reached}')
