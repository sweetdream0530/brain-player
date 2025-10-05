#!/bin/bash

# Initialize variables
script="neurons/validator.py"
autoRunLoc=$(readlink -f "$0")
proc_name="brainplay_auto_validator" 
args=()
version_location="./game/__init__.py"
version="__version__"
branch="dev"

# Set repository directory and Python venv path
REPO_DIR="$(dirname "$(dirname "$autoRunLoc")")"
PYTHON_ENV="$REPO_DIR/venv"

# Change to repository directory to ensure relative paths work correctly
cd "$REPO_DIR"

# Default configuration - can be overridden by environment variables or command line
DEFAULT_CHECK_INTERVAL=1200  # Check for updates every 20 minutes
CHECK_INTERVAL=${CHECK_INTERVAL:-$DEFAULT_CHECK_INTERVAL}
LOG_FILE="./logs/validator_auto_update.log"
BACKUP_DIR="./backups"

old_args=$@

# Parse command line arguments for configuration
temp_args=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --check-interval)
            CHECK_INTERVAL="$2"
            shift 2
            ;;
        --log-file)
            LOG_FILE="$2"
            shift 2
            ;;
        --backup-dir)
            BACKUP_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] [VALIDATOR_ARGS...]"
            echo ""
            echo "Options:"
            echo "  --check-interval SECONDS    Set update check interval (default: 1200)"
            echo "  --log-file PATH             Set log file path"
            echo "  --backup-dir PATH           Set backup directory path"
            echo "  --help, -h                  Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  CHECK_INTERVAL              Override default check interval"
            echo ""
            echo "Examples:"
            echo "  $0 --check-interval 600     # Check every 10 minutes"
            echo "  $0 --check-interval 300     # Check every 5 minutes"
            echo "  CHECK_INTERVAL=180 $0       # Check every 3 minutes via env var"
            exit 0
            ;;
        *)
            # Pass remaining arguments to validator
            temp_args+=("$1")
            shift
            ;;
    esac
done

# Restore remaining arguments
set -- "${temp_args[@]}"

# Validate check interval
if ! [[ "$CHECK_INTERVAL" =~ ^[0-9]+$ ]] || [[ "$CHECK_INTERVAL" -lt 60 ]]; then
    echo "Error: CHECK_INTERVAL must be a number >= 60 seconds"
    exit 1
fi

# Create logs and backup directories if they don't exist
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
mkdir -p "$BACKUP_DIR" 2>/dev/null || true

# Verify log directory exists and is writable
if [ ! -d "$(dirname "$LOG_FILE")" ]; then
    echo "Warning: Could not create log directory $(dirname "$LOG_FILE")"
    echo "Logs will only be displayed to console"
    LOG_FILE="/dev/null"
fi

check_package_installed() {
    local package_name="$1"
    os_name=$(uname -s)
    
    if [[ "$os_name" == "Linux" ]]; then
        # Use dpkg-query to check if the package is installed
        if dpkg-query -W -f='${Status}' "$package_name" 2>/dev/null | grep -q "installed"; then
            return 1
        else
            return 0
        fi
    elif [[ "$os_name" == "Darwin" ]]; then
         if brew list --formula | grep -q "^$package_name$"; then
            return 1
        else
            return 0
        fi
    else
        echo "Unknown operating system"
        return 0
    fi
}

# Check if jq is installed before proceeding
check_package_installed "jq"
if [ "$?" -eq 0 ]; then
    echo "Error: Missing package 'jq'. Please install it for your system first."
    echo "On Ubuntu/Debian: sudo apt-get install jq"
    echo "On macOS: brew install jq"
    exit 1
fi

# Logging function with timestamps
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

# Convenience logging functions
log_info() {
    log "INFO" "$@"
}

log_warn() {
    log "WARN" "$@"
}

log_error() {
    log "ERROR" "$@"
}

log_debug() {
    log "DEBUG" "$@"
}

# Backup function to create a snapshot before updating
create_backup() {
    local backup_name="backup_$(date '+%Y%m%d_%H%M%S')"
    local backup_path="$BACKUP_DIR/$backup_name"
    
    log_info "Creating backup: $backup_name"
    
    # Create backup directory
    mkdir -p "$backup_path"
    
    # Copy critical files and directories
    cp -r "$REPO_DIR/game" "$backup_path/" 2>/dev/null
    cp -r "$REPO_DIR/neurons" "$backup_path/" 2>/dev/null
    cp "$REPO_DIR/requirements.txt" "$backup_path/" 2>/dev/null
    cp "$REPO_DIR/setup.py" "$backup_path/" 2>/dev/null
    
    # Store current git commit hash
    cd "$REPO_DIR"
    git rev-parse HEAD > "$backup_path/commit_hash.txt" 2>/dev/null
    
    # Store current version
    echo "$1" > "$backup_path/version.txt"
    
    if [[ $? -eq 0 ]]; then
        log_info "Backup created successfully at: $backup_path"
        echo "$backup_path"
        return 0
    else
        log_error "Failed to create backup"
        return 1
    fi
}

# Rollback function to restore from backup
rollback_from_backup() {
    local backup_path="$1"
    
    if [[ ! -d "$backup_path" ]]; then
        log_error "Backup directory not found: $backup_path"
        return 1
    fi
    
    log_warn "Rolling back from backup: $backup_path"
    
    # Stop the validator process
    pm2 stop "$PM2_PROCESS_NAME" 2>/dev/null
    
    cd "$REPO_DIR"
    
    # Get the commit hash from backup
    if [[ -f "$backup_path/commit_hash.txt" ]]; then
        local commit_hash=$(cat "$backup_path/commit_hash.txt")
        log_info "Attempting to rollback to commit: $commit_hash"
        
        # Reset to the backed up commit
        git reset --hard "$commit_hash"
        if [[ $? -ne 0 ]]; then
            log_error "Failed to reset to backup commit"
            return 1
        fi
    fi
    
    # Restore files from backup
    cp -r "$backup_path/game" "$REPO_DIR/" 2>/dev/null
    cp -r "$backup_path/neurons" "$REPO_DIR/" 2>/dev/null
    cp "$backup_path/requirements.txt" "$REPO_DIR/" 2>/dev/null
    cp "$backup_path/setup.py" "$REPO_DIR/" 2>/dev/null
    
    # Reinstall dependencies from backup
    if [[ -f "$backup_path/requirements.txt" ]]; then
        log_info "Reinstalling dependencies from backup..."
        "$PYTHON_ENV/bin/pip" install -r "$backup_path/requirements.txt"
    fi
    
    # Restart the validator
    pm2 restart "$PM2_PROCESS_NAME"
    
    log_info "Rollback completed successfully"
    return 0
}

# Clean old backups (keep only last 5)
cleanup_old_backups() {
    log_debug "Cleaning up old backups..."
    cd "$BACKUP_DIR" 2>/dev/null || return 0
    # Only show cleanup message if there are actually files to clean up
    local files_to_clean=$(ls -t 2>/dev/null | tail -n +6)
    if [ -n "$files_to_clean" ]; then
        echo "$files_to_clean" | xargs -r rm -rf 2>/dev/null
        log_debug "Old backups cleaned up"
    else
        log_debug "No old backups to clean up"
    fi
}

# Check if pm2 is installed
if ! command -v pm2 &> /dev/null
then
    log_error "pm2 could not be found. Please install pm2 first."
    log_info "To install see: https://pm2.keymetrics.io/docs/usage/quick-start/"
    exit 1
fi

log_info "Starting validator with auto-update functionality..."
log_info "Configuration:"
log_info "  Check interval: $CHECK_INTERVAL seconds ($((CHECK_INTERVAL/60)) minutes)"
log_info "  Log file: $LOG_FILE"
log_info "  Backup directory: $BACKUP_DIR"

# Checks if $1 is smaller than $2
# If $1 is smaller than or equal to $2, then true. 
# else false.
version_less_than_or_equal() {
    [  "$1" = "`echo -e "$1\n$2" | sort -V | head -n1`" ]
}

# Checks if $1 is smaller than $2
# If $1 is smaller than $2, then true. 
# else false.
version_less_than() {
    [ "$1" = "$2" ] && return 1 || version_less_than_or_equal $1 $2
}

# Returns the difference between 
# two versions as a numerical value.
get_version_difference() {
    local tag1="$1"
    local tag2="$2"

    # Extract the version numbers from the tags
    local version1=$(echo "$tag1" | sed 's/v//')
    local version2=$(echo "$tag2" | sed 's/v//')

    # Split the version numbers into an array
    IFS='.' read -ra version1_arr <<< "$version1"
    IFS='.' read -ra version2_arr <<< "$version2"

    # Calculate the numerical difference
    local diff=0
    for i in "${!version1_arr[@]}"; do
        local num1=${version1_arr[$i]}
        local num2=${version2_arr[$i]}

        # Compare the numbers and update the difference
        if (( num1 > num2 )); then
            diff=$((diff + num1 - num2))
        elif (( num1 < num2 )); then
            diff=$((diff + num2 - num1))
        fi
    done

    strip_quotes $diff
}

read_version_value() {
    # Read each line in the file
    while IFS= read -r line; do
        # Check if the line contains the variable name
        if [[ "$line" == *"$version"* ]]; then
            # Extract the value of the variable
            local value=$(echo "$line" | awk -F '=' '{print $2}' | tr -d ' ')
            strip_quotes $value
            return 0
        fi
    done < "$version_location"

    echo ""
}

check_variable_value_on_github() {
    local repo="$1"
    local file_path="$2"
    local variable_name="$3"

    local url="https://api.github.com/repos/$repo/contents/$file_path?ref=$branch"
    
    # Use curl with timeout - single attempt since we check every 20 minutes anyway
    local response=$(curl -s --max-time 30 "$url" 2>/dev/null)
    local curl_exit_code=$?
    
    # Check if curl failed
    if [[ $curl_exit_code -ne 0 ]]; then
        log_warn "Network error: Failed to connect to GitHub (curl exit code: $curl_exit_code). Will retry in next check cycle."
        return 1
    fi

    # Check if response is empty
    if [[ -z "$response" ]]; then
        log_warn "Empty response from GitHub API. Will retry in next check cycle."
        return 1
    fi

    # Check for API rate limit or other errors
    if echo "$response" | jq -e '.message' >/dev/null 2>&1; then
        local error_msg=$(echo "$response" | jq -r '.message')
        log_warn "GitHub API error: $error_msg. Will retry in next check cycle."
        return 1
    fi

    # Extract the content from the response
    local content=$(echo "$response" | tr -d '\n' | jq -r '.content' 2>/dev/null)

    if [[ "$content" == "null" || -z "$content" ]]; then
        log_error "File '$file_path' not found in the repository or content is null."
        return 1
    fi

    # Decode the Base64-encoded content
    local decoded_content=$(echo "$content" | base64 --decode 2>/dev/null)
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to decode base64 content from GitHub."
        return 1
    fi

    # Extract the variable value from the content
    local variable_value=$(echo "$decoded_content" | grep "$variable_name" | awk -F '=' '{print $2}' | tr -d ' ')

    if [[ -z "$variable_value" ]]; then
        log_error "Variable '$variable_name' not found in the file '$file_path'."
        return 1
    fi

    # Success - echo the stripped value and return 0
    strip_quotes $variable_value
    return 0
}

strip_quotes() {
    local input="$1"

    # Remove leading and trailing quotes using parameter expansion
    local stripped="${input#\"}"
    stripped="${stripped%\"}"

    echo "$stripped"
}

# Loop through all command line arguments
while [[ $# -gt 0 ]]; do
  arg="$1"

  # Check if the argument starts with a hyphen (flag)
  if [[ "$arg" == -* ]]; then
    # Check if the argument has a value
    if [[ $# -gt 1 && "$2" != -* ]]; then
          if [[ "$arg" == "--script" ]]; then
            script="$2";
            shift 2
        else
            # Add '=' sign between flag and value
            args+=("'$arg'");
            args+=("'$2'");
            shift 2
        fi
    else
      # Add '=True' for flags with no value
      args+=("'$arg'");
      shift
    fi
  else
    # Argument is not a flag, add it as it is
    args+=("'$arg '");
    shift
  fi
done

# Check if script argument was provided
if [[ -z "$script" ]]; then
    echo "The --script argument is required."
    exit 1
fi

echo watching branch: $branch
echo pm2 process name: $proc_name

# Get the current version locally.
current_version=$(read_version_value)

# Check if script is already running with pm2
if pm2 status | grep -q $proc_name; then
    echo "The script is already running with pm2. Stopping and restarting..."
    pm2 stop $proc_name
    pm2 delete $proc_name
fi

# Run the Python script with the arguments using pm2
echo "Running $script with the following pm2 config:"

# Join the arguments with commas using printf
joined_args=$(printf "%s," "${args[@]}")

# Remove the trailing comma
joined_args=${joined_args%,}

# Create the pm2 config file
echo "module.exports = {
  apps : [{
    name   : '$proc_name',
    script : '$script',
    interpreter: '$PYTHON_ENV/bin/python',
    min_uptime: '5m',
    max_restarts: '5',
    args: [$joined_args]
  }]
}" > app.config.js

# Print configuration to be used
cat app.config.js

pm2 start app.config.js

log_info "Starting auto-update monitoring loop..."
    
    while true; do
        log_info "Checking for updates..."

        # First ensure that this is a git installation
        if [ -d "./.git" ]; then

            # check value on github remotely
            latest_version=$(check_variable_value_on_github "shiftlayer-llc/brainplay-subnet" "game/__init__.py" "__version__")

            # If the file has been updated
            if version_less_than $current_version $latest_version; then
                log_info "Latest version: $latest_version"
                log_info "Current version: $current_version"
                diff=$(get_version_difference $latest_version $current_version)
                if [ "$diff" -gt 0 ]; then
                    # Create backup before updating
                    backup_path=$(create_backup "$current_version")
                    if [[ $? -ne 0 ]]; then
                        log_error "Failed to create backup. Skipping update for safety."
                        sleep 1200
                        continue
                    fi

                    # Pull latest changes
                    # Failed git pull will return a non-zero output
                    log_debug "Pulling latest changes from repository..."
                    if git pull origin $branch; then
                        # latest_version is newer than current_version, should download and reinstall.
                        log_info "New version published. Updating the local copy."

                        # Install latest changes just in case.
                        log_info "Installing updated dependencies..."
                        if ! "$PYTHON_ENV/bin/pip" install -e .; then
                            log_error "Failed to install dependencies. Rolling back..."
                            rollback_from_backup "$backup_path"
                            sleep 1200
                            continue
                        fi

                        # # Run the Python script with the arguments using pm2
                        # TODO (shib): Remove this pm2 del in the next spec version update.
                        # pm2 del auto_run_validator
                        log_info "Restarting PM2 process"
                        
                        # Test if the restart is successful
                        if ! pm2 restart $proc_name; then
                            log_error "Failed to restart PM2 process. Rolling back..."
                            rollback_from_backup "$backup_path"
                            sleep 1200
                            continue
                        fi

                        # Verify the process is running
                        sleep 5
                        if ! pm2 describe $proc_name | grep -q "online"; then
                            log_error "Validator process failed to start properly. Rolling back..."
                            rollback_from_backup "$backup_path"
                            sleep 1200
                            continue
                        fi

                        # Update current version:
                        current_version=$(read_version_value)
                        log_info "Validator updated and restarted successfully!"
                        
                        # Clean up old backups
                        cleanup_old_backups

                        # Restart the validator PM2 process instead of the entire script
                        log_info "Restarting validator process..."
                        pm2 restart $proc_name
                        log_info "Validator updated and restarted successfully!"
                    else
                        log_error "**Will not update**"
                        log_error "It appears you have made changes on your local copy. Please stash your changes using git stash."
                        # Remove the backup since update failed
                        rm -rf "$backup_path" 2>/dev/null
                    fi
                else
                    # current version is newer than the latest on git. This is likely a local copy, so do nothing. 
                    log_warn "**Will not update**"
                    log_warn "The local version is $diff versions behind. Please manually update to the latest version and re-run this script."
                fi
            else
                log_debug "**Skipping update**"
                log_debug "$current_version is the same as or more than $latest_version. You are likely running locally."
            fi
        else
            log_error "The installation does not appear to be done through Git. Please install from source at https://github.com/shiftlayer-llc/brainplay-subnet and rerun this script."
        fi
        
        # Wait for the configured interval
        # This should be plenty of time for validators to catch up
        # and should prevent any rate limitations by GitHub.
        log_debug "Next check in $CHECK_INTERVAL seconds ($((CHECK_INTERVAL/60)) minutes)..."
        sleep $CHECK_INTERVAL
    done