#!/usr/bin/env bash
set -euo pipefail

ROS_APT_DEB="/tmp/ros2-apt-source.deb"
TARGET_USER="${1:-}"

cleanup() {
  rm -f "$ROS_APT_DEB"
}
trap cleanup EXIT

source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "22.04" ]]; then
  echo "This installer only supports Ubuntu 22.04." >&2
  exit 10
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This package installer must be launched as Ubuntu root." >&2
  exit 12
fi

echo
echo "[1/5] Updating Ubuntu package information..."
sudo apt-get update
echo "[1/5] Applying Ubuntu package updates. This can take several minutes..."
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

echo
echo "[2/5] Preparing locale and the official ROS 2 package source..."
sudo apt-get install -y locales software-properties-common curl ca-certificates
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
sudo add-apt-repository universe -y
sudo apt-get update

ROS_APT_SOURCE_VERSION="$(
  curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest |
    grep -F '"tag_name"' |
    head -n 1 |
    cut -d '"' -f 4
)"
if [[ -z "$ROS_APT_SOURCE_VERSION" ]]; then
  echo "Could not determine the current ros-apt-source release." >&2
  exit 11
fi

curl -fL \
  -o "$ROS_APT_DEB" \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.jammy_all.deb"
sudo dpkg -i "$ROS_APT_DEB"
sudo apt-get update

echo
echo "[3/5] Installing ROS 2 Humble, RViz, MoveIt, and Petasos support tools..."
echo "[3/5] apt may pause visually while unpacking large packages; do not close this window."
sudo apt-get install -y \
  ros-humble-desktop \
  ros-humble-joint-state-publisher-gui \
  ros-humble-moveit \
  ros-humble-moveit-setup-assistant \
  ros-humble-gazebo-ros-pkgs \
  ros-humble-ros2-control \
  ros-humble-ros2-controllers \
  python3-colcon-common-extensions \
  python3-rosdep \
  python3-vcstool

echo "[4/5] Initializing rosdep..."
if ! sudo rosdep init 2>/dev/null; then
  echo "rosdep was already initialized; continuing."
fi
if [[ -n "$TARGET_USER" && "$TARGET_USER" != "root" ]]; then
  sudo -H -u "$TARGET_USER" rosdep update
else
  rosdep update
fi

echo "[5/5] Verifying ROS 2, RViz, and MoveIt..."
# ROS/ament setup files are not guaranteed to be compatible with Bash
# nounset mode. Keep strict error handling for this installer, but suspend
# nounset only while the official environment file initializes its variables.
set +u
source /opt/ros/humble/setup.bash
set -u
ros2 pkg prefix rviz2 >/dev/null
ros2 pkg prefix joint_state_publisher_gui >/dev/null
ros2 pkg prefix moveit_setup_assistant >/dev/null
ros2 pkg prefix moveit_ros_move_group >/dev/null
ros2 pkg prefix controller_manager >/dev/null
ros2 pkg prefix joint_state_broadcaster >/dev/null
ros2 pkg prefix joint_trajectory_controller >/dev/null
ros2 pkg prefix gazebo_ros >/dev/null
command -v colcon >/dev/null
command -v rosdep >/dev/null
command -v xacro >/dev/null

echo
echo "ROS 2 Humble installation and verification completed."
