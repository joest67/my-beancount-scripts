import argparse

from pathlib import Path
from shutil import copyfile
from beancount import loader
from beancount.parser import printer

from modules.imports.alipay import Alipay
from modules.imports.citic_credit import CITICCredit
from modules.imports.cmb_credit import CMBCredit
from modules.imports.cmbc_credit import CMBCCredit
from modules.imports.exc import NotSuitableImporterException
from modules.imports.icbc_debit import ICBCDebit
from modules.imports.wechat import WeChat
from modules.imports.yuebao import YuEBao

parser = argparse.ArgumentParser("import")
parser.add_argument("path", help="CSV Path")
parser.add_argument(
    "--entry", help="Entry bean path (default = main.bean)", default='main.bean')
parser.add_argument("--out", help="Output bean path", default='out.bean')
args = parser.parse_args()

entries, errors, option_map = loader.load_file(args.entry)

importers = [Alipay, WeChat, CITICCredit,
             CMBCCredit, CMBCredit, YuEBao, ICBCDebit]
instance = None
for importer in importers:
    try:
        with open(args.path, 'rb') as f:
            file_bytes = f.read()
            instance = importer(args.path, file_bytes, entries, option_map)
        break
    except NotSuitableImporterException:
        pass
    except Exception as e:
        print(e)

if instance is None:
    print("No suitable importer!")
    exit(1)

new_entries = instance.parse()

mode = 'w'
main_filepath = args.entry
if main_filepath is not None and len(main_filepath) > 0 and Path(main_filepath).is_file():
    copyfile(main_filepath, args.out)
    mode = 'a'

with open(args.out, mode) as f:
    printer.print_entries(new_entries, file=f)

print('Outputed to ' + args.out)
exit(0)
"""
file = parser.parse_one('''
2018/01/15 * "测试" "测试"
  Assets:Test 300 CNY
  Income:Test

''')
print(file.postings)


file.postings[0] = file.postings[0]._replace(
    units=file.postings[0].units._replace(number=100))
print(file.postings[0])

data = printer.format_entry(file)
print(data)
"""
