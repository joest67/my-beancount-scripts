# coding: utf-8
import click
from beancount.parser import printer

from modules.imports.cmb_credit import CMBCredit
from modules.imports.cmb_debit import CMBDebit
from modules.imports.exc import NotSuitableImporterException

importers = [CMBCredit, CMBDebit]


def write_to_file(all_entries, out_filepath):
    with open(out_filepath, 'w') as f:
        printer.print_entries(all_entries, file=f)
    print('Outputed to ' + out_filepath)


@click.command()
@click.argument("path")
@click.option("--out", default="out.bean", help="bean 文件输出地址")
def main(path, out):
    all_entries = []
    for filepath in path.split(","):
        part_entries = import_account(filepath)
        if part_entries is not None:
            all_entries += part_entries

    # todo duplicate fix
    write_to_file(all_entries, out)


def import_account(filepath):
    instance = None
    for _importer in importers:
        try:
            with open(filepath, 'rb') as f:
                instance = _importer(filepath, f.read(), [], {})
            break
        except NotSuitableImporterException:
            pass
        except Exception as e:
            print(e)
    if instance is None:
        print("No suitable importer for file: %s" % filepath)
        exit(1)
    return instance.parse()


if __name__ == '__main__':
    main()
