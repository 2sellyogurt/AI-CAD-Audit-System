# LLM配置指引

本系统支持多种LLM用于语义分析、缺陷推理和报告生成。

## 方案一：Ollama本地部署（推荐，免费）

```bash
# 1. 下载安装Ollama
# https://ollama.com/download

# 2. 下载模型
ollama pull qwen2.5:7b

# 3. 运行审查（自动连接Ollama）
python src/master.py --dxf-dir input --llm-provider ollama --llm-model qwen2.5:7b
```

## 方案二：DeepSeek API（便宜，效果好）

```bash
# 1. 注册 https://platform.deepseek.com
# 2. 获取API Key
# 3. 运行审查
python src/master.py --dxf-dir input --llm-provider deepseek --llm-model deepseek-chat --llm-api-key sk-xxx
```

## 方案三：OpenAI API（最强，最贵）

```bash
python src/master.py --dxf-dir input --llm-provider openai --llm-model gpt-4o --llm-api-key sk-xxx
```

## 无LLM模式

不配置LLM时，系统使用纯规则匹配（91条强制条文），无需任何API。

```bash
python src/master.py --dxf-dir input
```
