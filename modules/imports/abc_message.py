# coding: utf-8
import re
from datetime import datetime, date

import click
from beancount.parser import printer

from modules.imports import create_entry, ACCOUNT_ABC

PATTERN = r'(.*)((\d{2}月\d{2}日)(\d{2}:[0-9]{2})?)(.*(支付宝|财付通))?(.*)人民币(-?[0-9.]*).*'
compiled = re.compile(PATTERN)
today = datetime.now().today()


def convert(line):
    if not compiled.match(line):
        print("not matched line, " + line)
        return
    parts = compiled.match(line).groups()
    _date = datetime.strptime(parts[2], '%m月%d日')
    time = date(today.year, _date.month, _date.day)
    if parts[5] is None:
        payee = '默认'
        desc = parts[6]
    else:
        payee = parts[5]
        desc = '%s_%s' % (parts[5], parts[6])
    if '-' in parts[7]:
        trade_price = cost = parts[7].strip('-')
    else:
        trade_price = cost = '-' + parts[7]
        # print("收入忽略, " + line)
        # return
    trade_currency = real_currency = 'CNY'
    print("Importing {} at {}".format(desc, time))
    return create_entry(desc, time, cost, payee,
                        trade_currency, trade_price, real_currency, ACCOUNT_ABC)


@click.command()
@click.argument("filepath")
@click.option("--out", default='abc.bean', help="账号文件")
def main(filepath, out):
    lines = [line.strip('\n') for line in open(filepath)]
    if len(lines) <= 0:
        print("file content is empty, " + filepath)
        exit(1)
    print("read file %s lines" % len(lines))

    new_entries = list(filter(lambda line: line is not None, [convert(r) for r in lines]))

    with open(out, 'w') as f:
        printer.print_entries(new_entries, file=f)

    print('Outputed to ' + out)


if __name__ == '__main__':
    main()
