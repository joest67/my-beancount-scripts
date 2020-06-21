from datetime import date, datetime

import click
import requests
from beancount.parser import printer
from pycookiecheat import chrome_cookies

from modules.imports import create_entry, backup
from modules.imports.exc import BaseBizException

Account_suishouji = 'Liabilities:CreditCard:SSJ'

DETAIL_URL = 'https://www.sui.com/tally/new.rmi'

headers = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36",
    "refer": "https://www.sui.com/tally/new.do",
    "origin": "https://www.sui.com"
}


def build_request(date_start: date, date_end: date):
    begin_date = date_start.strftime("%Y.%m.%d")
    end_date = date_end.strftime("%Y.%m.%d")
    request_data = {'opt': 'list2',
                    'beginDate': begin_date,
                    'endDate': end_date,
                    'cids': '0',
                    'bids': '0',
                    'sids': '0',
                    'pids': '0',
                    'memids': '0',
                    'isDesc': '0',
                    'page': '1',
                    'mids': '0'}
    return request_data


def do_request(url, data, max_retries=5):
    retry = 0
    status_code = 0
    while retry < max_retries:
        resp = requests.post(url, data=data, headers=headers, cookies=chrome_cookies(url))
        status_code = resp.status_code
        if status_code / 100 == 2:
            return resp.json()
        retry += 1
        print("retry %s times" % retry)
    raise BaseBizException("response status get %s" % status_code)


def filter_type(record):
    return record.get("tranName") == "支出"


def parse_records(*json_val_list):
    ret = []
    for json_val in json_val_list:
        for group in json_val["groups"]:
            ret += group["list"]
    return list(filter(filter_type, ret))


def fetch_records(date_start: date, date_end: date):
    # records
    processed = 0
    total_page = 1
    total_page_inited = False
    resp_list = []
    while processed < total_page:
        request_data = build_request(date_start, date_end)
        request_data["page"] = str(processed + 1)
        json_val = do_request(DETAIL_URL, request_data)
        if not total_page_inited:
            total_page = json_val["pageCount"]
            total_page_inited = True
        resp_list.append(json_val)
        processed += 1

    return parse_records(*resp_list)


"""
{'account': 515609245049, 'buyerAcount': '家庭信用开支', 'buyerAcountId': 515609245049, 'categoryIcon': 'd_com2.png',
'categoryId': 5372791554113, 'categoryName': '宝宝用品', 'content': '', 'currencyAmount': 0,
'date': {'date': 1, 'day': 1, 'hours': 21, 'minutes': 14, 'month': 5, 'seconds': 46, 'time': 1591017286000, 'timezoneOffset': -480, 'year': 120}, 
'imgId': 5372791554113, 'itemAmount': 84.9, 'memberId': 0, 'memberName': '', 'memo': '狗狗', 'projectId': 0,
'projectName': '', 'relation': '', 'sellerAcount': '', 'sellerAcountId': 0, 'tranId': 18595193216674,
'tranName': '支出', 'tranType': 1, 'transferStoreId': 0, 'url': ''}
"""
def convert(record):
    description = record["memo"] or record["categoryName"]
    date_map = record["date"]
    created = datetime.fromtimestamp(date_map["time"] / 1000)
    trade_price = real_price = str(record["itemAmount"])
    real_currency = trade_currency = "CNY"
    payee = record["buyerAcount"]
    entry = create_entry(description, created.date(), real_price, payee,
                         trade_currency, trade_price, real_currency, Account_suishouji)

    print("Importing {} at {}".format(description, created))
    return entry


@click.command()
@click.argument("start", type=click.DateTime(formats=["%Y-%m-%d"]))
@click.argument("end", type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--entry", help="Entry bean path")
@click.option("--out", default='out.bean', help="Output bean path")
def main(start, end, entry, out):
    print("%s - %s" % (start, end))
    records = fetch_records(start, end)
    print("records: %s" % len(records))
    new_entries = [convert(r) for r in records]

    mode = 'w'
    if entry is not None:
        backup(entry, out)
        mode = 'a'

    with open(out, mode) as f:
        printer.print_entries(new_entries, file=f)

    print('Outputed to ' + out)


if __name__ == '__main__':
    main()
