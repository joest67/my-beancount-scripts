# coding: utf-8

from datetime import datetime

from modules.imports import BaseParser, CsvReader

Account_CMB = 'Liabilities:DebitCard:CMB'

"""
交易日期,交易时间,收入,支出,余额,交易类型,交易备注
"	20200630","	13:44:45","73.64","","73.64","	代发工资","	xxxx"
"""


def build_trade_time(line):
    return datetime.strptime(line.get("交易日期") + ' ' + line.get("交易时间"), '%Y%m%d %H:%M:%S')


class CMBDebit(BaseParser):

    def check_match(self):
        matched = self.filename is not None and self.filename.endswith("csv") and \
                  'cmb' in self.filename and 'debit' in self.filename
        return matched

    def parse(self):
        ret = []
        csv_contents = CsvReader(self.filename).parse()
        print('read %s rows' % csv_contents.size)
        for idx, line in enumerate(csv_contents):
            time = build_trade_time(line)
            if len(line.get("收入")) > 0:
                print("忽略收入")
                continue

            description = line.get("交易类型") + "_" + line.get("交易备注")
            payee = "CMB-Debit"
            trade_currency = real_currency = 'CNY'
            trade_price = real_price = line.get("支出")
            # trade_currency = change_currency(line[3].strip())

            print("{}: Importing {} at {}".format(idx + 1, description, time))
            entry = self.create_entry(description, time, real_price, payee, trade_currency, trade_price, real_currency, Account_CMB)
            ret.append(entry)
        return ret
