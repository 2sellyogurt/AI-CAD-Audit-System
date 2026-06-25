# 笔记：LLM适配器与图纸预处理分析

## 一、LLM适配器 (v7/llm/base_adapter.py)
```
抽象基类: LLMBaseAdapter

配置类 (LLMConfig):
├── provider: 提供商名称
├── model: 模型名称
├── base_url: API基础地址
├── api_key: API密钥
├── timeout: 超时时间 (默认30s)
├── image_detail: 图片细节级别 (high)
├── max_retries: 最大重试次数 (2)
├── retry_delay: 重试间隔 [2.0, 5.0]
├── temperature: 温度 (0.1)
├── max_tokens: 最大Token (4096)
└── extra_headers: 额外请求头

统计类 (CallStats):
├── total_calls: 总调用次数
├── success_calls: 成功次数
├── failed_calls: 失败次数
├── total_tokens: 总Token数
├── total_cost: 总费用
└── avg_latency_ms: 平均延迟

抽象方法:
├── ask_text(prompt, system, temperature, max_tokens) → str
└── ask_vision(prompt, image_paths, system, temperature, max_tokens) → str

通用方法:
├── ask_json(): 请求JSON格式返回
├── get_stats(): 获取统计信息
└── _update_stats(): 更新调用统计
```

## 二、图纸提取器 (v7/preprocessor/drawing_extractor.py)
```
核心类:
├── TextEntity (文本实体)
│   ├── entity_id, raw_text
│   ├── x, y, z (坐标)
│   ├── layer (图层)
│   └── entity_type, file
└── DrawingInfo (图纸信息)
    ├── file_path, readable_name
    ├── discipline (专业分类)
    ├── content_disciplines (内容涉及专业)
    ├── drawing_type (图纸类型)
    ├── floor (楼层)
    ├── drawing_number (图号)
    ├── text_entities (文本实体列表)
    ├── text_content (合并文本内容)
    ├── png_path, png_paths (导出图片路径)
    └── extraction_ok, extraction_error

专业分类规则 (CLASSIFICATION_RULES):
├── building: 建施, 建筑, 总图, 平面, 立面...
├── structure: 结施, 结构, 基础, 配筋...
├── hvac: 暖施, 暖通, 空调, 通风...
├── plumbing: 水施, 给排水, 给水, 排水...
├── electrical: 电施, 电气, 配电, 照明...
├── fire: 消施, 消防, 防火, 报警...
├── landscape: 绿施, 景观, 绿化, 园林...
├── foundation_pit: 基坑, 支护, 降水...
├── curtain_wall: 幕墙, 玻璃幕墙...
└── decoration: 装饰, 装修, 精装...

提取流程:
1. ezdxf读取DXF文件
2. 提取TEXT/MTEXT实体 (文本+坐标+图层)
3. 按文件名前缀分类专业
4. 建立轴线坐标映射
5. 生成文本路径上下文
```

## 三、调试关键点
| 问题 | 排查方向 |
|------|----------|
| LLM调用失败 | 检查 api_key, base_url, model 配置 |
| 超时错误 | 增加 timeout 或检查网络 |
| Token超限 | 减少 max_tokens 或精简prompt |
| 图纸提取失败 | 检查DXF文件格式、ezdxf版本 |
| 专业分类错误 | 检查文件名是否包含分类关键词 |
| 坐标映射错误 | 检查图层命名是否符合规则 |
| 文本丢失 | 检查TEXT/MTEXT实体是否存在 |

## 四、依赖版本要求
```
ezdxl: 1.4.4 (DXF处理)
openai: 1.x (LLM调用)
flask: 3.x (Web服务)
lxml: 6.x (XML处理)
docx: 最新 (Word报告)
```
