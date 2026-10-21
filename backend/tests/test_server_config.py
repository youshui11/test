"""复用根目录模型配置时只解析声明，不执行示例服务器代码。"""
import pytest
from backend.config import Settings


def test_server_config_read_without_executing_source(tmp_path):
    source = tmp_path / 'server.py'
    source.write_text('raise RuntimeError("must not execute")\nmodel = DeepSeek(id="deepseek-v4-flash", '
                      'api_key="source-key", use_thinking=False)\n', encoding='utf-8')
    settings = Settings(_env_file=None, jwt_secret='x' * 32, llm_config_source='server',
                        llm_server_config_path=source, llm_api_key='ignored-env-key')
    assert settings.llm_api_key.get_secret_value() == 'source-key'
    assert settings.llm_model == 'deepseek-v4-flash'
    assert settings.llm_provider == 'deepseek'
    assert settings.llm_base_url == 'https://api.deepseek.com'
    assert settings.llm_use_thinking is False
    source.write_text('model = DeepSeek(id="deepseek-v4-pro", api_key="new-source-key")\n', encoding='utf-8')
    refreshed = Settings(_env_file=None, jwt_secret='x' * 32, llm_config_source='server', llm_server_config_path=source)
    assert refreshed.llm_api_key.get_secret_value() == 'new-source-key'
    assert refreshed.llm_model == 'deepseek-v4-pro'
    assert refreshed.llm_use_thinking is None


def test_server_config_rejects_expressions_without_executing_them(tmp_path):
    source = tmp_path / 'server.py'
    source.write_text('model = DeepSeek(api_key=unknown_function())', encoding='utf-8')
    with pytest.raises(ValueError, match='字面量') as error:
        Settings(_env_file=None, jwt_secret='x' * 32, llm_config_source='server',
                 llm_server_config_path=source, llm_api_key='private-test-secret')
    assert 'private-test-secret' not in str(error.value)


def test_env_config_remains_available_without_server_file(tmp_path):
    settings = Settings(_env_file=None, jwt_secret='x' * 32, llm_config_source='env',
                        llm_server_config_path=tmp_path / 'missing.py', llm_api_key='env-key')
    assert settings.llm_api_key.get_secret_value() == 'env-key'
