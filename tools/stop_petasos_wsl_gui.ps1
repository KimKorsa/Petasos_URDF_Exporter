$ErrorActionPreference = "SilentlyContinue"
$distro = "Ubuntu-22.04"

$registered = (& wsl.exe --list --quiet 2>$null | Out-String) -replace "`0", ""
if ($registered -notmatch "(?im)^\s*Ubuntu-22\.04\s*$") {
    exit 0
}

$cleanupScript = @'
set +e
stopped=0
runtime_dir="$HOME/petasos_ros2_ws/.petasos_runtime"

for pid_file in "$runtime_dir"/*.pid; do
  [ -f "$pid_file" ] || continue
  pid="$(cat "$pid_file" 2>/dev/null)"
  case "$pid" in
    ''|*[!0-9]*) rm -f -- "$pid_file"; continue ;;
  esac
  if [ -r "/proc/$pid/cmdline" ]; then
    command_line="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
    case "$command_line" in
      *"ros2 launch"*"display.launch.py"*)
        kill -TERM "$pid" 2>/dev/null && stopped=$((stopped + 1))
        ;;
    esac
  fi
  rm -f -- "$pid_file"
done

rviz_pids="$(pgrep -x rviz2 2>/dev/null)"
if [ -n "$rviz_pids" ]; then
  rviz_count="$(printf '%s\n' "$rviz_pids" | wc -l)"
  pkill -TERM -x rviz2 2>/dev/null
  stopped=$((stopped + rviz_count))
  sleep 0.5
  pkill -KILL -x rviz2 2>/dev/null
fi

for process_name in moveit_setup_assistant move_group joint_state_publisher_gui robot_state_publisher ros2_control_node; do
  process_pids="$(pgrep -x "$process_name" 2>/dev/null)"
  if [ -n "$process_pids" ]; then
    process_count="$(printf '%s\n' "$process_pids" | wc -l)"
    pkill -TERM -x "$process_name" 2>/dev/null
    stopped=$((stopped + process_count))
  fi
done

pkill -TERM -f '[r]os2 launch .*demo\.launch\.py' 2>/dev/null
sleep 0.5
for process_name in moveit_setup_assistant move_group joint_state_publisher_gui robot_state_publisher ros2_control_node; do
  pkill -KILL -x "$process_name" 2>/dev/null
done
pkill -KILL -f '[r]os2 launch .*demo\.launch\.py' 2>/dev/null

printf 'PETASOS_RVIZ_CLEANED:%s\n' "$stopped"
exit 0
'@

$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($cleanupScript))
$command = "printf '%s' '$encoded' | base64 -d | bash"
$output = & wsl.exe -d $distro -- bash -lc $command 2>$null

$match = [regex]::Match(($output | Out-String), "PETASOS_RVIZ_CLEANED:(\d+)")
if ($match.Success -and [int]$match.Groups[1].Value -gt 0) {
    Write-Host "Previous RViz session closed."
}

exit 0
