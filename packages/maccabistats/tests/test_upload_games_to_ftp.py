import pytest

from maccabistats.github_actions_scripts import upload_maccabipedia_games_to_ftp as ftp_upload

def _set_ftp_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for env_name in ftp_upload.FTP_ENV_NAMES:
        monkeypatch.setenv(env_name, values.get(env_name, 'set'))


def test_empty_host_fails_before_loading_games_or_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    # A missing GitHub secret reaches the job as an empty string, and ftplib.FTP(host='')
    # never connects, so login() died with a NoneType.sendall that named no secret.
    _set_ftp_env(monkeypatch, MACCABIPEDIA_FTP='')
    monkeypatch.setattr(ftp_upload, 'MaccabiPediaSource', _fail_if_called)
    monkeypatch.setattr(ftp_upload.ftplib, 'FTP', _fail_if_called)

    with pytest.raises(RuntimeError, match='MACCABIPEDIA_FTP$'):
        ftp_upload.upload_maccabipedia_games_to_maccabipedia_ftp()


def test_every_missing_secret_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_ftp_env(monkeypatch, MACCABIPEDIA_FTP='  ', MACCABIPEDIA_FTP_PASSWORD='')
    monkeypatch.delenv('MACCABIPEDIA_FTP_USERNAME')

    with pytest.raises(RuntimeError) as raised:
        ftp_upload.upload_maccabipedia_games_to_maccabipedia_ftp()

    assert str(raised.value).endswith('MACCABIPEDIA_FTP, MACCABIPEDIA_FTP_USERNAME, MACCABIPEDIA_FTP_PASSWORD')


def test_set_secrets_reach_ftp_login(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    games_file = tmp_path / 'maccabipedia.games'
    games_file.write_bytes(b'games')
    _set_ftp_env(monkeypatch, MACCABIPEDIA_FTP='ftp.example.org', MACCABIPEDIA_FTP_USERNAME='bot',
                 MACCABIPEDIA_FTP_PASSWORD='secret')
    monkeypatch.setattr(ftp_upload, 'MaccabiPediaSource', lambda: _StubSource(games_file))
    ftp_calls: list[tuple] = []
    monkeypatch.setattr(ftp_upload.ftplib, 'FTP', lambda host: _StubFtp(host, ftp_calls))

    ftp_upload.upload_maccabipedia_games_to_maccabipedia_ftp()

    assert ftp_calls == [('connect', 'ftp.example.org'), ('login', 'bot', 'secret'),
                         ('stor', 'STOR domains/maccabipedia.co.il/public_html/MaccabiPedia.games', b'games')]


class _StubSource:
    def __init__(self, games_file) -> None:
        self._games_file = games_file

    def find_last_created_source_maccabi_games_file(self):
        return self._games_file


class _StubFtp:
    def __init__(self, host: str, calls: list[tuple]) -> None:
        self._calls = calls
        calls.append(('connect', host))

    def login(self, user: str, passwd: str) -> None:
        self._calls.append(('login', user, passwd))

    def storbinary(self, command: str, file) -> None:
        self._calls.append(('stor', command, file.read()))


def _fail_if_called(*args: object, **kwargs: object) -> None:
    raise AssertionError('must not be reached when FTP secrets are missing')
