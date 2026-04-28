ARG ROS_DISTRO=jazzy
FROM ros:${ROS_DISTRO}-ros-base

ARG ROS_DISTRO=jazzy
ENV ROS_DISTRO=${ROS_DISTRO}

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-venv \
    python3-pip \
    ros-${ROS_DISTRO}-control-msgs \
    ros-${ROS_DISTRO}-controller-manager \
    ros-${ROS_DISTRO}-joint-state-publisher \
    ros-${ROS_DISTRO}-moveit \
    ros-${ROS_DISTRO}-moveit-configs-utils \
    ros-${ROS_DISTRO}-moveit-msgs \
    ros-${ROS_DISTRO}-moveit-ros-move-group \
    ros-${ROS_DISTRO}-moveit-ros-planning-interface \
    ros-${ROS_DISTRO}-open-manipulator \
    ros-${ROS_DISTRO}-open-manipulator-bringup \
    ros-${ROS_DISTRO}-open-manipulator-description \
    ros-${ROS_DISTRO}-open-manipulator-moveit-config \
    ros-${ROS_DISTRO}-robot-state-publisher \
    ros-${ROS_DISTRO}-ros-gz-bridge \
    ros-${ROS_DISTRO}-ros-gz-sim \
    ros-${ROS_DISTRO}-ros2-control \
    ros-${ROS_DISTRO}-ros2-controllers \
    ros-${ROS_DISTRO}-trajectory-msgs \
    ros-${ROS_DISTRO}-xacro \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /tmp/omx-web-requirements.txt
RUN python3 -m venv --system-site-packages /opt/omx-web-venv \
    && source /opt/omx-web-venv/bin/activate \
    && python3 -m pip install --no-cache-dir -r /tmp/omx-web-requirements.txt

COPY backend /app/backend
COPY docs /app/docs

ENV PYTHONPATH=/app/backend
ENV OMX_ROS_WS=/home/kjhz/omx_ws
ENV OMX_ROS_SETUP=/home/kjhz/omx_ws/install/setup.bash

EXPOSE 8000

CMD source /opt/omx-web-venv/bin/activate \
    && if [ -f "$OMX_ROS_SETUP" ]; then source "$OMX_ROS_SETUP"; else source "/opt/ros/${ROS_DISTRO}/setup.bash"; fi \
    && uvicorn omx_web_bridge.app:app --host 0.0.0.0 --port 8000
