# Contributing to AI CAD Audit System

Thank you for your interest in contributing! This guide will help you get started.

## Quick Start

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/AI-CAD-Audit-System.git`
3. **Install** dependencies: `pip install -r requirements.txt`
4. **Create a branch**: `git checkout -b feature/your-feature-name`
5. **Make changes** and test with `pytest`
6. **Submit** a Pull Request

## Development Setup

```bash
# Install in development mode
pip install -r requirements.txt

# Run tests
pytest tests/

# Run dry-run mode (no LLM API key needed)
python v7/master_v7.py --dry-run
```

## How You Can Contribute

### Add Checkpoints

The easiest way to contribute is adding new checkpoint rules. Checkpoints are defined in YAML files under `v7/checkpoints/definitions/`.

Example checkpoint:

```yaml
- id: JZ-001
  name: Evacuation Door Net Width Check
  description: Check if residential door and exit net width >= 0.90m
  discipline: building
  check_type: dimension_min
  route: dual
  severity: A
  priority: 100
  standard_code: GB50016-2014(2018)
  standard_clause: "5.5.30"
  clause_text: "Net width of residential doors and exits shall not be less than 0.90m"
  target_object: ["evacuation door", "residential door", "exit"]
  target_property: "net width"
  operator: ">="
  limit_value: 900
  unit: mm
  suggestion_template: "Increase evacuation door width to >= 900mm"
  applicable_building_types: ["all"]
```

### Improve DXF Parsing

Help improve drawing extraction for complex drawings:
- Multi-scale drawings
- Non-standard title blocks
- Custom CAD entities

### Add International Code Support

Currently only Chinese GB standards are supported. We welcome:
- Eurocode (EN)
- International Building Code (IBC)
- NFPA standards
- Local building codes

### UI/UX Improvements

The web interface (Flask-based) can benefit from:
- Better responsive design
- Real-time progress updates
- Interactive drawing annotation
- Export to PDF

## Code Style

- Follow PEP 8
- Use type hints for function signatures
- Add docstrings to public functions and classes
- Keep functions focused — one function, one responsibility
- Write tests for new features

## Commit Messages

Use clear, descriptive commit messages:

```
feat: add curtain wall panel thickness checkpoint (JZ-CW-003)
fix: correct scale recognition for A0+ sheets
docs: update checkpoint coverage table in README
test: add unit tests for fire compartment area check
```

## Pull Request Process

1. Ensure all tests pass: `pytest`
2. Update documentation if you changed behavior
3. Add tests for new features
4. Keep PRs focused — one feature/fix per PR
5. Reference any related issues

## Reporting Issues

When filing an issue, please include:

- **OS and Python version**
- **Steps to reproduce**
- **Expected vs. actual behavior**
- **Sample DXF file** (if applicable, anonymized)
- **Error logs** (if any)

## Questions?

Feel free to open an issue with the `question` label, or start a discussion in the Discussions tab.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
