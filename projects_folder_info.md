# Projects Folder Configuration

All scripts in the agentic-system have been updated to use a consistent `./projects` folder for storing all generated artifacts and workspace files.

## Updated Files

### Root-level Test Scripts
- `example_usage.py` - Now uses `./projects`
- `test_project_creation.py` - Now uses `./projects`
- `test_workspace_system.py` - Now uses `./projects`
- `test_full_execution.py` - Now uses `./projects`
- `test_decomposition_fixed.py` - Now uses `./projects`
- `interactive_meta_agent_test.py` - Now uses `./projects`
- `test_meta_agent_simple.py` - Now uses `./projects`
- `test_meta_agent_mock.py` - Now uses `./projects`

### Test Files
- `tests/integration/test_artifact_integration.py` - Updated to use `projects` folder structure

### Example Files
- `examples/basic_usage.py` - Now uses `./projects/demo_project`
- `examples/artifact_management_demo.py` - Now uses `./projects/demo_artifacts`

### Core Configuration
- `src/agents/meta_agent.py` - Already defaults to `./projects` when no path is specified

## Default Behavior

The MetaAgent class now defaults to using `./projects` as the storage path when no specific path is provided:

```python
self.artifact_storage_path = artifact_storage_path or Path("./projects")
```

This ensures that regardless of which script is run, all projects will be created in a visible `projects` folder in the current directory, making it easy to find and access generated code from Windows Explorer.

## Project Structure

When a task is executed, the system creates:
```
projects/
└── [human_readable_project_name_timestamp]/
    ├── workspace/          # All generated code files
    │   ├── main.py
    │   ├── test_main.py
    │   └── ...
    └── artifacts/          # Internal artifact storage
```

All agents can read and write to the same workspace directory, ensuring seamless collaboration.