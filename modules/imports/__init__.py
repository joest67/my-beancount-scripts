import abc
import csv
import time
from datetime import date
from shutil import copyfile

from beancount.core import data
from beancount.core.amount import Amount
from beancount.core.data import Transaction, Posting
from beancount.core.number import Decimal
from beancount.query import query_compile
from beancount.query.query_env import TargetsEnvironment

from .deduplicate import Deduplicate
from .exc import NotSuitableImporterException
from ..accounts import *

ACCOUNT_ABC = 'Liabilities:DebitCard:ABC'
Account_CMB = 'Liabilities:DebitCard:CMB'
ACCOUNT_CREDIT_CMB = 'Liabilities:CreditCard:CMB'

class BaseParser(object):

    __metaclass__ = abc.ABCMeta

    def __init__(self, filename, byte_content, entries, option_map):
        self.filename = filename
        self.today = date.today()
        self.deduplicate = Deduplicate(entries, option_map)
        match = self.check_match()
        if not match:
            raise NotSuitableImporterException("default raise")

    @abc.abstractmethod
    def check_match(self) -> bool:
        return False

    @abc.abstractmethod
    def parse(self):
        pass

    @staticmethod
    def create_mock_meta():
        meta = {}
        return data.new_metadata('beancount/core/testing.beancount', 12345, meta)

    def create_entry(self, description, time, real_price, payee,
                     trade_currency, trade_price, real_currency, account) -> Transaction:
        return create_entry(description, time, real_price, payee,
                            trade_currency, trade_price, real_currency, account)


class CsvContent(object):

    def __init__(self, header, rows):
        self.header = header
        self.rows = rows
        self.size = len(rows)

    def __iter__(self):
        self.pos = 0
        return self

    def __next__(self):  # type: () -> dict
        if self.pos >= self.size:
            raise StopIteration
        row = self.rows[self.pos]
        self.pos += 1
        return dict(zip(self.header, row))


class CsvReader(object):

    STRIP_CHARS = ' \t'

    def __init__(self, filename, splitter=','):
        self.filename = filename
        self.splitter = splitter

    def parse(self) -> CsvContent:
        header = None
        rows = []
        with open(self.filename) as csv_file:
            reader = csv.reader(csv_file, delimiter=',')
            for idx, line in enumerate(reader):
                if idx == 0:
                    header = self.__parse_line(line)
                    continue
                rows.append(self.__parse_line(line))
        return CsvContent(header, rows)

    def __parse_line(self, columns):  # type: (list) -> list
        return [c.strip(self.STRIP_CHARS) for c in columns]


def replace_flag(entry, flag):
    return entry._replace(flag='!')


def get_account_by_guess(from_user, description, time=None):
    if description != '':
        for key, value in descriptions.items():
            if description_res[key].findall(description):
                if callable(value):
                    return value(from_user, description, time)
                else:
                    return value
                break
    for key, value in anothers.items():
        if another_res[key].findall(from_user):
            if callable(value):
                return value(from_user, description, time)
            else:
                return value
            break
    return "Expenses:Unknown"


def create_mock_meta():
    meta = {}
    return data.new_metadata('beancount/core/testing.beancount', 12345, meta)


def create_entry(description, time, real_price, payee,
                 trade_currency, trade_price, real_currency, account_source) -> Transaction:
    account = get_account_by_guess(description, '', time)
    flag = "*"
    if account == "Unknown":
        flag = "!"

    entry = Transaction(create_mock_meta(), time, flag, payee,
                        description, data.EMPTY_SET, data.EMPTY_SET, [])

    if real_currency == trade_currency:
        data.create_simple_posting(
            entry, account, trade_price, trade_currency)
    else:
        trade_amount = Amount(Decimal(trade_price), trade_currency)
        real_amount = Amount(Decimal(abs(round(float(
            real_price), 2))) / Decimal(abs(round(float(trade_price), 2))), real_currency)
        posting = Posting(account, trade_amount,
                          None, real_amount, None, None)
        entry.postings.append(posting)

    data.create_simple_posting(entry, account_source, None, None)
    return entry


def get_income_account_by_guess(from_user, description, time=None):
    for key, value in incomes.items():
        if income_res[key].findall(description):
            return value
    return "Income:Unknown"


def get_account_by_name(name, time=None):
    if accounts.get(name, '') == '':
        return "Unknown:" + name
    else:
        return accounts.get(name)


class DictReaderStrip(csv.DictReader):
    @property
    def fieldnames(self):
        if self._fieldnames is None:
            # Initialize self._fieldnames
            # Note: DictReader is an old-style class, so can't use super()
            csv.DictReader.fieldnames.fget(self)
            if self._fieldnames is not None:
                self._fieldnames = [name.strip() for name in self._fieldnames]
        return self._fieldnames

    def __next__(self):
        if self.line_num == 0:
            # Used only for its side effect.
            self.fieldnames
        row = next(self.reader)
        self.line_num = self.reader.line_num

        # unlike the basic reader, we prefer not to return blanks,
        # because we will typically wind up with a dict full of None
        # values
        while row == []:
            row = next(self.reader)
        row = [element.strip() for element in row]
        d = dict(zip(self.fieldnames, row))
        lf = len(self.fieldnames)
        lr = len(row)
        if lf < lr:
            d[self.restkey] = row[lf:].strip()
        elif lf > lr:
            for key in self.fieldnames[lr:]:
                d[key] = self.restval.strip()
        return d


def backup(filename, dest_filepath=None):
    if dest_filepath is None or filename == dest_filepath:
        dest_filepath = '{}_{}.bak'.format(filename, str(int(time.time())))
    copyfile(filename, dest_filepath)
    return dest_filepath


class Metas(query_compile.EvalFunction):
    __intypes__ = []

    def __init__(self, operands):
        super().__init__(operands, object)

    def __call__(self, context):
        args = self.eval_args(context)
        meta = context.entry.meta
        return meta


TargetsEnvironment.functions['metas'] = Metas
