#!/usr/bin/env sh
set -e

SOURCE_DIRECTORY="/home/pi/DairyCattleRaspberryPi/stm32/"

echo "Running start-services.sh"
user=$1
scriptname=$2
shift 2
args=$@
echo "Username: $user"
echo "Python Script to Start: $SOURCE_DIRECTORY$scriptname"
echo "Arguments: $args"


if command -v "systemctl" > /dev/null;
then
  if id "$user" > /dev/null && command -v "sudo" > /dev/null; then
    sudo -u "$user" python $UPDATE_CONF $args
    # sudo -u "$user" -n systemctl start "$service"
    sudo -u "$user" python "$SOURCE_DIRECTORY$scriptname" "$args"
  else
    echo "username or sudo command not found"
    python "$SOURCE_DIRECTORY$scriptname" "$args"
  fi
fi
