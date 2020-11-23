#!/bin/env python
# coding: utf-8

"""
资金流（）和信息流对账
"""
from collections import defaultdict
from datetime import date

import click
from beancount import loader
from beancount.core.compare import hash_entries
from beancount.core.number import ZERO
from beancount.parser import printer
from beancount.query import query

from modules.imports import backup, ACCOUNT_ABC, Account_CMB, ACCOUNT_CREDIT_CMB
from modules.imports.colors import bcolors

MAX_ERROR_AMOUNT = 5  # 5元


class GlobalContext(object):
    def __init__(self):
        self.aborted = False
        self.interrupted = False
        self.entry_changed = False
        self.interactive = False
        self.show_paired = False


def _get_number(r):
    if hasattr(r.position, "units"):
        return r.position.units.number
    return r.position.get_currency_units("CNY").number


def sum_records(records):
    if records is None or len(records) == 0:
        return ZERO
    else:
        return sum(_get_number(r) for r in records)


class CompareGroup(object):

    def __init__(self, info, mm, _date):
        self.info = info
        self.mm = mm
        self.date = _date
        self._pair_records, self._common_keys = self.__init_pair_key()

    def __init_pair_key(self):
        info_pair_records = defaultdict(list)
        for r in self.info.records:
            info_pair_records[self.get_pair_key(r)].append(r)
        mm_pair_records = defaultdict(list)
        for r in self.mm.records:
            mm_pair_records[self.get_pair_key(r)].append(r)
        common_keys = (info_pair_records.keys() | mm_pair_records.keys()) ^ {None}
        ret = [(info_pair_records.get(common_key), mm_pair_records.get(common_key))
               for common_key in common_keys if common_key is not None]
        return ret, common_keys

    def get_pair_key(self, record):
        return getattr(record, "pair_key")

    def diff_amount(self):
        return self.info.sum() - self.mm.sum()

    @property
    def pair_records(self):
        return self._pair_records

    @property
    def common_keys(self):
        return self._common_keys

    def sort_by_amount(self, r):
        return r.position

    def _single_mm_records(self):
        return [record for record in self.mm.records
                if self.get_pair_key(record) not in self.common_keys]

    @property
    def single_mm_records(self):
        return sorted(self._single_mm_records(), key=self.sort_by_amount)

    def _single_info_records(self):
        return [record for record in self.info.records
                if self.get_pair_key(record) not in self.common_keys]

    @property
    def single_info_records(self):
        return sorted(self._single_info_records(), key=self.sort_by_amount)

    def has_remain_records(self):
        return len(self.single_mm_records) > 0 or len(self.single_info_records) > 0

    def has_remain_pair_records(self):
        return len(self.single_mm_records) > 0 and len(self.single_info_records) > 0


class SameGroup(object):
    def __init__(self, records, all_records):
        self.records = records
        self.all_records_map = {r.id: idx for idx, r in enumerate(all_records)}

    def sum(self):
        return sum_records(self.records)

    def hash_ids(self):
        return [r.id for r in self.records]

    def _index(self, record):
        return self.all_records_map.get(record.id)

    def join_index(self):
        return ",".join([str(self._index(r)) for r in self.records])


class PairGuess(object):
    def __init__(self, compare_group: CompareGroup):
        self.compare_group = compare_group
        self._prompt_hint = None
        self._paired_records = []
        self.__pair()

    def __pair(self):
        if not self.compare_group.has_remain_pair_records():
            return

        mm_assemble_records = self.group_by(self.compare_group.single_mm_records)
        info_assemble_records = self.group_by(self.compare_group.single_info_records)
        for mm in mm_assemble_records:
            for info in info_assemble_records:
                if mm.sum() == info.sum():
                    self._paired_records.append((info, mm))
                    # 只匹配一次 TODO
                    break

    def group_by(self, records):
        ret = defaultdict(list)
        for r in records:
            ret[r.narration].append(r)
        return [SameGroup(group_records, records) for group_records in ret.values()]

    def has_paired_records(self):
        return len(self.paired_records) > 0

    @property
    def prompt_hint(self):
        if not self.has_paired_records():
            return ""
        hint = ";".join([a.join_index() + ":" + b.join_index() for a, b in self.paired_records])
        return hint

    @property
    def paired_records(self):
        return self._paired_records


class RecordStorage(object):

    info_account = ["Liabilities:CreditCard:SSJ"]
    mm_debit_account = [Account_CMB, ACCOUNT_ABC]
    mm_credit_account = [ACCOUNT_CREDIT_CMB]
    mm_account = mm_debit_account + mm_credit_account

    def __init__(self):
        self.entries = None
        self.option_map = None
        self.hash_entry_map = None
        self.start_date = None
        self.end_date = None
        self._info_records = None
        self._mm_records = None

    def init(self, filepath, start, end):
        self.start_date = start
        self.end_date = end
        self.entries, _, self.option_map = loader.load_file(filepath)
        self.hash_entry_map, _ = hash_entries(self.entries)
        self.init_data()

    def init_data(self):
        self._info_records = self._query_records(self.start_date, self.end_date, self.info_account)
        self._mm_records = self._query_mm_records(self.start_date, self.end_date)

    def output_to_file(self, dest_filepath):
        backup_file = backup(dest_filepath)
        with open(dest_filepath, 'w') as f:
            printer.print_entries(self.entries, file=f)
        print("rewrite success %s, bakup %s" % (dest_filepath, backup_file))

    @classmethod
    def arrange_by_date(cls, items):
        group_by = defaultdict(list)
        for item in items:
            group_by[str(item.date)].append(item)

        ret = {}
        for k, v in group_by.items():
            _date = v[0].date
            b = TransactionBlock(_date, v)
            ret[_date] = b
        return ret

    def _query_mm_records(self, date_start, date_end) -> dict:
        account_param = " or ".join(["account = '%s'" % account for account in self.mm_account])
        mm_credit_account_param = " or ".join(["account = '%s'" % account for account in self.mm_credit_account])
        query_params = (date_start, date_end, mm_credit_account_param, account_param)
        bql = "SELECT id, date, narration, position, account, entry_meta('pair_key') as pair_key where" \
              " date >= {} and date <= {} " \
              " and ((number(cost(position)) >= 0 and ({})) or (number(cost(position)) < 0 and ({})))" \
              "order by date desc"
        _, items = query.run_query(self.entries, self.option_map, bql, *query_params)
        return self.arrange_by_date(items)

    def _query_records(self, date_start, date_end, accounts) -> dict:
        account_param = " or ".join(["account = '%s'" % account for account in accounts])
        query_params = (date_start, date_end, account_param)
        bql = "SELECT id, date, narration, position, account, entry_meta('pair_key') as pair_key where" \
              " date >= {} and date <= {} " \
              " and ({})" \
              "order by date desc"
        _, items = query.run_query(self.entries, self.option_map, bql, *query_params)
        return self.arrange_by_date(items)

    @property
    def info_records(self):
        return self._info_records

    @property
    def mm_records(self):
        return self._mm_records

    def get_sorted_dates(self):
        dates = self.info_records.keys() | self.mm_records.keys()
        return sorted(dates)

    def get_by_date(self, _date) -> CompareGroup:
        info = self.info_records.get(_date, TransactionBlock(_date))
        mm = self.mm_records.get(_date, TransactionBlock(_date))
        return CompareGroup(info, mm, _date)

    def pair_records(self, hash_ids, pair_key):
        for hash_id in hash_ids:
            self.hash_entry_map.get(hash_id).meta["pair_key"] = pair_key


storage = RecordStorage()
global_context = GlobalContext()


class TransactionBlock(object):

    def __init__(self, _date: date, records=None):
        self.date = _date
        self.records = [] if records is None else records

    def sum(self):
        return sum_records(self.records)

    def __eq__(self, other):
        if not isinstance(other, TransactionBlock):
            return False
        return self.sum() == other.sum()


class Printer(object):
    RECORD_TEMPLATE = "{0}{1}: {2}"
    INTERACTIVE_TEMPLATE = "[{0}]{1}: {2}"
    PAIR_TEMPLATE = "{}: ({},{})"

    @classmethod
    def get_detail(cls, record):
        if hasattr(record.position, "units"):
            return record.position
        return record.position.to_string(parens=False)

    @classmethod
    def print_normal_record(cls, compare_group):
        cls._print_with_color(cls._format_records(compare_group.single_info_records), bcolors.OKBLUE)
        cls.print_split_line()
        cls._print_with_color(cls._format_records(compare_group.single_mm_records), bcolors.OKGREEN)

    @classmethod
    def _format_records(cls, records, prefix=""):
        if records is None:
            return ""
        _records = sorted(records, key=lambda r: r.position)
        return "\n".join([cls.RECORD_TEMPLATE.format(prefix, record.narration, cls.get_detail(record))
                          for record in _records])

    @classmethod
    def _print_with_color(cls, _str, colors=""):
        print(colors + _str + bcolors.ENDC)

    @classmethod
    def print_interactive_record(cls, compare_group):
        for idx, record in enumerate(compare_group.single_info_records):
            record_str = cls.INTERACTIVE_TEMPLATE.format(idx, record.narration, cls.get_detail(record))
            cls._print_with_color(record_str, bcolors.OKBLUE)
        cls.print_split_line()
        for idx, record in enumerate(compare_group.single_mm_records):
            record_str = cls.INTERACTIVE_TEMPLATE.format(idx, record.narration, cls.get_detail(record))
            cls._print_with_color(record_str, bcolors.FAIL)

    @classmethod
    def print_split_line(cls, content="", splitter='-', size=20, colors=""):
        if len(colors) > 0:
            print(colors + content.center(size, splitter) + bcolors.ENDC)
        else:
            print(content.center(size, splitter))

    @classmethod
    def print_date_split(cls, _date):
        cls.print_split_line(_date, '=', 40, colors=bcolors.WARNING)

    @classmethod
    def print_pair_record(cls, paired):
        _sum = lambda records: sum(_get_number(r) for r in records)
        _detail = lambda records: ','.join([r.narration for r in records])
        _str = "\n".join([cls.PAIR_TEMPLATE.format(-_sum(p[0]), _detail(p[0]), _detail(p[1])) for p in paired])
        cls._print_with_color(_str, bcolors.GRAY)


def process_cmp_result(compare_group):
    colors = "" if abs(compare_group.diff_amount()) <= MAX_ERROR_AMOUNT else bcolors.FAIL
    Printer._print_with_color("信息流对比资金流差值：({}-{})={}"
                              .format(-compare_group.info.sum(), -compare_group.mm.sum(),
                                      -(compare_group.diff_amount())),
                              colors=colors)

    if global_context.show_paired and len(compare_group.pair_records) > 0:
        Printer.print_pair_record(compare_group.pair_records)
        Printer.print_split_line()

    if global_context.interactive and compare_group.has_remain_pair_records():
        start_interactive_handle(compare_group)
    else:
        if compare_group.has_remain_records():
            Printer.print_normal_record(compare_group)


def get_detail(record):
    if hasattr(record.position, "units"):
        return record.position
    return record.position.to_string(parens=False)


def build_pair_key(compare_group, info_record_ids):
    idx = info_record_ids.split(",")[0]
    return compare_group.single_info_records[int(idx)].id


def start_interactive_handle(compare_group):
    Printer.print_interactive_record(compare_group)
    try:
        handle_input(compare_group)
    except EOFError:
        global_context.interrupted = True
    except KeyboardInterrupt:
        global_context.aborted = True


def check_pair_amount(info_update_records, mm_update_records):
    a = abs(sum(_get_number(r) for r in info_update_records))
    b = abs(sum(_get_number(r) for r in mm_update_records))
    diff = abs(a - b)
    if diff < 1:
        return True
    print("amount diff %s, discard pair operation", diff)
    return False


def parse_pair_response(input_str):
    # reg pattern compare
    try:
        return [pair.split(":") for pair in input_str.strip(";:").split(";")]
    except:
        print("input format error, " + input_str)
        return []


def handle_input(compare_group):
    pair_guess = PairGuess(compare_group)
    input_hint = 'input pair action:'
    if pair_guess.has_paired_records():
        input_hint += '[default: %s]' % pair_guess.prompt_hint
    action = input(input_hint + ">")
    if len(action) <= 0 and pair_guess.has_paired_records():
        action = pair_guess.prompt_hint
    elif len(action.strip(' ')) <= 0:
        return

    paired = parse_pair_response(action)
    for info_record_ids, mm_record_ids in paired:
        pair_key = build_pair_key(compare_group, info_record_ids)
        assert pair_key is not None, "pair_key is null"

        info_update_records = [compare_group.single_info_records[int(idx)]
                               for idx in info_record_ids.split(',')]
        mm_update_records = [compare_group.single_mm_records[int(idx)]
                             for idx in mm_record_ids.split(',')]
        check_passed = check_pair_amount(info_update_records, mm_update_records)
        if check_passed:
            update_hashes = {r.id for r in info_update_records} | {r.id for r in mm_update_records}
            storage.pair_records(update_hashes, pair_key)
            global_context.entry_changed = True


@click.command()
@click.option("--show_paired", default=True, help="是否展示已配对数据", type=click.BOOL)
@click.option("--interactive", default=False, help="对账模式", type=click.BOOL)
@click.option("--start", help="开始日期", type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--end", help="截止日期", type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--filepath", help="账号文件")
def main(show_paired, interactive, start: date, end: date, filepath):
    storage.init(filepath, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    global_context.interactive = interactive
    global_context.show_paired = show_paired

    dates_list = storage.get_sorted_dates()
    for _date in dates_list:
        compare_group = storage.get_by_date(_date)
        Printer.print_date_split(str(_date))
        process_cmp_result(compare_group)

        if global_context.interrupted:
            print("exit after saving")
            break

        if global_context.aborted:
            print("exit without saving")
            exit(0)

    if global_context.entry_changed:
        storage.output_to_file(filepath)


if __name__ == '__main__':
    main()
