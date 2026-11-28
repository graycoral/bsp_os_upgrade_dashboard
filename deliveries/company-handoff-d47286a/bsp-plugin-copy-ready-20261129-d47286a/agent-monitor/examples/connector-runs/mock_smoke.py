"""Synthetic single-board TC used by the packaged connector acceptance test."""
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--com', required=True)
args = parser.parse_args()
print(f'Mock board on {args.com}')
print('Test Result: PASS')
