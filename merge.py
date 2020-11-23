# coding: utf-8
import click
from beancount import loader
from beancount.parser import printer


@click.command()
@click.option("--filepath_list", help="文件，按,分割")
@click.option("--out", help="输出文件")
def main(filepath_list, out):
    all_entries = []
    for filepath in filepath_list.split(","):
        entries, _, option_map = loader.load_file(filepath)
        all_entries += entries

    with open(out, 'w') as f:
        printer.print_entries(all_entries, file=f)
    print("output to %s" % out)


if __name__ == '__main__':
    main()
