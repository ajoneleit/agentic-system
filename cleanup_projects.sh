#!/bin/bash

# Navigate to projects directory
cd /mnt/c/Users/ajoneleit/agentic-system/projects

# Remove all directories except artifacts, metadata, and index.json
for dir in */; do
    if [ "$dir" != "artifacts/" ] && [ "$dir" != "metadata/" ]; then
        echo "Removing directory: $dir"
        rm -rf "$dir"
    fi
done

# List remaining contents
echo "Remaining contents:"
ls -la