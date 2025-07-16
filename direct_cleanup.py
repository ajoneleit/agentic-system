import os
import shutil

# Function to remove a directory
def remove_directory(path):
    if os.path.exists(path):
        shutil.rmtree(path)
        print(f"Removed: {path}")
    else:
        print(f"Not found: {path}")

# Base path
base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'

# List of directories to remove (from the LS output)
directories_to_remove = [
    'calculator', 'calculator_2', 'calculator_3', 'calculator_4', 'calculator_5',
    'calculator_6', 'calculator_7', 'calculator_8', 'calculator_9',
    'concurrent_failure_tests', 'concurrent_failure_tests_2', 'concurrent_failure_tests_3',
    'concurrent_failures_test',
    'execute_multiple_concurrent', 'execute_multiple_concurrent_2', 'execute_multiple_concurrent_3',
    'execute_multiple_concurrent_4', 'execute_multiple_concurrent_5', 'execute_multiple_concurrent_6',
    'execute_multiple_concurrent_7', 'execute_multiple_concurrent_8', 'execute_multiple_concurrent_9',
    'execute_multiple_concurrent_10', 'execute_multiple_concurrent_11', 'execute_multiple_concurrent_12',
    'execute_multiple_concurrent_13',
    'execute_resource_intensive', 'execute_resource_intensive_2', 'execute_resource_intensive_3',
    'execute_resource_intensive_4', 'execute_resource_intensive_5', 'execute_resource_intensive_6',
    'execute_resource_intensive_7', 'execute_resource_intensive_8', 'execute_resource_intensive_9',
    'execute_resource_intensive_10', 'execute_resource_intensive_11', 'execute_resource_intensive_12',
    'execute_resource_intensive_13', 'execute_resource_intensive_14', 'execute_resource_intensive_15',
    'heavy_task_1', 'heavy_task_2', 'heavy_task_handler', 'heavy_task_runner',
    'hello_world_python', 'hello_world_python_2', 'hello_world_python_3', 'hello_world_python_4',
    'hello_world_python_5', 'hello_world_python_6', 'hello_world_python_7', 'hello_world_python_8',
    'hello_world_python_9', 'hello_world_python_10', 'hello_world_python_11', 'hello_world_python_12',
    'hello_world_python_13', 'hello_world_python_14',
    'invalid_request', 'invalid_request_2', 'invalid_request_3', 'invalid_request_4', 'invalid_request_5',
    'invalid_request_6', 'invalid_request_7', 'invalid_request_8', 'invalid_request_9', 'invalid_request_10',
    'invalid_request_11', 'invalid_request_12', 'invalid_request_13', 'invalid_request_14', 'invalid_request_15',
    'invalid_request_16', 'invalid_request_17', 'invalid_request_18',
    'partial_success', 'partial_success_2', 'partial_success_3', 'partial_success_4', 'partial_success_5',
    'partial_success_6', 'partial_success_handler', 'partial_success_tracker',
    'project', 'project_2', 'project_3', 'project_4', 'project_5', 'project_6', 'project_7',
    'project_8', 'project_9', 'project_10', 'project_11', 'project_12', 'project_13', 'project_14',
    'project_15', 'project_16', 'project_17',
    'project_name_hello_world', 'project_name_hello_world_2', 'project_name_hello_world_3',
    'project_name_hello_world_4', 'project_name_hello_world_5', 'project_name_hello_world_6',
    'project_name_hello_world_7', 'project_name_hello_world_8', 'project_name_hello_world_9',
    'project_name_hello_world_10', 'project_name_multi_agent', 'project_name_test_project',
    'project_name_test_project_2', 'project_name_test_project_3',
    'python_gui_calculator', 'python_hello_world',
    'rest_api_postgresql', 'rest_api_postgresql_2', 'rest_api_postgresql_3', 'rest_api_postgresql_4',
    'rest_api_postgresql_5', 'rest_api_postgresql_6', 'rest_api_postgresql_7', 'rest_api_postgresql_8',
    'rest_api_postgresql_9', 'rest_api_postgresql_10',
    'test_concurrent_failures', 'test_concurrent_failures_2',
    'test_project', 'test_project_2', 'test_project_3', 'test_project_4', 'test_project_5',
    'test_project_6', 'test_project_7', 'test_project_8', 'test_project_9', 'test_project_10',
    'test_project_11', 'test_project_12', 'test_project_13', 'test_project_14', 'test_project_15',
    'test_project_16', 'test_project_17', 'test_project_18',
    'todo_list', 'todo_list_2', 'todo_list_3',
    'untitled_project',
    'weather_api_client', 'weather_cli_tool', 'weather_cli_tool_2', 'weather_cli_tool_3',
    'weather_client', 'weather_desktop_app', 'weather_desktop_app_2'
]

# Remove each directory
for dir_name in directories_to_remove:
    full_path = os.path.join(base_path, dir_name)
    remove_directory(full_path)

print(f"\nRemoval complete. Removed {len(directories_to_remove)} directories.")

# List remaining contents
print("\nRemaining contents:")
try:
    remaining = os.listdir(base_path)
    for item in remaining:
        print(f"  {item}")
except Exception as e:
    print(f"Error listing contents: {e}")