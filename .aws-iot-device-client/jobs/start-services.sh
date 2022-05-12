#!/usr/bin/env sh
set -e

SOURCE_DIRECTORY="/home/pi/DairyCattleRaspberryPi/stm32/"

echo "$@"

user=$1
args=$2
echo "Username: $user"
echo "Python Script to Start: $SOURCE_DIRECTORY$args"
echo "Arguments: $args"

# Hacky way to get the first item in args
for arg in $args
do
  scriptname=$arg
  break
done

if command -v "systemctl" > /dev/null;
then
  if id "$user" > /dev/null 2>&1 && command -v "sudo" > /dev/null; then
    echo $(pkill -f $SOURCE_DIRECTORY$scriptname)
    sudo -u nohup "$user" python $SOURCE_DIRECTORY$args  > /dev/null 2>&1 &
  else
    echo "username or sudo command not found"
    echo $(pkill -f $SOURCE_DIRECTORY$scriptname)
    echo "killed old"
    nohup python $SOURCE_DIRECTORY$args > /dev/null 2>&1 &
  fi
fi
echo "done"
