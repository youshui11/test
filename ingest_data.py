from server import cx_knowledge

cx_knowledge.insert(
    name="订单-10001",
    text_content="""
    订单号：10001
    客户：张三
    商品：智能耳机
    订单状态：已发货
    物流状态：运输中
    """,
    metadata={
        "order_id": "10001",
        "customer_name": "张三",
        "status": "已发货",
    },
)

cx_knowledge.insert(
    name="售后工单-20001",
    text_content="""
    工单号：20001
    客户：李四
    问题：耳机左耳无声音
    状态：等待客服处理
    """,
    metadata={
        "ticket_id": "20001",
        "customer_name": "李四",
        "status": "待处理",
    },
)