# Setup Instructions for Running the Interactive Meta Agent Test

To run the interactive Meta Agent test that shows task decomposition with real Claude API calls, you need to set up your environment:

## 1. Create a .env file

Create a file named `.env` in the project root directory with your Anthropic API key:

```bash
# In the project root: /mnt/c/Users/ajoneleit/agentic-system/
echo "ANTHROPIC_API_KEY=your_api_key_here" > .env
```

Replace `your_api_key_here` with your actual Anthropic API key.

## 2. Activate the virtual environment

The project has a virtual environment with all dependencies installed:

```bash
# From the project root
source venv/bin/activate
```

You should see `(venv)` appear in your terminal prompt.

## 3. Run the interactive test

Now you can run the interactive Meta Agent test:

```bash
python interactive_meta_agent_test.py
```

This will present a menu where you can:
- Option 1: Test task decomposition only (see all subtask JSONs)
- Option 2: Test full execution (decompose + execute)

## What the test does

When you choose option 1 and enter a task:
1. The Meta Agent sends your task to Claude Opus for analysis
2. Claude Opus decomposes it into subtasks with:
   - name
   - description  
   - agent_type (which sub-agent should handle it)
   - complexity
   - dependencies
   - priority
   - other metadata
3. The test displays each subtask as a detailed JSON object
4. Shows dependency analysis and execution planning

## Example tasks to try

- "Create a Python web scraper that extracts product prices from an e-commerce website"
- "Build a REST API with user authentication and CRUD operations"
- "Create a machine learning model to classify images"
- "Develop a real-time chat application with WebSockets"

## Alternative: Run the demo without API calls

If you want to see the task decomposition format without making API calls:

```bash
python demo_task_decomposition.py
```

This shows example decompositions with the exact JSON structure that the real Meta Agent produces.

## Alternative: Run with mocked responses

To test with mocked Claude responses:

```bash
python test_meta_agent_mock.py
```

This simulates the Meta Agent behavior without making actual API calls.