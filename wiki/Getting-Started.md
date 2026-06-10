# Getting Started

## Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Git (optional, for cloning)

## Installation

```bash
# Clone the repository
git clone https://github.com/2sellyogurt/AI-CAD-Audit-System.git
cd AI-CAD-Audit-System

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Set your LLM API key as an environment variable:

```bash
# ZhipuAI (recommended for Chinese users)
export ZHIPU_API_KEY="your-api-key"

# DeepSeek
export DEEPSEEK_API_KEY="your-api-key"

# OpenAI-compatible providers
export OPENAI_API_KEY="your-api-key"
```

## First Run

```bash
# Full review pipeline (requires DXF files + LLM API key)
python v7/master_v7.py

# Dry-run mode (no LLM calls, validates pipeline only)
python v7/master_v7.py --dry-run

# Demo mode (simulated data + review UI)
python v7/master_v7.py --demo

# Review-only mode (use existing problem pool)
python v7/master_v7.py --review-only
```

## Web UI

```bash
# Start admin dashboard
python v7/admin/server.py

# Start review interface
python v7/review_ui/app.py
```

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_dag_executor.py -v
```

## Next Steps

- Read the [Architecture](Architecture) page to understand system design
- Check the [Configuration](Configuration) page for advanced settings
- See the [Usage Guide](Usage-Guide) for detailed workflows
