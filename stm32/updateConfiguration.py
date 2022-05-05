import argparse
import dotenv
import sys

dotenv_file = dotenv.find_dotenv()
dotenv.load_dotenv(dotenv_file)

for key, value in zip(sys.argv[1::2], sys.argv[2::2]):
    if not key.startswith('--'):
        raise ValueError('Missing -- in environment key')
    key = key.strip('--')
    dotenv.set_key(dotenv_file, key, value)
