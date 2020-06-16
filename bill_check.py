#!/bin/env python
# coding: utf-8

"""
资金流（）和信息流对账
"""
from collections import defaultdict
from datetime import date

from beancount import loader
from beancount.core.number import Decimal, ZERO
from beancount.query import query

info_account = ["Liabilities:CreditCard:SSJ"]
mm_account = ["Liabilities:CreditCard:CMB"]
filepath = "0615_out.bean"

entries, errors, option_map = loader.load_file(filepath)


def query_records(date_start, date_end, accounts, assemble_same_name=True) -> dict:
    account_param = " or ".join(["account = '%s'" % account for account in accounts])
    if assemble_same_name:
        bql = "SELECT date, narration, sum(position) as position where" \
              " ({}) and date >= {} and date < {} group by date, narration order by date desc"\
            .format(account_param, date_start, date_end)
    else:
        bql = "SELECT date, narration, position, account  where" \
              " ({})" \
              " and date >= {} and date < {} order by date desc"\
            .format(account_param, date_start, date_end)
    _, items = query.run_query(entries, option_map, bql)
    return arrange_by_date(items)


def _get_number(r):
    if hasattr(r.position, "units"):
        return r.position.units.number
    return r.position.get_currency_units("CNY").number


class TransactionBlock(object):

    def __init__(self, _date: date, records=None):
        self.date = _date
        self.records = records

    def add(self, record):
        self.records.append(record)

    def sum(self):
        return ZERO if self.is_empty() \
            else sum(_get_number(r) for r in self.records)

    def __eq__(self, other):
        if not isinstance(other, TransactionBlock):
            return False
        return self.sum() == other.sum()

    def is_empty(self):
        return self.records is None or len(self.records) == 0


def format_records(records, prefix):
    if records is None:
        return ""
    _records = sorted(records, key=lambda r: r.position)
    return "\n".join(["{}{}: {}".format(prefix, record.narration, record.position.to_string(parens=False))
                      for record in _records])


def arrange_by_date(items):
    group_by = defaultdict(list)
    for item in items:
        group_by[str(item.date)].append(item)

    ret = {}
    for k, v in group_by.items():
        _date = v[0].date
        b = TransactionBlock(_date, v)
        ret[_date] = b
    return ret


def print_readable_cmb_result(info, mm):
    print("信息流对比资金流差值：({}-{})={}".format(-info.sum(), -mm.sum(), -(info.sum() - mm.sum())))
    print("%s" % (format_records(info.records, '+')))
    print("".center(20, '-'))
    print("%s" % (format_records(mm.records, '-')))


def main():
    info_records = query_records("2020-05-01", "2020-06-01", info_account)
    mm_records = query_records("2020-05-01", "2020-06-01", mm_account)

    dates = info_records.keys() | mm_records.keys()
    dates_list = sorted(dates)
    for _date in dates_list:
        info = info_records.get(_date, TransactionBlock(_date))
        mm = mm_records.get(_date, TransactionBlock(_date))
        print(str(_date).center(30, '='))
        if info == mm:
            print("same")
        else:
            print_readable_cmb_result(info, mm)


if __name__ == '__main__':
    main()
