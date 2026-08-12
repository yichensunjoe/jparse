#!/bin/zsh
cd -- "${0:A:h}"
/usr/bin/python3 src/manage.py stop
printf '\n按任意键关闭…'
read -k 1

