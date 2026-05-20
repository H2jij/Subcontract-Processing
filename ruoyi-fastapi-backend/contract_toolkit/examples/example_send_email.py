"""
示例：发送邮件（带 DOCX 附件）
"""
import sys
sys.path.insert(0, "../..")  # 指向 contract_toolkit 的父目录

from contract_toolkit import EmailSender, DocxFiller

# ── 1. 配置发件邮箱 ─────────────────────────────────────────────
sender = EmailSender(
    host="smtp.163.com",
    port=465,
    user="your_email@163.com",
    password="your_auth_code",       # 163授权码，不是登录密码
    sender_name="青岛瑞利杰金属有限公司",
    debug=False,                      # 改为 True 可只打印日志不真实发送
)

# ── 2. 填充 DOCX 模板 ───────────────────────────────────────────
filler = DocxFiller("../../流程图文件/律师修订框架合同/律师修订版_年度采购框架合同（钢料).docx")

print(f"模板占位符：{filler.placeholders}")
print(f"是否自动转换（下划线→占位符）：{filler.is_converted}")

filled_bytes = filler.fill({
    "乙方名称":         "上海测试钢料贸易有限公司",
    "乙方地址":         "上海市浦东新区测试路1号",
    "乙方法定代表人":   "李总",
    "乙方联系电话":     "021-12345678",
    "统一社会信用代码": "91310000TEST000001",
    "甲方法定代表人":   "张总",
    "甲方联系方式":     "0532-88888888",
    "甲方信用代码":     "91370200XXXXXXXX00",
    "合同期限_起_年":   "2026",
    "合同期限_起_月":   "01",
    "合同期限_起_日":   "01",
    "合同期限_止_年":   "2026",
    "合同期限_止_月":   "12",
    "合同期限_止_日":   "31",
    "包装指导书编号":   "PKG-2026-STEEL-001",
    "签订日期_年":      "2026",
    "签订日期_月":      "01",
    "签订日期_日":      "15",
})

print(f"DOCX 填充完成，大小：{len(filled_bytes)//1024} KB")

# ── 3. 发送邮件（带 DOCX 附件）──────────────────────────────────
html = sender.wrap_html(
    title="年度采购框架合同（钢料）确认通知",
    body="""
    <p>尊敬的合作方，您好：</p>
    <p>请查阅附件中的年度采购框架合同，并在 <strong>72 小时</strong> 内回复确认意见。</p>
    <table class="info">
      <tr><td>合同号</td><td><strong>CONT-2026-TEST-V1</strong></td></tr>
      <tr><td>合同类型</td><td>年度采购框架合同（材料供应·钢料）</td></tr>
      <tr><td>乙方</td><td>上海测试钢料贸易有限公司</td></tr>
      <tr><td>合同期限</td><td>2026-01-01 至 2026-12-31</td></tr>
    </table>
    """,
)

result = sender.send(
    to="recipient@example.com",
    subject="【请确认】年度采购框架合同（钢料）— CONT-2026-TEST-V1",
    html=html,
    attachment_bytes=filled_bytes,
    attachment_name="年度采购框架合同（钢料）CONT-2026-TEST-V1.docx",
)

print(f"发送结果：{result}")
