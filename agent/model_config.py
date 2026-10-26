# 文件作用：使用 AST 静态解析智能体源文件中的模型参数和顶层常量。
# 关联关系：由 backend/config.py 在 server 模式下调用，仅解析声明，不执行智能体源代码。
"""静态读取 agent/server.py 模型元信息；实际 Agent 由调用适配器加载。"""
import ast
from pathlib import Path


def read_server_model_config(path: Path) -> dict:
    try:
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    except (OSError, SyntaxError):
        raise ValueError('无法读取指定 server.py 的模型配置') from None
    assignments = {target.id: node.value for node in tree.body if isinstance(node, ast.Assign)
                   for target in node.targets if isinstance(target, ast.Name)}
    # 团队及成员可以各自声明模型；以网站实际调用的导出对象为准。
    root = next((assignments[name] for name in ('pd_team', 'deepseek_agent', 'cx_agent')
                 if name in assignments), None)
    model = next((keyword.value for keyword in root.keywords if keyword.arg == 'model'), None) \
        if isinstance(root, ast.Call) else None
    if isinstance(model, ast.Name):
        model = assignments.get(model.id)
    calls = [node for node in ast.walk(model if model is not None else tree) if isinstance(node, ast.Call)
             and ((isinstance(node.func, ast.Name) and node.func.id == 'DeepSeek')
                  or (isinstance(node.func, ast.Attribute) and node.func.attr == 'DeepSeek'))]
    if len(calls) != 1:
        raise ValueError('server.py 需要恰好一处明确的 DeepSeek 模型声明')
    values = {}
    for keyword in calls[0].keywords:
        if keyword.arg in {'api_key', 'id', 'base_url', 'use_thinking'}:
            try:
                value = keyword.value
                if isinstance(value, ast.Name):
                    value = assignments.get(value.id, value)
                values[keyword.arg] = ast.literal_eval(value)
            except (ValueError, TypeError, SyntaxError):
                raise ValueError('server.py 的模型配置须使用字符串或布尔字面量') from None
    for name in ['api_key', 'id', 'base_url']:
        if name in values and (not isinstance(values[name], str) or not values[name].strip()):
            raise ValueError('server.py 的模型配置字符串不能为空')
    if not values.get('api_key') or '你的_' in values['api_key']:
        raise ValueError('请在 agent/server.py 的 DeepSeek 声明中配置 api_key 字符串')
    thinking = values.get('use_thinking')
    if thinking is not None and not isinstance(thinking, bool):
        raise ValueError('server.py 的 use_thinking 必须为 True、False 或 None')
    return {'llm_api_key': values['api_key'], 'llm_provider': 'deepseek',
            'llm_model': values.get('id', 'deepseek-v4-flash'),
            'llm_base_url': values.get('base_url', 'https://api.deepseek.com'),
            'llm_use_thinking': thinking}
