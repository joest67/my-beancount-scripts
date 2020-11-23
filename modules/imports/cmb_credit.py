import abc
import csv
from datetime import date, datetime

import eml_parser
from beancount.core import data
from beancount.core.data import Transaction
from bs4 import BeautifulSoup

from modules.imports.exc import NotSuitableImporterException
from . import create_entry
from .deduplicate import Deduplicate

Account_CMB = 'Liabilities:CreditCard:CMB'
trade_area_list = {
    'CN': 'CNY',
    'US': 'USD',
    'JP': 'JPY',
    'HK': 'HKD',
    'BG': 'BG',
    'NL': 'NL'
}

"""
TODO
1. 过滤 自动购、自动还款 的记录
2. 识别美元和其他货币
"""

BLACK_KEYWORD_LIST = ["自动购", "自动还款"]


def read_content(filename):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except Exception as e:
        pass


def change_currency(currency):
    if currency == '':
        return 'CNY'
    if currency not in trade_area_list:
        print('Unknown trade area: ' + currency +
              ', please append it to ' + __file__)
        return currency
    return trade_area_list[currency]


def get_date(detail_date, post_date, today, description):
    _date_str = post_date if len(detail_date.strip(' ')) <= 0 else detail_date
    if '分期' in description:
        _date_str = post_date
    _date = datetime.strptime(_date_str, '%m%d')
    ret = date(today.year, _date.month, _date.day)
    if ret > today:
        ret = ret.replace(year=ret.year - 1)
    return ret


class BaseParser(object):

    __metaclass__ = abc.ABCMeta

    def __init__(self, filename):
        self.filename = filename
        self.today = date.today()

    @abc.abstractmethod
    def match(self) -> bool:
        return False

    @abc.abstractmethod
    def parse(self):
        pass

    @staticmethod
    def create_mock_meta():
        meta = {}
        return data.new_metadata('beancount/core/testing.beancount', 12345, meta)

    def create_entry(self, description, time, real_price, payee,
                     trade_currency, trade_price, real_currency) -> Transaction:
        return create_entry(description, time, real_price, payee,
                            trade_currency, trade_price, real_currency, Account_CMB)


def import_suishouji(entry: Transaction):
    from modules.imports.suishouji import import_record
    d = entry.date
    dt = datetime(year=d.year, month=d.month, day=d.day)
    print(entry.postings[0].units.number)
    import_record(dt, str(entry.postings[0].units.number), entry.narration)


class EmlParser(BaseParser):

    def __init__(self, filename):
        super(EmlParser, self).__init__(filename)
        self.byte_content = read_content(filename)
        self.parsed_eml = None
        self.soup = None

    def match(self) -> bool:
        if not self.filename.endswith('eml'):
            return False

        parsed_eml = eml_parser.eml_parser.decode_email_b(self.byte_content, include_raw_body=True)
        if '招商银行信用卡' in parsed_eml['header']['subject']:
            self.after_match(parsed_eml)
            return True

        return False

    def after_match(self, *args):
        self.parsed_eml = args[0]
        self.soup = BeautifulSoup(self.parsed_eml['body'][0]['content'], 'html.parser')

    def ignore_record(self, description):
        return any([keyword in description for keyword in BLACK_KEYWORD_LIST])

    def parse(self):
        transactions = []
        # balance = d.select('#fixBand16')[0].text.replace('RMB', '').strip()
        # date_range = d.select('#fixBand38 div font')[0].text.strip()
        # transaction_date = dateparser.parse(
        #     date_range.split('-')[1].split('(')[0])
        # transaction_date = date(transaction_date.year,
        #                         transaction_date.month, transaction_date.day)
        # self.date = transaction_date
        # balance = '-' + \
        #     d.select('#fixBand40 div font')[0].text.replace(
        #         '￥', '').replace(',', '').strip()
        # entry = Balance(
        #     account=Account_CMB,
        #     amount=Amount(Decimal(balance), 'CNY'),
        #     meta={},
        #     tolerance='',
        #     diff_amount=Amount(Decimal('0'), 'CNY'),
        #     date=self.date
        # )
        # transactions.append(entry)

        bands = self.soup.select('#fixBand35 #loopBand2>table>tr')
        for idx, band in enumerate(bands):
            tds = band.select('td #fixBand15 table table td')
            if len(tds) == 0:
                continue
            # ""|trade_date|post_date|description|
            start_pos = 0
            full_descriptions = tds[start_pos + 3].text.strip().split('-')
            payee = full_descriptions[0]
            if len(full_descriptions) == 1:
                description = full_descriptions[0]
            else:
                description = '-'.join(full_descriptions[1:])

            trade_date = tds[start_pos + 1].text.strip()
            post_date = tds[start_pos + 2].text.strip()
            time = get_date(trade_date, post_date, self.today, description)

            if self.ignore_record(description):
                print("ignore hit black keyword {}".format(description))
                continue
            trade_currency = real_currency = 'CNY'
            trade_price = real_price = tds[start_pos + 4].text \
                .replace('￥', '') \
                .replace('\xa0', '').strip()
            if "$" in real_price:
                print("ignore us record {}".format(description))
                continue
            # trade_price = tds[start_pos + 6].text.replace('\xa0', '').strip()
            # trade_currency = change_currency(tds[start_pos + 7].text.strip())
            print("{}: Importing {} at {}".format(idx, description, time))

            entry = self.create_entry(description, time, real_price, payee,
                                      trade_currency, trade_price, real_currency)
            import_suishouji(entry)
            transactions.append(entry)

        return transactions


class CsvParser(BaseParser):

    def __init__(self, filename):
        super(CsvParser, self).__init__(filename)

    def match(self) -> bool:
        """"format 交易日期,	记账日期,	交易摘要,	交易地点,	卡号末四位,	人民币金额,	交易地金额"""
        # 正则匹配 todo
        matched = self.filename is not None and self.filename.endswith("csv") and \
            'cmb' in self.filename and 'credit' in self.filename
        return matched


    def parse(self):
        ret = []
        with open(self.filename) as csv_file:
            reader = csv.reader(csv_file, delimiter=',')
            for idx, line in enumerate(reader):
                if idx == 0:
                    continue
                time = datetime.strptime(line[0].strip('\t'), '%Y-%m-%d').date()
                full_descriptions = line[2].strip().split('-')
                payee = full_descriptions[0]
                if len(full_descriptions) == 1:
                    description = full_descriptions[0]
                else:
                    description = '-'.join(full_descriptions[1:])
                real_currency = 'CNY'
                real_price = line[4].strip()\
                    .replace('￥', '') \
                    .replace('$', '')
                trade_price = line[6].strip()
                trade_currency = change_currency(line[3].strip())

                print("{}: Importing {} at {}".format(idx, description, time))
                entry = self.create_entry(description, time, real_price, payee, trade_currency, trade_price, real_currency)
                import_suishouji(entry)
                ret.append(entry)
        return ret


implements = (EmlParser, CsvParser)


class ParserFactory(object):

    @staticmethod
    def get_matched_impl(filepath):
        for impl_cls in implements:
            impl = impl_cls(filepath)
            if impl.match():
                return impl
        return None


class CMBCredit(object):

    def __init__(self, filename, byte_content, entries, option_map):
        impl = ParserFactory.get_matched_impl(filename)
        if impl is None:
            raise NotSuitableImporterException("Not CMB!")
        self.impl = impl
        self.deduplicate = Deduplicate(entries, option_map)
        self.date = date.today()

    def parse(self):
        ret = []
        transactions = self.impl.parse()
        for idx, trans in enumerate(transactions):
            amount = trans.postings[0].units.number
            duplicate = self.do_duplicate_check(trans, amount)
            if not duplicate:
                ret.append(trans)
        # self.deduplicate.apply_beans()
        return transactions

    def do_duplicate_check(self, entry, amount):
        return False
        # return self.deduplicate.find_duplicate(entry, -amount, None, Account_CMB)
