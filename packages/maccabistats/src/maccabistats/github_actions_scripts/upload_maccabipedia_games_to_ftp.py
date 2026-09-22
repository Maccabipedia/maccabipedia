import ftplib
import logging
import os

from maccabistats.parse.maccabipedia.maccabipedia_source import MaccabiPediaSource

logging.basicConfig(format='%(message)s', level=logging.INFO)

MACCABIPEDIA_GAMES_FILE_NAME_ON_FTP = 'MaccabiPedia.games'  # We use this file name in our Telegram bot
MACCABIPEDIA_FTP_FOLDERS_PREFIX = 'domains/maccabipedia.co.il/public_html/'


FTP_ENV_NAMES = ('MACCABIPEDIA_FTP', 'MACCABIPEDIA_FTP_USERNAME', 'MACCABIPEDIA_FTP_PASSWORD')


def _read_ftp_credentials() -> tuple[str, str, str]:
    # A missing GitHub secret reaches the job as an empty string, and ftplib.FTP(host='')
    # never connects, so login() dies with an unrelated NoneType.sendall. Name the secrets instead.
    missing_env_names = [name for name in FTP_ENV_NAMES if not os.environ.get(name, '').strip()]
    if missing_env_names:
        raise RuntimeError(f'Missing or empty FTP secrets: {", ".join(missing_env_names)}')

    ftp_address, ftp_username, ftp_password = (os.environ[name] for name in FTP_ENV_NAMES)
    return ftp_address, ftp_username, ftp_password


def upload_maccabipedia_games_to_maccabipedia_ftp() -> None:
    ftp_address, ftp_username, ftp_password = _read_ftp_credentials()

    logging.info('Loading MaccabiPedia games')
    latest_maccabipedia_games_file = MaccabiPediaSource().find_last_created_source_maccabi_games_file()
    logging.info(f'Last maccabipedia games file: {latest_maccabipedia_games_file}')

    maccabipedia_ftp = ftplib.FTP(host=ftp_address)
    maccabipedia_ftp.login(user=ftp_username,
                           passwd=ftp_password)

    logging.info('Logged in to MaccabiPedia FTP')

    full_remote_ftp_file_path = f'{MACCABIPEDIA_FTP_FOLDERS_PREFIX}{MACCABIPEDIA_GAMES_FILE_NAME_ON_FTP}'
    logging.info(f'Starting to upload latest maccabipedia games file: {latest_maccabipedia_games_file} '
                 f'to FTP at: {full_remote_ftp_file_path}')

    with open(latest_maccabipedia_games_file, 'rb') as maccabipedia_games_file:
        maccabipedia_ftp.storbinary(f'STOR {full_remote_ftp_file_path}',
                                    maccabipedia_games_file)

    logging.info(f'Uploaded {latest_maccabipedia_games_file} successfully to FTP')


if __name__ == '__main__':
    upload_maccabipedia_games_to_maccabipedia_ftp()
