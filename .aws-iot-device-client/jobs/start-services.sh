#!/usr/bin/env sh
set -e

UPDATE_CONF="/home/pi/DairyCattleRaspberryPi/stm32/updateConfiguration.py"

echo "Running start-services.sh"
user=$1
service=$2
shift 2
args=$@
echo "Username: $user"
echo "Services to start: $services"
echo "Arguments: $args"


if command -v "systemctl" > /dev/null;
then
  if id "$user" > /dev/null && command -v "sudo" > /dev/null; then
    sudo -u "$user" python $UPDATE_CONF $args
    # sudo -u "$user" -n systemctl start "$service"
    sudo -u "$user" python "$service" "$args"
  else
    echo "username or sudo command not found"
    systemctl start "$service"
  fi
fi
