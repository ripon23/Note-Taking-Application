import argparse
import os
from getpass import getpass

from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError, PyMongoError

from .database import connect
from .security import create_account
from .validation import ApiError, account


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Create a Secure Notes administrator.')
    parser.add_argument('--email', required=True)
    parser.add_argument('--name', default='Administrator')
    args = parser.parse_args()
    db = None
    try:
        password = os.getenv('ADMIN_PASSWORD') or getpass('New admin password: ')
        values = account({'email': args.email, 'name': args.name, 'password': password, 'role': 'admin'})
        db = connect(os.environ['MONGODB_URI'])
        create_account(db, values)
        print('Administrator created.')
    except DuplicateKeyError:
        parser.exit(1, 'That account already exists.\n')
    except ApiError as error:
        parser.exit(1, f'{error}\n')
    except (KeyError, PyMongoError):
        parser.exit(1, 'Check MONGODB_URI, database permissions, and connectivity.\n')
    finally:
        if db is not None:
            db.client.close()


if __name__ == '__main__':
    main()
