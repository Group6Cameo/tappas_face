#!/usr/bin/env bash
# Currently in development, not yet tested

# Exit immediately if a command exits with a non-zero status
set -e

# 1. Update apt-get to ensure we have the latest package information
echo "Updating system packages..."
sudo apt update
sudo apt upgrade -y

echo "Installing system dependencies for OpenCV..."
sudo apt install -y libhdf5-dev libhdf5-103 libqtgui4 libqtwebkit4 libqt4-test libatlas-base-dev libjasper-dev libilmbase23 libopenexr23 libgstreamer1.0-dev

sudo apt install -y python3-picamera2

echo "Installing virtual environment support..."
sudo apt install -y python3-venv

echo "Setting up Python virtual environment 'cameo'..."
python3 -m venv ../cameo --system-site-packages
source ../cameo/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install cmake
pip install -r requirements.txt

# 2. Install hailo-all
sudo apt-get install -y hailo-all
sudo apt install rpicam-apps

# 3. Install required packages
sudo apt-get install -y \
    rsync \
    ffmpeg \
    x11-utils \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-virtualenv \
    python-gi-dev \
    libgirepository1.0-dev \
    gcc-12 \
    g++-12 \
    cmake \
    git \
    libzmq3-dev \
    libopencv-dev \
    python3-opencv \
    libcairo2-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-bad1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    gstreamer1.0-x \
    gstreamer1.0-alsa \
    gstreamer1.0-gl \
    gstreamer1.0-gtk3 \
    gstreamer1.0-qt5 \
    gstreamer1.0-pulseaudio \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    gstreamer1.0-libcamera

# 4. Clone the tappas_cpp12 repository in the parent folder, then move into it
cd ..
git clone https://github.com/Aoyamaxx/tappas_gcc12
cd tappas_gcc12

# 5. Run the install script with the specified parameters
./install.sh --skip-hailort --target-platform rpi
