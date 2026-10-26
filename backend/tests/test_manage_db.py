"""数据库维护命令必须显式选择操作；升级只在临时数据库验证。"""
import asyncio

import pytest
from sqlalchemy import inspect, text

from backend import manage_db
from backend.database import connect_database


@pytest.mark.parametrize('arguments', [
    ['--help'], ['check', '--help'], ['init', '--help'], ['upgrade', '--help'],
])
def test_help_does_not_read_settings_or_connect(arguments, monkeypatch, capsys):
    def forbidden():
        raise AssertionError('帮助命令不应读取本机配置或连接数据库')

    monkeypatch.setattr(manage_db, 'Settings', forbidden)
    with pytest.raises(SystemExit) as result:
        manage_db.main(arguments)
    assert result.value.code == 0
    assert 'usage:' in capsys.readouterr().out


@pytest.mark.parametrize('arguments', [[], ['unknown'], ['upgrade', '--admin', 'admin']])
def test_invalid_command_cannot_fall_back_to_initialization(arguments, monkeypatch):
    def forbidden():
        raise AssertionError('无效命令不应读取配置或修改数据库')

    monkeypatch.setattr(manage_db, 'Settings', forbidden)
    with pytest.raises(SystemExit) as result:
        manage_db.main(arguments)
    assert result.value.code == 2


@pytest.mark.parametrize('command', ['check', 'init', 'upgrade'])
def test_explicit_command_dispatches_only_requested_operation(command, monkeypatch):
    settings = object()
    invoked = []
    monkeypatch.setattr(manage_db, 'Settings', lambda: settings)

    def operation(name):
        async def run(*arguments):
            invoked.append((name, arguments))
        return run

    for name in ('check_database', 'initialize', 'upgrade_database'):
        monkeypatch.setattr(manage_db, name, operation(name))
    manage_db.main([command])
    expected = {'check': 'check_database', 'init': 'initialize', 'upgrade': 'upgrade_database'}
    arguments = (settings, None, None) if command == 'init' else (settings,)
    assert invoked == [(expected[command], arguments)]


def test_admin_password_mismatch_stops_before_database_work(monkeypatch):
    answers = iter(['first-password', 'different-password'])
    monkeypatch.setattr(manage_db.getpass, 'getpass', lambda _: next(answers))

    def forbidden():
        raise AssertionError('密码不一致时不应连接数据库')

    monkeypatch.setattr(manage_db, 'Settings', forbidden)
    with pytest.raises(SystemExit, match='两次密码不一致'):
        manage_db.main(['init', '--admin', 'admin'])


def test_upgrade_preserves_legacy_rows_and_is_repeatable(tmp_path):
    async def verify():
        engine, _ = connect_database(f'sqlite+aiosqlite:///{tmp_path / "legacy.db"}')
        try:
            async with engine.begin() as connection:
                await connection.execute(text('CREATE TABLE knowledge_base '
                    '(id INTEGER PRIMARY KEY, file_id TEXT, chunk_text TEXT)'))
                await connection.execute(text("INSERT INTO knowledge_base VALUES (1, 'old', '原有资料')"))
                await manage_db.upgrade(connection)
                await manage_db.upgrade(connection)
                row = (await connection.execute(text(
                    'SELECT id, file_id, chunk_text, chunk_index FROM knowledge_base'))).one()
                assert tuple(row) == (1, 'old', '原有资料', None)
                tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
                assert set(tables) == {'users', 'sessions', 'messages', 'uploads', 'knowledge_base', 'ingest_jobs'}
        finally:
            await engine.dispose()

    asyncio.run(verify())
