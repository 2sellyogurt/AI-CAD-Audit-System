# Architecture

## System Overview

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│  DXF/DWG    │───▶│ Preprocessor │───▶│   Scanner   │───▶│   Agents     │
│  Input      │    │ (Extract,    │    │ (Drawing    │    │ (12 Discipline│
│             │    │  Split,      │    │  Scanner)   │    │  Reviewers)  │
│             │    │  Scale)      │    │             │    │              │
└─────────────┘    └──────────────┘    └─────────────┘    └──────┬───────┘
                                                                   │
                                                                   ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│  Final      │◀───│   Report     │◀───│   Audit     │◀───│  Problem     │
│  Output     │    │  Generator   │    │  (False     │    │  Pool        │
│  (.md/.xlsx)│    │              │    │   Negative) │    │  (Unified)   │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
```

## Core Components

### Preprocessor (`v7/preprocessor/`)
Handles DXF/DWG file parsing:
- **Drawing Extractor**: Extracts content from DXF files
- **Frame Splitter**: Splits multi-frame drawings into individual frames
- **Grid Splitter**: Divides large drawings into manageable grid sections
- **Scale Recognition**: Automatically detects drawing scale
- **DWG Converter**: Converts DWG files to DXF format
- **Standardization Checker**: Validates drawing standard compliance

### Scanner (`v7/scanner/`)
Analyzes drawing content and extracts features for rule checking.

### Agents (`v7/agents/`)
12 specialized discipline review agents:
- **Base Agent**: Common agent functionality and LLM communication
- **Chief Agent**: Cross-discipline verification and result aggregation
- **Discipline Agents**: Building, Structure, HVAC, Plumbing, Electrical, Fire, Curtain Wall, Decoration, Landscape, Foundation Pit

### Checkpoints (`v7/checkpoints/`)
Rule engine for deterministic compliance checking:
- **Engine**: Executes YAML-defined rules against extracted data
- **Schema**: Validates checkpoint YAML definitions
- **Definitions**: YAML rule files per discipline (100+ checkpoints)

### LLM Layer (`v7/llm/`)
Abstraction for multiple LLM providers:
- **Base Adapter**: Common LLM interface
- **Text Adapter**: Text-only LLM queries
- **Vision Adapter**: Vision + text multimodal analysis

### Problem Pool (`v7/problem_pool/`)
Unified issue management across all discipline reviews.

### Audit (`v7/audit/`)
False-negative auditor to ensure review quality.

### Report (`v7/report_v7/`)
Generates role-based professional review reports in Markdown and Excel formats.

### Admin Dashboard (`v7/admin/`)
Web-based administration interface built with Flask.

### Review UI (`v7/review_ui/`)
Web interface for reviewing and annotating results.

## Data Flow

1. **Input**: DXF/DWG files are parsed and preprocessed
2. **Scanning**: Drawing content is scanned and features are extracted
3. **Rule Checking**: Checkpoint engine performs deterministic checks
4. **LLM Review**: Vision-language model reviews complex visual elements
5. **Cross-Check**: Chief agent verifies inter-discipline consistency
6. **Audit**: False-negative auditor validates findings
7. **Report**: Results formatted into professional review reports

## Dual-Route Strategy

The system uses two complementary review approaches:
- **Rule-Based**: Fast, deterministic checks for measurable criteria (dimensions, counts, ratings)
- **LLM-Based**: Visual understanding for complex checks requiring contextual interpretation
