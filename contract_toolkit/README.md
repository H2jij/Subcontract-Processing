# contract_toolkit — 合同邮件分发 & DOCX 自动填充工具包

独立可复用模块，**无数据库依赖**，可直接移植到任何 Python 项目。

---

## 包含模块

| 文件 | 功能 |
|------|------|
| `email_sender.py` | SMTP 邮件发送（支持附件、HTML 模板、SSL/STARTTLS） |
| `docx_filler.py` | DOCX 模板自动填充（支持 {{占位符}} 和下划线填空两种格式） |
| `pdf_converter.py` | DOCX → PDF 转换（LibreOffice 优先，降级 docx2pdf） |

---

## 安装依赖

```bash
pip install python-docx python-dotenv
# PDF 转换（可选）
winget install TheDocumentFoundation.LibreOffice  # Windows
# 或
sudo apt install libreoffice  # Ubuntu/Debian
```

---

## 快速使用

### 发送邮件

```python
from contract_toolkit import EmailSender

sender = EmailSender(
    host="smtp.163.com",
    port=465,
    user="your@163.com",
    password="your_auth_code",
    sender_name="公司名称",
)

result = sender.send(
    to="partner@example.com",
    subject="【合同确认】",
    html=sender.wrap_html("标题", "<p>正文内容</p>"),
    attachment_bytes=docx_bytes,         # 字节流附件
    attachment_name="合同.docx",
)
print(result)  # {"success": True, "smtp_message_id": "...", "error": None}
```

### 从 .env 文件读取配置

```python
sender = EmailSender.from_env(".env")  # 读取 SMTP_HOST/PORT/USER/PASSWORD
```

`.env` 文件格式：
```
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=your@163.com
SMTP_PASSWORD=your_auth_code
EMAIL_DEBUG=false
```

---

### 填充 DOCX 模板

```python
from contract_toolkit import DocxFiller

filler = DocxFiller("template.docx")

# 查看占位符
print(filler.placeholders)       # ['乙方名称', '乙方地址', ...]
print(filler.is_converted)       # True = 从下划线格式自动转换

# 填充
filled_bytes = filler.fill({
    "乙方名称": "ABC公司",
    "乙方地址": "上海市XX路1号",
    "合同期限_起_年": "2026",
    ...
})

# 保存到文件
filler.fill_to_file(values, "output/contract.docx")
```

#### 从数据字典批量提取字段值

```python
# 数据库查询结果
db_row = {"company_name": "ABC公司", "address": "上海市..."}

# 定义映射：{DOCX占位符: 数据字典键名}
mapping = {"乙方名称": "company_name", "乙方地址": "address"}

values = DocxFiller.build_values_from_dict(db_row, mapping)
# → {"乙方名称": "ABC公司", "乙方地址": "上海市..."}
```

---

### 转换 PDF

```python
from contract_toolkit import PdfConverter

# 检查是否有转换工具
print(PdfConverter.is_available())  # {"libreoffice": True, "docx2pdf": False}

# 从文件转换
pdf_path = PdfConverter.from_file("contract.docx", "output/")

# 从字节流转换
pdf_bytes = PdfConverter.from_bytes(docx_bytes)
```

---

## 模板格式说明

工具包支持两种模板格式，**自动识别，无需手动指定**：

**格式 A — 占位符格式（推荐新建模板时使用）：**
在 Word 文档中直接输入 `{{乙方名称}}`、`{{合同期限}}` 等占位符。

**格式 B — 下划线填空格式（律师修订版框架合同原始格式）：**
文档中用 `____` 下划线表示需要填写的位置，工具会自动按顺序替换为预设占位符，
**原始文件不会被修改**。

---

## 示例文件

- `examples/example_send_email.py` — 填充 DOCX 并发送邮件
- `examples/example_fill_from_db.py` — 从数据库读取字段并填充

---

## 移植到其他系统

1. 复制整个 `contract_toolkit/` 文件夹到目标项目
2. `pip install python-docx`
3. 配置 SMTP（邮箱地址 + 授权码）
4. 调用 `DocxFiller` 和 `EmailSender` 即可

不依赖 FastAPI、SQLAlchemy、psycopg2 等框架，任何 Python 项目均可使用。
