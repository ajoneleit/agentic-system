# Project Naming System Update

## Overview

The project naming system has been updated to create short, meaningful project names (1-2 words) instead of long descriptions. Projects with the same purpose are automatically numbered.

## Changes Made

### 1. Updated `MetaAgent` class in `src/agents/meta_agent.py`

#### Added `_generate_project_name()` method:
- Uses Claude API to generate concise 1-2 word project names
- Falls back to keyword extraction if API fails
- Focuses on the main output/goal of the project

#### Updated `_initialize_project_storage()` method:
- Now checks for existing projects with the same name
- Automatically appends numbers for duplicates (e.g., hello_world, hello_world_2)
- Removes timestamp from project folder names

## Naming Examples

| User Request | Project Name |
|-------------|--------------|
| "Create a simple Python hello world script" | `hello_world` |
| "Make another hello world program" | `hello_world_2` |
| "Print hello amber in a python script" | `hello_amber` |
| "Build a calculator with add and subtract" | `calculator` |
| "Write a fibonacci sequence generator" | `fibonacci` |
| "Create a web scraper for Amazon" | `amazon_scraper` |
| "Generate a TODO list application" | `todo_list` |

## Project Structure

```
projects/
├── hello_world/
│   ├── workspace/
│   │   └── hello_world.py
│   ├── artifacts/
│   └── project_metadata.json
├── hello_world_2/
│   ├── workspace/
│   │   └── hello_world.py
│   ├── artifacts/
│   └── project_metadata.json
└── calculator/
    ├── workspace/
    │   ├── calculator.py
    │   └── test_calculator.py
    ├── artifacts/
    └── project_metadata.json
```

## Benefits

1. **Readable Names**: Project folders have meaningful names that describe their purpose
2. **Easy Navigation**: Finding projects in Windows Explorer is much easier
3. **Automatic Numbering**: No conflicts when creating similar projects
4. **Clean Organization**: All projects in one `./projects` folder with consistent structure

## Testing

Run these scripts to see the naming system in action:
- `test_naming_simple.py` - Tests naming logic without dependencies
- `demo_project_naming.py` - Live demo creating actual projects

The system ensures that all projects have short, descriptive names while handling duplicates gracefully through automatic numbering.