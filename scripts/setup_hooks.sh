#!/bin/bash

# Setup script for git hooks and permissions
# Run this once after cloning the repository

echo "🔧 Setting up git hooks and script permissions..."

# Configure git to ignore file mode changes to prevent conflicts
echo "⚙️  Configuring git to ignore file permission changes..."
git config core.filemode false

# Create the post-merge hook if it doesn't exist
if [ ! -f ".git/hooks/post-merge" ]; then
    echo "📝 Creating post-merge git hook..."
    cat > .git/hooks/post-merge << 'EOF'
#!/bin/bash

# Git post-merge hook to automatically set executable permissions
# This runs after every git pull/merge operation

# Set executable permissions for script files
chmod +x scripts/run_auto_validator.sh 2>/dev/null || true
chmod +x scripts/check_compatibility.sh 2>/dev/null || true
chmod +x scripts/check_requirements_changes.sh 2>/dev/null || true
chmod +x scripts/install_staging.sh 2>/dev/null || true
chmod +x scripts/setup_hooks.sh 2>/dev/null || true

echo "✅ Executable permissions restored for script files"
EOF
fi

# Make the post-merge hook executable
chmod +x .git/hooks/post-merge

# Set executable permissions for all script files
echo "🔑 Setting executable permissions for script files..."
chmod +x scripts/*.sh 2>/dev/null || true

echo "✅ Setup complete! Git hooks are now active."
echo "📋 Git is configured to ignore file permission changes to prevent conflicts."
echo "📋 From now on, script permissions will be automatically restored after git pulls."