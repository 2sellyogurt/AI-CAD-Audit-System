# Getting Started Guide

## Prerequisites

- **Python 3.10+** (3.11 recommended)
- **pip** package manager
- **LLM API Key** (optional for dry-run/demo modes)
  - ZhipuAI (recommended for Chinese users)
  - DeepSeek
  - OpenAI-compatible providers

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/AI-CAD-Audit-System.git
cd AI-CAD-Audit-System
```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv venv

# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure LLM API Key

Choose one of the following methods:

**Method A: Environment Variable (Recommended)**

```bash
# Linux/macOS
export ZHIPU_API_KEY="your-api-key-here"

# Windows PowerShell
$env:ZHIPU_API_KEY = "your-api-key-here"
```

**Method B: Configuration File**

The system will prompt you to enter your API key on first run. Keys are encrypted and stored locally.

## Running the System

### Dry-Run Mode (No API Key Needed)

Validates that all modules load correctly and the pipeline is functional:

```bash
python v7/master_v7.py --dry-run
```

### Demo Mode (No API Key Needed)

Runs with simulated data and launches the review UI:

```bash
python v7/master_v7.py --demo
```

### Full Review Pipeline

Requires DXF files and an LLM API key:

```bash
# Place DXF files in the input directory
cp /path/to/your/drawings/*.dxf v7/input/

# Run full pipeline
python v7/master_v7.py
```

### Review-Only Mode

Launch the review UI using an existing problem pool (no LLM calls):

```bash
python v7/master_v7.py --review-only
```

## Web Interfaces

### Admin Dashboard

```bash
python v7/admin/server.py
# Open http://localhost:5000 in your browser
```

Features:
- Upload and manage drawings
- Configure review parameters
- Monitor review progress
- View system status

### Review Interface

```bash
python v7/review_ui/app.py
# Open http://localhost:5001 in your browser
```

Features:
- View detected issues on drawings
- Accept/reject/waive findings
- Add comments and annotations
- Export final review reports

## Understanding the Output

### Report Types

| Report | Description |
|--------|-------------|
| Executive Summary | High-level overview with statistics |
| Discipline Reports | Detailed findings per engineering discipline |
| Cross-Check Report | Inter-discipline conflicts and inconsistencies |
| Issue List | Complete list of all detected issues |

### Issue Severity Levels

| Level | Label | Description |
|-------|-------|-------------|
| A | Mandatory | Code violations that must be fixed |
| B | Important | Significant issues that should be addressed |
| C | Advisory | Suggestions for improvement |

### Issue Categories

- **Code Violation**: Fails to meet a specific code requirement
- **Design Defect**: Potential design problem not directly violating code
- **Missing Element**: Required element not found in drawing
- **Dimension Error**: Dimension outside acceptable range
- **Cross-Discipline Conflict**: Inconsistency between disciplines

## Adding Custom Checkpoints

Create a YAML file in `v7/checkpoints/definitions/`:

```yaml
discipline: building
description: Custom building checkpoints

checkpoints:
  - id: JZ-CUSTOM-001
    name: My Custom Check
    description: Check if X meets Y requirement
    discipline: building
    check_type: dimension_min
    route: dual
    severity: B
    priority: 50
    standard_code: GBXXXX-XXXX
    standard_clause: "X.X.X"
    clause_text: "Requirement text from the standard"
    target_object: ["target_element"]
    target_property: "property_to_check"
    operator: ">="
    limit_value: 1000
    unit: mm
    suggestion_template: "Increase X to >= 1000mm"
    applicable_building_types: ["all"]
```

## Troubleshooting

### "No module named 'v7'"

Make sure you're running from the project root directory, or set PYTHONPATH:

```bash
export PYTHONPATH=/path/to/AI-CAD-Audit-System
```

### "DXF file parsing errors"

- Ensure the DXF file is not corrupted (try opening in a CAD viewer first)
- Some proprietary DWG entities may not be supported — convert to DXF R2013 or later
- Very large files may need to be split manually before processing

### "LLM API timeout"

- Check your internet connection
- Verify your API key is valid
- Try a different LLM provider in `v7/config.yaml`

### "OSError: ODA File Converter not found"

This occurs when trying to convert DWG files. Install the [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter) or provide DXF files directly.

## Next Steps

- Read the [Architecture Guide](architecture.md) to understand the system design
- Check [CONTRIBUTING.md](../CONTRIBUTING.md) to contribute checkpoints or improvements
- Browse the checkpoint definitions in `v7/checkpoints/definitions/` for examples
