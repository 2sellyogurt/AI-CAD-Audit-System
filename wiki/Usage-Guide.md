# Usage Guide

## Running a Review

### Basic Usage

```bash
# Full pipeline review
python v7/master_v7.py
```

### Command Line Options

```bash
# Dry-run: validates pipeline without LLM calls
python v7/master_v7.py --dry-run

# Demo mode: simulated data + web UI
python v7/master_v7.py --demo

# Review-only: use existing problem pool data
python v7/master_v7.py --review-only
```

## Input Files

Place your DXF/DWG files in the input directory. The system supports:

- **DXF**: Directly supported via ezdxf
- **DWG**: Automatically converted to DXF (requires ODA File Converter or similar)
- **Multi-sheet**: Automatically split into individual frames

### File Naming Convention

Files are automatically classified by discipline based on filename prefixes:

| Prefix | Discipline |
|--------|-----------|
| `h-`, `暖通`, `hvac` | HVAC |
| `s-`, `结施`, `结构` | Structure |
| `水施`, `给排水`, `p-` | Plumbing |
| `电施`, `电气`, `e-` | Electrical |

## Web UI

### Admin Dashboard

```bash
python v7/admin/server.py
```

Access at `http://localhost:5000`. Features:
- Upload and manage drawing files
- Configure API settings
- View review results
- Manage checkpoint rules
- System monitoring

### Review Interface

```bash
python v7/review_ui/app.py
```

Interactive interface for:
- Viewing review findings
- Annotating issues
- Generating reports
- Cross-discipline comparison

## Output

### Reports

Reports are generated in `output_v7.0/`:
- **Markdown**: Human-readable review reports
- **Excel**: Structured data for further analysis
- **Role-based**: Chief reviewer, discipline-specific, cross-check reports

### Report Types

| Report | Description |
|--------|-------------|
| Chief Reviewer | Overall summary with cross-discipline findings |
| Discipline Reports | Detailed findings per engineering discipline |
| Cross-Check | Inter-discipline conflict analysis |
| Quality Score | Overall drawing quality assessment |

## Interpreting Results

### Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| A | Critical | Must fix before approval |
| B | Important | Should fix, document if deferred |
| C | Advisory | Improvement suggestion |

### Problem Categories

- **Dimension**: Measurements outside acceptable range
- **Missing Element**: Required component not found
- **Conflict**: Spatial conflict between disciplines
- **Non-Compliance**: Violates specific code requirement
- **Quality**: Poor drawing quality or unclear annotation

## Offline / No-API Mode

If you don't have an LLM API key, use:

```bash
python v7/master_v7.py --dry-run
```

This validates the pipeline and rule engine without making API calls. Results will only include rule-based (deterministic) findings.
