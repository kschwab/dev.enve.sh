#!/usr/bin/python3

import os
import subprocess
import pathlib

def enve_motd() -> str:

    # get uptime
    uptime = subprocess.run("uptime -p | cut -d ' ' -f 2-", shell=True, capture_output=True, text=True).stdout.strip()

    # get processors
    processor_name = subprocess.run("grep 'model name' /proc/cpuinfo | cut -d ' ' -f3- | awk {'print $0'} | head -1",
                                    shell=True, capture_output=True, text=True).stdout.strip()
    processor_name = processor_name.replace('(R)', '®')
    processor_name = processor_name.replace('(TM)', '™')
    processor_virt_count = subprocess.run("grep -ioP 'processor\t:' /proc/cpuinfo | wc -l",
                                          shell=True, capture_output=True, text=True).stdout.strip()

    # get memory
    mem_used, mem_avail, mem_total = subprocess.run("free -htg --si | grep 'Mem' | awk {'print $3,$7,$2'}",
                                                    shell=True, capture_output=True, text=True).stdout.strip().split()

    # get disk space
    disk_space = [('/', subprocess.run("flatpak-spawn --host df -H --output=avail / | tail -n+2",
                                       shell=True, capture_output=True, text=True).stdout.strip())]

    if os.path.exists('/home'):
        disk_space.append(('/home', subprocess.run("flatpak-spawn --host df -H --output=avail /home | tail -n+2",
                                                   shell=True, capture_output=True, text=True).stdout.strip()))

    if os.path.exists('/user'):
        disk_space.append(('/user', subprocess.run("flatpak-spawn --host df -H --output=avail /user | tail -n+2",
                                                   shell=True, capture_output=True, text=True).stdout.strip()))

    while len(disk_space) < 3:
        disk_space.append(('', ''))

    # get flatpak
    flatpak_ver = subprocess.run("flatpak-spawn --host flatpak --version | cut -d ' ' -f 2-",
                                 shell=True, capture_output=True, text=True).stdout.strip()
    flatpak_runtime = subprocess.run("cat /etc/*release | grep 'PRETTY_NAME' | cut -d '=' -f 2- | sed 's/\"//g'",
                                     shell=True, capture_output=True, text=True).stdout.strip()

    enve_motd_banner = \
r"""                 ,,))))))));,
              __)))))))))))))),
   \|/       -\(((((''''((((((((.     .----------------------------.
   -*-==//////((''  .     `)))))),   /  E N V E      _____________)
   /|\      ))| o    ;-.    '(((((  /            _______________)   ,(,
            ( `|    /  )    ;))))' /         _______________)    ,_))^;(~
               |   |   |   ,))((((_/      ________) __          %,;(;(>';'~
               o_);   ;    )))(((`    \ \   ~---~  `:: \       %%~~)(v;(`('~
                     ;    ''''````         `:       `:: |\,__,%%    );`'; ~ %
                    |   _                )     /      `:|`----'     `-'
              ______/\/~    |                 /        /
            /~;;.____/;;'  /          ___--,-(   `;;;/
           / //  _;______;'------~~~~~    /;;/\    /
          //  | |                        / ;   \;;,\
         (<_  | ;                      /',/-----'  _>
          \_| ||_                     //~;~~~~~~~~~
\e[32m─────────────╴\e[0m`\-| \e[32m─────────────────\e[0m (,~~ \e[32m──────────────────────────────────────
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━\e[0m \~| \e[32m━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓"""

    enve_motd_stats = \
"""
┃\e[0m CPU     \e[32m┃\e[0m {: <50} \e[32m┃\e[0m FREE SPACE    \e[32m┃
┃\e[0m RAM     \e[32m┃\e[0m {: <50} \e[32m┃\e[0m {: <5} {: >7} \e[32m┃
┃\e[0m UPTIME  \e[32m┃\e[0m {: <50} \e[32m┃\e[0m {: <5} {: >7} \e[32m┃
┃\e[0m FLATPAK \e[32m┃\e[0m {: <50} \e[32m┃\e[0m {: <5} {: >7} \e[32m┃\e[0m""".format(
    '%s (%s vCPU)' % (processor_name, processor_virt_count),
    '%s used, %s total (%s avail)' % (mem_used, mem_total, mem_avail), *disk_space[0],
    '%s' % uptime, *disk_space[1],
    'v%s, %s' % (flatpak_ver, flatpak_runtime), *disk_space[2])

    return enve_motd_banner + enve_motd_stats

def print_enve_motd() -> None:
    subprocess.run('echo -e "$ENVE_MOTD"', shell=True, env={'ENVE_MOTD': enve_motd()})

if __name__ == '__main__':
    print_enve_motd()
