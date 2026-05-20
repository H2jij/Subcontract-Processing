"""
示例：从数据库读取字段并填充 DOCX，然后发送邮件

适用于复用到其他系统时，数据来源替换为你自己的查询逻辑即可。
"""
import sys
sys.path.insert(0, "../..")

from contract_toolkit import EmailSender, DocxFiller

# ────────────────────────────────────────────────────────────────────
# Step 1: 从你的系统读取数据（替换为你自己的查询逻辑）
# ────────────────────────────────────────────────────────────────────

def get_contract_data(contract_id: int) -> dict:
    """
    模拟从数据库或 API 读取合同相关数据。

    在你的系统中，将此函数替换为实际的数据库查询。
    返回值格式：{字段名: 字段值}
    """
    # 示例数据（替换为你的数据库查询）
    return {
        "company_name":   "上海ABC贸易有限公司",
        "company_address":"上海市浦东新区XX路1号",
        "contact_person": "李经理",
        "contact_phone":  "021-12345678",
        "credit_code":    "91310000XXXXXXXXXX",
        "contract_no":    f"CONT-2026-{contract_id:04d}",
        "start_year":     "2026", "start_month": "01", "start_day": "01",
        "end_year":       "2026", "end_month":   "12", "end_day":   "31",
    }


# ────────────────────────────────────────────────────────────────────
# Step 2: 定义占位符与数据字段的映射关系
# ────────────────────────────────────────────────────────────────────

# {DOCX模板占位符名称: 数据字典的键名}
FIELD_MAPPING = {
    "乙方名称":         "company_name",
    "乙方地址":         "company_address",
    "乙方法定代表人":   "contact_person",
    "乙方联系电话":     "contact_phone",
    "统一社会信用代码": "credit_code",
    "合同期限_起_年":   "start_year",
    "合同期限_起_月":   "start_month",
    "合同期限_起_日":   "start_day",
    "合同期限_止_年":   "end_year",
    "合同期限_止_月":   "end_month",
    "合同期限_止_日":   "end_day",
}

# 固定值（甲方信息，不需要从数据库读取）
FIXED_VALUES = {
    "甲方法定代表人": "张总",
    "甲方联系方式":   "0532-88888888",
    "甲方信用代码":   "91370200XXXXXXXX00",
    "包装指导书编号": "PKG-2026-STEEL-001",
    "签订日期_年":    "2026",
    "签订日期_月":    "01",
    "签订日期_日":    "15",
}


# ────────────────────────────────────────────────────────────────────
# Step 3: 填充 DOCX
# ────────────────────────────────────────────────────────────────────

CONTRACT_ID = 1001

# 读取数据
data = get_contract_data(CONTRACT_ID)

# 用工具方法从数据字典提取占位符值
auto_values = DocxFiller.build_values_from_dict(data, FIELD_MAPPING)

# 合并固定值
all_values = {**FIXED_VALUES, **auto_values}

# 加载模板并填充（路径改为你的模板文件）
filler = DocxFiller("../../流程图文件/律师修订框架合同/律师修订版_年度采购框架合同（钢料).docx")
print(f"模板占位符 ({len(filler.placeholders)} 个): {filler.placeholders}")

filled_bytes = filler.fill(all_values)
print(f"DOCX 填充完成，覆盖字段: {len(all_values)} 个，大小: {len(filled_bytes)//1024} KB")


# ────────────────────────────────────────────────────────────────────
# Step 4: 发邮件（替换收件人和 SMTP 配置）
# ────────────────────────────────────────────────────────────────────

sender = EmailSender(
    host="smtp.163.com",
    port=465,
    user="QingdaoYanchuang@163.com",
    password="UEiQVKSeGWEYV4Y6",
    sender_name="青岛瑞利杰金属有限公司",
    debug=True,   # True=仅打印，False=真实发送
)

html = sender.wrap_html(
    title=f"年度采购框架合同确认 — {data['contract_no']}",
    body=f"""
    <p>尊敬的 <strong>{data['company_name']}</strong>，您好：</p>
    <p>请查阅附件中的年度采购框架合同并确认。</p>
    <table class="info">
      <tr><td>合同号</td><td><strong>{data['contract_no']}</strong></td></tr>
      <tr><td>乙方</td><td>{data['company_name']}</td></tr>
    </table>
    """,
)

result = sender.send(
    to="partner@example.com",          # 替换为实际收件人
    subject=f"【请确认】年度采购框架合同 — {data['contract_no']}",
    html=html,
    attachment_bytes=filled_bytes,
    attachment_name=f"合同_{data['contract_no']}.docx",
)

print(f"发送结果: {result}")
