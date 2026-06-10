"""5个管线环节的Prompt模板

每个模板对应一个LLM增强接入点：
1. Step1: 标高/轴线语义提取
2. Step2: 合规审查结论二次判断
3. Step3: 碰撞风险语义分析
4. Step4: 跨专业一致性分析
5. Step5: 专业报告生成
"""

SYSTEM_BASE = (
    "你是一位拥有20年经验的中国建筑行业审图专家，精通GB50016/GB50010/"
    "GB50015/GB50057/GB50054/GB50736等全部建筑设计规范。"
    "你的回答必须严谨、准确、可直接用于施工图审查报告。"
)


def prompt_step1_elevation(text: str, known_elevations: str) -> str:
    return (
        "请从以下施工图文本中提取所有标高值。\n\n"
        "【文本内容】\n" + text[:3000] + "\n\n"
        "【已知标高参考】\n" + known_elevations + "\n\n"
        "【提取规则】\n"
        "1. 标高值通常以m为单位，范围-20m~200m\n"
        "2. 排除管径(如DN100)、面积(如4.36m²)、比例(如1:100)等非标高数值\n"
        "3. 区分绝对标高(相对海平面)和相对标高(相对±0.000)\n"
        "4. 标注标高类型：结构标高/建筑标高/管中标高/窗顶标高等\n\n"
        "【输出格式】JSON数组，每条记录必须包含完整证据链\n"
        '[{"value": 3.257, "type": "绝对标高",\n'
        '  "evidence_chain": {\n'
        '    "source_file": "来源文件名",\n'
        '    "source_text": "原文片段（如±0.000=3.257m）",\n'
        '    "line_hint": "所在区域描述（如一层平面图左下角）",\n'
        '    "extract_method": "提取方法（正则匹配/语义识别）"\n'
        '  }}]\n'
        "如果没有标高信息，返回空数组 []"
    )


def prompt_step1_axis(text: str) -> str:
    return (
        "请从以下施工图文本中提取所有轴线编号。\n\n"
        "【文本内容】\n" + text[:3000] + "\n\n"
        "【提取规则】\n"
        "1. 轴线格式：数字轴(1,2,3.../①,②,③...)、字母轴(A,B,C.../a,b,c...)\n"
        "2. 排除以下非轴线内容：轴流风机、轴测图、轴向力、转轴、轴承\n"
        "3. 轴线通常出现在'XX轴'、'轴线A'、'①轴'等上下文中\n\n"
        "【输出格式】JSON数组\n"
        '["A", "B", "C", "1", "2", "3"]\n'
        "如果没有轴线信息，返回空数组 []"
    )


def prompt_step2_compliance(rule_name: str, rule_description: str,
                            code_ref: str, text: str, keyword: str) -> str:
    return (
        "你是一位资深施工图审查专家。请根据规范要求，对图纸文本进行专业审查。\n\n"
        "【规范要求】\n"
        "- 规则名称：" + rule_name + "\n"
        "- 规则描述：" + rule_description + "\n"
        "- 规范依据：" + code_ref + "\n\n"
        "【图纸文本】\n" + text[:2000] + "\n\n"
        "【匹配关键词】" + keyword + "\n\n"
        "【审查要求】\n"
        "1. 仔细分析文本中是否有明确的数值、参数或描述\n"
        "2. 将文本中的数值与规范限值进行精确比对\n"
        "3. 如果文本信息不足以做出判断，标记为'待核实'\n"
        "4. 必须给出完整的证据链，包含：图纸编号、具体位置、数值来源\n\n"
        "【输出格式】JSON\n"
        '{"verdict": "合规|不合规|待核实",\n'
        ' "confidence": "high|medium|low",\n'
        ' "reason": "判断理由（100字以内，必须包含具体数值比对）",\n'
        ' "evidence_chain": {\n'
        '   "drawing_ref": "图纸编号（如A-101, S-201等）",\n'
        '   "location": "具体位置（如轴③-④交轴C处）",\n'
        '   "measured_value": "图纸标注的实际数值",\n'
        '   "code_value": "规范要求的限值",\n'
        '   "comparison": "数值比对结论（如1.2m ≥ 1.1m，满足要求）"\n'
        ' },\n'
        ' "evidence": "关键文本原文片段"}'
    )


def prompt_step3_collision(text_a: str, text_b: str, file_a: str, file_b: str) -> str:
    return (
        "请分析以下两份施工图文本中是否存在管线碰撞或空间冲突风险。\n\n"
        "【图纸A: " + file_a + "】\n" + text_a[:1500] + "\n\n"
        "【图纸B: " + file_b + "】\n" + text_b[:1500] + "\n\n"
        "【分析要求】\n"
        "1. 识别两份图纸中提到的管线(水管/风管/电缆桥架/燃气管等)\n"
        "2. 判断这些管线是否可能在同一空间位置交叉或重叠\n"
        "3. 特别关注标高相近(差值<0.3m)的管线\n"
        "4. 注意管线尺寸(DN/宽度×高度)和走向\n\n"
        "【输出格式】JSON，每条冲突必须包含完整证据链\n"
        '{"has_risk": true|false,\n'
        ' "risk_level": "high|medium|low|none",\n'
        ' "conflicts": [\n'
        '   {"pipe_a": "管线A描述",\n'
        '    "pipe_b": "管线B描述",\n'
        '    "reason": "冲突原因",\n'
        '    "evidence_chain": {\n'
        '      "file_a": "来源文件A",\n'
        '      "file_b": "来源文件B",\n'
        '      "text_a_excerpt": "文件A关键文本",\n'
        '      "text_b_excerpt": "文件B关键文本",\n'
        '      "spatial_overlap": "空间重叠描述（如标高3.2m处交叉）"\n'
        '    }}],\n'
        ' "summary": "50字以内的风险概述"}'
    )


def prompt_step4_cross_discipline(findings: str) -> str:
    return (
        "请分析以下跨专业审查发现，判断是否为真正的设计问题。\n\n"
        "【跨专业审查发现】\n" + findings[:3000] + "\n\n"
        "【分析要求】\n"
        "1. 判断每个发现是真正的设计冲突还是正常的跨专业配合\n"
        "2. 评估问题的严重程度（是否影响施工/安全/功能）\n"
        "3. 给出具体的整改建议\n\n"
        "【输出格式】JSON数组，每条发现必须包含完整证据链\n"
        '[{"finding": "原始发现",\n'
        '  "is_real_issue": true|false,\n'
        '  "severity": "critical|major|minor|false_alarm",\n'
        '  "analysis": "专业分析（100字以内）",\n'
        '  "recommendation": "整改建议",\n'
        '  "evidence_chain": {\n'
        '    "source_disciplines": ["涉及专业列表"],\n'
        '    "conflict_files": ["冲突文件列表"],\n'
        '    "conflict_description": "冲突具体描述",\n'
        '    "normative_reference": "相关规范条款（如有）"\n'
        '  }}]'
    )


def prompt_step5_report(issues: str, project_info: str) -> str:
    return (
        "请将以下审查问题整理为专业的施工图审查报告摘要。\n\n"
        "【项目信息】\n" + project_info + "\n\n"
        "【审查问题清单】\n" + issues[:4000] + "\n\n"
        "【输出要求】\n"
        "1. 按严重程度分级汇总（严重/重要/一般/提示）\n"
        "2. 每个问题包含：问题描述、规范依据、整改建议、证据链\n"
        "3. 证据链必须包含：来源文件、原文片段、数值比对、定位信息\n"
        "4. 最后给出总体评价和建议\n"
        "5. 语言风格：专业、严谨、简洁，符合施工图审查报告规范\n\n"
        "【报告格式】Markdown，每个问题使用以下结构：\n"
        "### [严重程度] 问题标题\n"
        "- **问题描述**：xxx\n"
        "- **规范依据**：xxx\n"
        "- **整改建议**：xxx\n"
        "- **证据链**：\n"
        "  - 来源文件：xxx\n"
        "  - 原文片段：xxx\n"
        "  - 数值比对：xxx\n"
        "  - 定位信息：xxx\n"
    )


def prompt_smart_verify(text: str, rule_desc: str, initial_verdict: str) -> str:
    return (
        "以下是一条施工图审查的初步结论，请用你的专业知识进行复核。\n\n"
        "【初步结论】" + initial_verdict + "\n"
        "【审查规则】" + rule_desc + "\n"
        "【图纸文本】\n" + text[:2000] + "\n\n"
        "请判断初步结论是否正确，并给出你的专业意见。\n"
        "【输出格式】JSON\n"
        '{"agree": true|false,\n'
        ' "final_verdict": "合规|不合规|待核实",\n'
        ' "confidence": "high|medium|low",\n'
        ' "reason": "专业判断理由"}'
    )


def prompt_rule_llm_check(rule_name: str, rule_desc: str, code_ref: str,
                          keywords: str, discipline: str, drawing_texts: str) -> str:
    """Step2 LLM独立审查：替代纯正则关键词匹配的语义化合规判断"""
    prompt = (
        "你是一位资深施工图审查专家。\n\n"
        "请基于以下规则，对施工图纸文本进行独立的合规性审查。\n"
        "注意：你必须基于图纸文本中的实际内容做出专业判断，而非仅做关键词匹配。\n\n"
        "【审查规则】\n"
        "- 规则名称：" + rule_name + "\n"
        "- 规则说明：" + rule_desc + "\n"
        "- 规范依据：" + code_ref + "\n"
        "- 所属专业：" + discipline + "\n"
        "- 触发关键词：" + keywords + "\n\n"
        "【图纸文本内容】\n" + drawing_texts[:4000] + "\n\n"
        "【审查方法论】\n"
        "1. 不要仅依赖关键词匹配——理解文本语义，判断上下文含义\n"
        "2. 若文本中出现数值，将其与规范限值做精确比对\n"
        '3. 区分\u201c设计说明\u201d（意图性描述）和\u201c施工标注\u201d（实测数据）\n'
        '4. 注意排除误导性关键词（如\u201c详见另图\u201d表示此处未详细标注）\n'
        '5. 若文本信息不足以做出明确判断，标记为\u201c待核实\u201d并说明缺什么信息\n\n'
        "【输出格式】严格JSON\n"
        '{"verdict": "合规|不合规|待核实",\n'
        ' "confidence": "high|medium|low",\n'
        ' "reason": "判断理由",\n'
        ' "evidence": "关键文本原文片段",\n'
        ' "evidence_chain": {\n'
        '   "drawing_ref": "来源图纸标识",\n'
        '   "location_hint": "文本在图纸中的位置特征",\n'
        '   "measured_value": "图纸中标注的实际数值（若无则填null）",\n'
        '   "code_value": "规范要求的限值（若无则填null）",\n'
        '   "semantic_judgment": "语义层面判断"\n'
        ' }}'
    )
    return prompt


def prompt_severity_assessment(issue_category: str, issue_description: str,
                               building_type: str, area_info: str,
                               context_text: str) -> str:
    """严重度LLM评估：替代硬编码_SEVERITY_RULES的综合上下文判断"""
    prompt = (
        "你是一位资深施工图审查专家，请对以下审查发现的问题进行严重度分级评估。\n\n"
        "【问题信息】\n"
        "- 问题类别：" + issue_category + "\n"
        "- 问题描述：" + issue_description + "\n"
        "- 建筑类型：" + building_type + "\n"
        "- 所在区域：" + area_info + "\n"
        "- 上下文文本：\n" + context_text[:1500] + "\n\n"
        "【严重度分级标准】\n"
        "- A级（严重）：强条违规、结构安全隐患、消防系统失效，必须立即整改\n"
        "- B级（重要）：非强条违规、净高不足、管线碰撞、跨专业不一致，影响使用功能\n"
        "- C级（一般）：标注不完整、间距偏小、优化建议，不影响安全但影响品质\n"
        "- D级（提示）：信息提示、参考建议，人工复核即可\n\n"
        "【评估要求】\n"
        "1. 综合考虑问题类别、建筑类型、所在区域的风险程度\n"
        '2. 例如同一类\u201c净距不足\u201d问题，在消防通道为A级，在普通走廊为C级\n'
        "3. 教学建筑/医院/商场等人员密集场所，同等问题严重度应上调一档\n"
        "4. 给出明确的严重度判断理由\n\n"
        "【输出格式】JSON\n"
        '{"severity": "A|B|C|D",\n'
        ' "confidence": "high|medium|low",\n'
        ' "reason": "分级理由（100字以内）",\n'
        ' "risk_factors": ["影响安全", "影响功能", "仅影响观感"]}'
    )
    return prompt


def prompt_suggestion_generate(issue_category: str, issue_description: str,
                               severity: str, collision_info: str,
                               building_type: str) -> str:
    """整改建议LLM生成：替代硬编码_SOLUTION_KB模板的智能建议"""
    prompt = (
        "你是一位资深施工图审查专家，请针对以下审查问题给出具体可操作的整改建议。\n\n"
        "【问题信息】\n"
        "- 问题类别：" + issue_category + "\n"
        "- 问题描述：" + issue_description + "\n"
        "- 严重度：" + severity + "\n"
        "- 碰撞/冲突详情：" + collision_info + "\n"
        "- 建筑类型：" + building_type + "\n\n"
        "【建议撰写要求】\n"
        "1. 建议必须具体可操作，包含调整方向和量化参考值\n"
        "2. 优先级从高到低列出，主方案+备选方案\n"
        "3. 需考虑施工可行性：安装顺序、操作空间、经济合理性\n"
        "4. 遵守机电安装优先级：风管→桥架→喷淋→水管→电气管线\n"
        '5. 涉及结构修改时，必须标注\u201c需设计院确认\u201d\n\n'
        "【输出格式】JSON\n"
        '{"primary_solution": "首选整改方案（80字以内）",\n'
        ' "alternatives": ["备选方案1", "备选方案2"],\n'
        ' "calculation_hint": "调整量计算方法（如调整量=重叠高度+50mm安全余量）",\n'
        ' "constraints": ["施工约束条件1", "约束条件2"],\n'
        ' "requires_designer_approval": true|false,\n'
        ' "estimated_impact": "对相关专业的影响说明"}'
    )
    return prompt


def prompt_cross_discipline_analysis(findings: str, discipline_a: str,
                                     discipline_b: str) -> str:
    """跨专业一致性LLM分析：替代纯比对逻辑的语义化判断"""
    prompt = (
        "你是一位资深施工图审查专家，请分析以下跨专业审查发现，判断是否为真正的设计问题。\n\n"
        "【涉及专业】" + discipline_a + " vs " + discipline_b + "\n\n"
        "【跨专业审查发现】\n" + findings[:4000] + "\n\n"
        "【分析要求】\n"
        '1. 区分\u201c真正的设计矛盾\u201d和\u201c正常的专业配合差异\u201d\n'
        "   例：建筑图标注门洞高2.1m、结构图梁底高2.3m → 正常配合\n"
        "   例：建筑图排水沟位置与结构图基础重合 → 设计矛盾\n"
        "2. 评估问题严重程度和实际影响\n"
        "3. 判断是否需要专业间协调（会签/变更通知单）\n"
        "4. 给出具体的协调建议和参考规范\n"
        "5. 如果发现是标注习惯差异而非实质矛盾，明确指出\n\n"
        "【输出格式】JSON数组\n"
        '[{"finding": "原始发现描述",\n'
        '  "is_real_issue": true|false,\n'
        '  "severity": "critical|major|minor|false_alarm",\n'
        '  "analysis": "专业分析（150字以内）",\n'
        '  "coordination_advice": "专业协调建议",\n'
        '  "evidence_chain": {\n'
        '    "source_a": "专业A来源",\n'
        '    "source_b": "专业B来源",\n'
        '    "conflict_nature": "冲突性质（实质矛盾/标注差异/正常配合）",\n'
        '    "resolution": "解决方式（会签/变更/忽略）"\n'
        '  }}]'
    )
    return prompt


def prompt_compliance_enhanced(rule_name: str, rule_desc: str, standard: str,
                               clause: str, check_type: str, issues_context: str,
                               building_type: str) -> str:
    """合规检查LLM增强：对数值边界情况的语义判断（compliance_rule_engine补充）"""
    prompt = (
        "你是一位资深施工图审查专家。以下合规检查的数值处于边界值范围，请做语义层面的专业判断。\n\n"
        "【规范依据】\n"
        "- 规范：" + standard + "\n"
        "- 条款：" + clause + "\n"
        "- 规则：" + rule_name + "\n"
        "- 描述：" + rule_desc + "\n"
        "- 检查类型：" + check_type + "\n"
        "- 建筑类型：" + building_type + "\n\n"
        "【边界问题详情】\n" + issues_context[:3000] + "\n\n"
        "【判断要求】\n"
        "1. 判断该偏差是否在工程允许误差范围内（通常±5%可接受）\n"
        "2. 考虑该位置是否为关键区域（消防通道/疏散走道/设备机房等从严判断）\n"
        "3. 考虑建筑类型对要求的差异（教学建筑/医院要求高于普通厂房）\n\n"
        "【输出格式】JSON\n"
        '{"verdict": "可接受|需整改|需人工复核",\n'
        ' "tolerance_percent": "偏差百分比",\n'
        ' "is_critical_area": true|false,\n'
        ' "reason": "判断理由（100字以内）",\n'
        ' "recommendation": "处置建议（50字以内）"}'
    )
    return prompt
