# Technical Architecture

## System Overview

AI CAD Audit System is a multi-agent, pipeline-based architecture for automated construction drawing review. It combines deterministic rule checking with LLM-powered visual analysis to cover both measurable dimensions and qualitative design compliance.

## Core Pipeline

```
Input (DXF/DWG)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Preprocessor                                    │
│  ┌─────────────┐  ┌──────────────┐              │
│  │ DWG→DXF     │─▶│ Drawing      │              │
│  │ Converter   │  │ Extractor    │              │
│  └─────────────┘  └──────┬───────┘              │
│                          │                       │
│  ┌─────────────┐  ┌──────▼───────┐              │
│  │ Frame       │  │ Grid         │              │
│  │ Splitter    │  │ Splitter     │              │
│  └──────┬──────┘  └──────┬───────┘              │
│         │                │                       │
│  ┌──────▼────────────────▼───────┐              │
│  │ Scale Recognition &           │              │
│  │ Image Enhancement             │              │
│  └──────────────┬────────────────┘              │
└─────────────────┼───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  Scanner                                         │
│  Drawing content scanner extracts text,          │
│  dimensions, symbols, and spatial data           │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  Agent Orchestrator (Scheduler)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Building │ │Structure │ │  HVAC    │ ...x12  │
│  │  Agent   │ │  Agent   │ │  Agent   │        │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘        │
│       │             │             │              │
│       └─────────────┼─────────────┘              │
│                     │                            │
│  ┌──────────────────▼──────────────────┐        │
│  │         Chief Agent                  │        │
│  │  (Cross-discipline verification)     │        │
│  └──────────────────┬──────────────────┘        │
└─────────────────────┼───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  Problem Pool (Unified Issue Management)         │
│  ┌────────────┐  ┌──────────────┐               │
│  │ Dedup      │  │ Conflict     │               │
│  │ Engine     │  │ Resolution   │               │
│  └────────────┘  └──────────────┘               │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  Audit & Report                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │ False        │  │ Role-based   │             │
│  │ Negative     │  │ Report       │             │
│  │ Auditor      │  │ Generator    │             │
│  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────┘
```

## Key Components

### 1. Preprocessor (`v7/preprocessor/`)

| Module | Purpose |
|--------|---------|
| `drawing_extractor.py` | Parse DXF entities (text, lines, arcs, dimensions) |
| `dwg_converter.py` | Convert DWG to DXF using ODA File Converter |
| `frame_splitter.py` | Split multi-frame drawings into individual frames |
| `grid_splitter.py` | Split drawings by grid lines |
| `image_enhancer.py` | Enhance image quality for LLM vision input |
| `pil_renderer.py` | Render DXF to high-res PNG images |

### 2. Checkpoint Engine (`v7/checkpoints/`)

The checkpoint engine loads YAML-defined rules and performs deterministic checks:

- **dimension_min/max**: Check if dimensions meet code requirements
- **required_element**: Verify mandatory elements exist (e.g., fire exits)
- **fire_rating**: Validate material fire resistance ratings
- **area_limit**: Check compartment or floor area limits
- **distance_min**: Verify minimum distances (e.g., between buildings)

Each checkpoint has a `route` field:
- `rule`: Deterministic check only (no LLM needed)
- `llm`: Vision-language model check only
- `dual`: Both rule-based and LLM checks

### 3. LLM Adapter Layer (`v7/llm/`)

Abstract interface supporting multiple LLM providers:
- **Text adapter**: For text-only analysis (extracted drawing data)
- **Vision adapter**: For image + text analysis (drawing screenshots)
- **Factory pattern**: `LLMFactory.create(provider, mode)`

Supported providers: ZhipuAI, DeepSeek, OpenAI, Ollama (local), and any OpenAI-compatible API.

### 4. Agent System (`v7/agents/`)

12 discipline-specific agents + 1 chief agent:

| Agent | Discipline | Key Checks |
|-------|-----------|------------|
| BuildingAgent | Architecture | Evacuation, accessibility, room dimensions |
| StructureAgent | Structural | Reinforcement, beam-column joints |
| HvacAgent | HVAC | Duct sizing, smoke exhaust |
| PlumbingAgent | Plumbing | Pipe sizing, drainage |
| ElectricalAgent | Electrical | Cable rating, emergency lighting |
| FireAgent | Fire protection | Compartment area, sprinkler coverage |
| CurtainWallAgent | Curtain wall | Panel thickness, sealant width |
| DecorationAgent | Interior | Material fire rating |
| LandscapeAgent | Landscape | Planting distance, drainage |
| FoundationPitAgent | Foundation pit | Retaining structure |
| FreeReviewAgent | General | Open-ended LLM review |
| ChiefAgent | Cross-check | Inter-discipline conflicts |

### 5. Problem Pool (`v7/problem_pool/`)

Unified issue management with:
- **Deduplication**: Merge similar findings from different agents
- **Conflict tracking**: Track resolution status (open/resolved/waived)
- **Provenance**: Record which agent and data source found each issue

### 6. Report Generator (`v7/report_v7/`)

Generates role-based reports:
- **Chief reviewer report**: Executive summary with cross-discipline findings
- **Discipline reports**: Detailed findings per specialty
- **Cross-check report**: Inter-discipline conflict analysis

Output formats: Markdown (.md), Excel (.xlsx), DOCX (.docx)

## Data Flow

```
DXF File
  → DrawingExtractor.extract() → DrawingData
  → FrameSplitter.split() → List[Frame]
  → DrawingScanner.scan(frame) → ScannedContent
  → CheckpointEngine.check(content) → List[Issue]
  → Agent.review(frame, content) → List[Issue]
  → ProblemPool.add(issues) → DeduplicatedIssueList
  → FalseNegativeAuditor.audit() → AuditedIssueList
  → RoleReportGenerator.generate() → ReportFiles
```

## Configuration

- `v7/config.yaml`: Global settings (LLM provider, image resolution, etc.)
- `v7/checkpoints/definitions/*.yaml`: Checkpoint rules per discipline
- Environment variables: `ZHIPU_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`

## Security

- API keys stored via `cryptography` encrypted config, never hardcoded
- `secure_config.py` handles key encryption/decryption
- All LLM calls use HTTPS
- Input validation on DXF parsing to prevent injection
