# 文件作用：提供通过真实接口注册并登录测试账号的辅助函数。
# 关联关系：供 tests/backend 等接口测试复用，不依赖其他测试模块。


def account(client, name='alice'):
    response = client.post('/api/users', json={'username': name, 'password': 'password123'})
    assert response.status_code == 201, response.text
    response = client.post('/api/login', json={'username': name, 'password': 'password123'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}
