# AI智能审图系统 v7.0 - 交付包

## 一、系统简介

AI智能审图系统 v7.0 是一个基于大语言模型（LLM）和计算机视觉技术的建筑图纸合规性审查平台。

**核心能力**：
- 自动识别建筑、结构、暖通、给排水、电气、消防、幕墙、装饰、景观、基坑 10 个专业图纸
- 185 条检查点规则自动审查
- 11 个专业 Agent 并行协作审查
- 严重度分级（A/B/C/D）与多维度报告

**v7.0 改进**：
- 配置集中化管理（`v7/constants.py`）
- 前后端数据联动（API 配置与 Agent 配置同步）
- 字体颜色可读性优化
- 专业计数动态加载

---

## 二、目录结构

```
AI-CAD-Audit-System-v7.0/
├── src/v7/              # 源代码（Python）
│   ├── admin/           # 管理后台（6个页面）
│   ├── agents/          # 11个专业审查Agent
│   ├── checkpoints/     # 185条审查规则引擎
│   ├── config/          # 配置文件
│   ├── db/              # 数据库
│   └── input/           # 图纸输入目录（放入DXF文件）
├── src/output_v7.0/     # 审查报告输出目录
├── Start.bat            # 【推荐】一键启动（自动检测环境+启动服务+打开浏览器）
├── launch.bat           # 精简启动（假设环境已就绪）
├── requirements.txt     # Python依赖清单
├── .env.template        # 配置模板（API密钥/端口/项目名）
└── README.md            # 本文件
```

---

## 三、快速开始（3步启动）

### 第1步：环境准备

- **Python 3.10+**（必需）
  - 下载：https://www.python.org/downloads/
  - 安装时勾选 **"Add Python to PATH"**

### 第2步：配置API密钥

**方式一（推荐）：Web界面配置**
1. 启动系统后访问 http://localhost:2708
2. 点击"API配置"页面
3. 选择模型厂商，粘贴API Key，点击保存

**方式二：手动编辑.env文件**
1. 复制 `.env.template` 为 `.env`
2. 编辑 `.env`，填入至少一个LLM提供商的API Key：

```env
# 智谱AI（推荐，默认）
ZHIPU_API_KEY=your_key_here

# 或 DeepSeek
DEEPSEEK_API_KEY=your_key_here

# 或 OpenAI
OPENAI_API_KEY=your_key_here

# 或 豆包
DOUBAO_API_KEY=your_key_here
```

### 第3步：启动系统

**双击 `Start.bat`**（Windows）

首次运行会自动：
- 检测 Python 环境
- 创建虚拟环境 `.venv`
- 安装项目依赖（5-10分钟）
- 初始化数据库
- 启动服务并自动打开浏览器

访问地址：`http://localhost:2708`

---

## 四、使用流程

### 4.1 上传图纸

1. 将 DXF 图纸文件放入 `input/` 目录
2. 或打开 **图纸管理** 页面上传

### 4.2 启动审查

1. 选择审查模式（完整审查/快速审查/自由审查）
2. 选择要审查的图纸
3. 点击"开始审查"

### 4.3 查看结果

1. **审查结果** 页面查看所有问题
2. 按严重度/专业/状态筛选
3. 导出 Word/PDF/Excel 报告

---

## 五、管理后台页面

| 页面 | 功能 |
|------|------|
| 图纸管理 | 上传/查看/分类图纸 |
| 规则与专业维护 | 185条检查点规则的增删改查 |
| Agent 配置 | 11个Agent的启用/模型/Prompt配置 |
| API 密钥配置 | LLM提供商API密钥管理 |
| 审查结果 | 审查问题查看与状态更新 |
| 系统维护 | 缓存清理、日志查看、版本管理 |

---

## 六、常见问题

**Q: 启动报"Python not found"**
A: 安装 Python 3.10+，勾选 "Add Python to PATH"

**Q: 依赖安装慢/失败**
A: 脚本默认使用清华镜像，如仍失败请检查网络

**Q: 端口被占用**
A: 编辑 `.env` 修改 `V7_ADMIN_PORT`，或关闭占用2708端口的程序

**Q: 中文乱码**
A: 已自动设置 `PYTHONUTF8=1`

---

## 七、技术支持

- **文档**: `docs/使用手册.md`
- **配置**: `src/v7/constants.py`（统一配置中心）
- **规则**: 管理后台"规则与专业维护"页面

---

**版本**: v7.0  
**日期**: 2026-06-17  
**许可证**: MIT
