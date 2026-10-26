# 文件作用：验证网站复用源智能体定义时保留配置并隔离每次请求的状态。
# 关联关系：覆盖 runtime.py 的智能体及团队复制和默认源文件路径。
"""确认后端调用 agent/server.py 定义的 Agent，且每次请求隔离状态。"""
import sys
from types import ModuleType
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.deepseek import DeepSeek
from backend.config import Settings
from agent.runtime import create_agent


def test_agent_source_preserves_definition_but_isolates_request_state(tmp_path, monkeypatch):
    def lookup_document(query: str) -> str:
        return query
    original = Agent(id='source-agent', name='Source Agent', instructions=['source instruction'],
                     tools=[lookup_document], model=DeepSeek(id='deepseek-v4-flash', api_key='test'),
                     db=SqliteDb(db_file=str(tmp_path / 'source.db')), add_history_to_context=True)
    module = ModuleType('agent.server')
    module.deepseek_agent = original
    monkeypatch.setitem(sys.modules, 'agent.server', module)
    source = tmp_path / 'server.py'
    source.write_text('agent=DeepSeek(id="deepseek-v4-flash", api_key="test")', encoding='utf-8')
    settings = Settings(_env_file=None, jwt_secret='x' * 32, llm_config_source='server', llm_server_config_path=source)
    first, second = create_agent(settings), create_agent(settings)
    assert first.id == second.id == 'source-agent'
    assert first.instructions == ['source instruction']
    assert first.tools and first.tools[0].__name__ == 'lookup_document'
    assert first is not original and first is not second
    assert first.model is not original.model and first.model is not second.model
    assert first.db is None and original.db is not None
    assert first.add_history_to_context is False and original.add_history_to_context is True
    first.instructions.append('request-only')
    assert second.instructions == original.instructions == ['source instruction']


def test_default_server_configuration_path_points_to_agent_directory():
    from backend.config import ROOT
    settings = Settings(_env_file=None, jwt_secret='x' * 32)
    assert settings.llm_server_config_path == ROOT / 'agent' / 'server.py'


def test_team_source_resolves_constants_and_isolates_members(tmp_path, monkeypatch):
    from agno.team import Team
    module = ModuleType('agent.server')
    member = Agent(model=DeepSeek(id='member', api_key='test'), instructions=['member'])
    module.cx_agent = member
    module.pd_team = Team(model=DeepSeek(id='leader', api_key='test'), members=[member],
                          db=SqliteDb(db_file=str(tmp_path / 'team.db')), add_history_to_context=True)
    monkeypatch.setitem(sys.modules, 'agent.server', module)
    source = tmp_path / 'server.py'
    source.write_text('KEY="test"\ncx_agent=Agent(model=DeepSeek(id="member",api_key=KEY))\n'
                      'pd_team=Team(model=DeepSeek(id="leader",api_key=KEY,use_thinking=False))', encoding='utf-8')
    settings = Settings(_env_file=None, jwt_secret='x' * 32, llm_config_source='server', llm_server_config_path=source)
    assert settings.llm_model == 'leader'
    first, second = create_agent(settings), create_agent(settings)
    assert isinstance(first, Team) and first.db is None and first.add_history_to_context is False
    assert first.model is not module.pd_team.model
    assert first.members[0] is not member and first.members[0] is not second.members[0]
    assert first.members[0].model is not second.members[0].model
    first.members[0].instructions.append('request')
    assert member.instructions == second.members[0].instructions == ['member']
