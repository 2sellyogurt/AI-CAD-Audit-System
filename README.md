<div align="center">

# AI CAD Audit System

**AI-Powered Construction Drawing Review Platform**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg)](CONTRIBUTING.md)

<br>

[![Architecture](https://img.shields.io/badge/topic-architecture-8A2BE2)](https://github.com/topics/architecture)
[![CAD](https://img.shields.io/badge/topic-cad-FF6B35)](https://github.com/topics/cad)
[![BIM](https://img.shields.io/badge/topic-bim-007EC6)](https://github.com/topics/bim)
[![AI](https://img.shields.io/badge/topic-ai-00BCD4)](https://github.com/topics/ai)
[![LLM](https://img.shields.io/badge/topic-llm-9C27B0)](https://github.com/topics/llm)
[![DXF](https://img.shields.io/badge/topic-dxf-607D8B)](https://github.com/topics/dxf)
[![Engineering](https://img.shields.io/badge/topic-engineering-E91E63)](https://github.com/topics/engineering)
[![Construction](https://img.shields.io/badge/topic-construction-FF9800)](https://github.com/topics/construction)
[![Building](https://img.shields.io/badge/topic-building-795548)](https://github.com/topics/building)
[![Computer Vision](https://img.shields.io/badge/topic-computer--vision-4CAF50)](https://github.com/topics/computer-vision)

[English](#features) | [中文](#功能特性)

</div>

---

## What is this?

AI CAD Audit System is an intelligent construction drawing review platform that leverages LLM (Large Language Model) and computer vision to automate the compliance checking of architectural and engineering drawings against Chinese national building codes (GB standards).

It covers **12 engineering disciplines** and supports the full pipeline from DXF/DWG parsing to professional review report generation.

## Features

- **Multi-Discipline Review** — 12 specialized agents covering building, structure, HVAC, plumbing, electrical, fire protection, curtain wall, decoration, landscape, foundation pit, and more
- **Code Compliance Checking** — 100+ built-in checkpoints mapped to GB standards (GB50016, GB50011, GB50974, etc.)
- **DXF/DWG Parsing** — Automatic drawing extraction, frame splitting, grid splitting, and scale recognition
- **LLM-Powered Analysis** — Dual-route architecture: rule-based checking + vision-language model review
- **Cross-Discipline Verification** — Detects conflicts between different engineering disciplines (e.g., structural vs. MEP)
- **Professional Reports** — Generates role-based review reports (chief reviewer, discipline-specific, cross-check)
- **Web UI** — Built-in admin dashboard and review interface
- **Offline Mode** — Dry-run and demo modes for testing without LLM API access

## Architecture

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

## Quick Start

### Prerequisites

- Python 3.10+
- pip
- **Windows**: Visual C++ Redistributable (required by OpenCV)
- **Linux**: `sudo apt install libgl1-mesa-glx libglib2.0-0` (required by OpenCV)

### Installation

```bash
# Clone the repository
git clone https://github.com/AI-CAD-Audit/AI-CAD-Audit-System.git
cd AI-CAD-Audit-System

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Set your LLM API key as an environment variable:

```bash
# Option 1: ZhipuAI (recommended for Chinese users)
export ZHIPU_API_KEY="your-api-key"

# Option 2: DeepSeek
export DEEPSEEK_API_KEY="your-api-key"

# Option 3: OpenAI-compatible providers
export OPENAI_API_KEY="your-api-key"
```

### Usage

```bash
# Start via unified launcher (recommended)
python v7/launcher.py

# Start without auto-opening browser
python v7/launcher.py --no-browser

# Full review pipeline (requires DXF files + LLM API key)
python v7/master_v7.py

# Dry-run mode (no LLM calls, validates pipeline only)
python v7/master_v7.py --dry-run

# Demo mode (simulated data + review UI)
python v7/master_v7.py --demo

# Review-only mode (use existing problem pool)
python v7/master_v7.py --review-only
```

### Web UI

```bash
# Start admin dashboard + frontend + review UI (recommended)
python v7/launcher.py

# Or start admin server directly
python -m v7.admin.server

# Build EXE (Windows)
cd v7 && pyinstaller launcher.spec
```

## Checkpoint Coverage

| Discipline | Checkpoints | Key Standards |
|-----------|-------------|---------------|
| Building | Evacuation door width, stair width, corridor width | GB50016-2014 |
| Structure | Reinforcement ratio, beam-column joints | GB50011-2010 |
| Fire Protection | Fire compartment area, sprinkler coverage | GB50016, GB50974 |
| HVAC | Duct sizing, smoke exhaust rate | GB50736, GB51251 |
| Plumbing | Pipe sizing, drainage slope | GB50015 |
| Electrical | Cable fire rating, emergency lighting | GB50016, GB50034 |
| Curtain Wall | Panel thickness, sealant width | JGJ102 |
| Decoration | Finishing material fire rating | GB50222 |
| Landscape | Planting distance, drainage gradient | CJJ/T 82 |
| Foundation Pit | Retaining structure, monitoring points | JGJ120 |

## Project Structure

```
v7/
├── master_v7.py              # Main entry point
├── config.yaml               # Global configuration
├── agents/                   # 12 discipline review agents
│   ├── base_agent.py         # Base agent class
│   ├── chief_agent.py        # Chief reviewer (cross-check)
│   └── discipline_agents.py  # All discipline agents
├── checkpoints/              # Rule engine + YAML definitions
│   ├── engine.py             # Checkpoint execution engine
│   ├── checkpoint_schema.py  # Schema validation
│   └── definitions/          # YAML rule files per discipline
├── preprocessor/             # Drawing extraction & splitting
│   ├── drawing_extractor.py  # DXF content extraction
│   ├── drawing_pipeline.py   # Full preprocessing pipeline
│   ├── frame_splitter.py     # Frame-based splitting
│   └── grid_splitter.py      # Grid-based splitting
├── llm/                      # LLM adapter layer
│   ├── base_adapter.py       # Abstract LLM interface
│   ├── text_adapter.py       # Text-only LLM calls
│   └── vision_adapter.py     # Vision + text LLM calls
├── scanner/                  # Drawing content scanner
├── scheduler/                # Agent orchestration
├── problem_pool/             # Unified issue management
├── audit/                    # False-negative auditor
├── cross_drawing/            # Cross-drawing context
├── report_v7/                # Report generation
├── review_ui/                # Web review interface
├── admin/                    # Admin dashboard
└── db/                       # Database schema & migration
```

## How It Works

### 1. Drawing Preprocessing
DXF/DWG files are parsed, split into individual frames, and converted to images. Scale recognition ensures accurate dimension checking.

### 2. Rule-Based Checking
The checkpoint engine loads YAML-defined rules and performs deterministic checks (dimension limits, required elements, fire ratings) against extracted drawing data.

### 3. LLM-Powered Review
For complex checks requiring visual understanding (e.g., "Is the evacuation route clearly marked?"), the system sends drawing images + context to a vision-language model.

### 4. Cross-Discipline Verification
The Chief Agent aggregates findings from all discipline agents and identifies conflicts (e.g., structural opening vs. HVAC duct routing).

### 5. Report Generation
Issues are collected into a unified problem pool, audited for false negatives, and formatted into professional review reports by discipline.

## Screenshots

> **Note**: Screenshots will be added after the first public release.

<!-- Uncomment when screenshots are ready:
![Admin Dashboard](docs/images/admin-dashboard.png)
![Review Interface](docs/images/review-ui.png)
![Sample Report](docs/images/sample-report.png)
-->

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas where we especially need help:
- Adding more checkpoints for additional GB standards
- Improving DXF parsing for complex drawings
- Adding support for international building codes
- UI/UX improvements for the review interface

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [ezdxf](https://github.com/mozman/ezdxf) for DXF parsing
- LLM integration via OpenAI-compatible API
- Inspired by the need to automate the tedious manual drawing review process in China's construction industry

## Disclaimer

This tool is designed to **assist** human reviewers, not replace them. All automated findings should be verified by qualified professionals before making engineering decisions. The checkpoint rules are based on publicly available Chinese national standards but may not cover all local amendments or special cases.
