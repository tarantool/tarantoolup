#!/usr/bin/env python

from __future__ import print_function

import subprocess
import argparse
import configparser
import os
import sys
import time
import re
import math


config_defaults = {
}


def get_process_name(pid):
    pid = int(pid)
    proc = subprocess.Popen(['ps', '-ax', '-eo', 'pid,comm'],
                            stdout=subprocess.PIPE)
    proc.wait()
    results = proc.stdout.readlines()

    for result in results:
        try:
            result.strip()
            parts = re.findall(r'\S+', result.decode('utf-8'))
            if int(parts[0]) == pid:
                return parts[1]
        except Exception:
            pass # ignore parsing errors

    return None


def get_start_time(pid):
    pid = int(pid)
    proc = subprocess.Popen(['ps', '-ax', '-eo', 'pid,etime'],
                            stdout=subprocess.PIPE)
    proc.wait()
    results = proc.stdout.readlines()

    etime = None
    for result in results:
        try:
            result.strip()
            parts = re.findall(r'\S+', result.decode('utf-8'))
            if int(parts[0]) == pid:
                etime = parts[1]
                break
        except Exception:
            pass # ignore parsing errors

    if etime is None:
        return None

    days = 0
    rest = etime

    if '-' in etime:
        days, _, rest = etime.partition('-')
        days = int(days)

    rest = [int(part) for part in rest.split(':')]
    rest = (3-len(rest)) * [0] + rest

    hours, minutes, seconds = rest

    since_start = days*24*3600 + hours*3600 + minutes*60 + seconds
    return time.time() - since_start


def which(file_name):
    for path in os.environ["PATH"].split(os.pathsep):
        full_path = os.path.join(path, file_name)
        if os.path.exists(full_path) and os.access(full_path, os.X_OK):
            return full_path
    return None


def instance_split(instance_name):
    app, _, instance = instance_name.partition('.')

    return app, instance


def config_get_value(config, instance_name, key):
    app, instance = instance_split(instance_name)

    sections = [app+'.'+instance, app, 'default']

    for section in sections:
        if section in config:
            if key in config[section]:
                return config[section][key]

    if key in config_defaults:
        return config_defaults[key]


def config_merge(config, instance_name):
    result = {}

    app, instance = instance_split(instance_name)

    sections = ['default', app, app+'.'+instance]

    for section in sections:
        if section in config:
            for key in config[section]:
                result[key] = config[section][key]

    return result


def config_to_env(config):
    result = {}

    for k in config:
        result['TARANTOOL_'+k.upper()] = config[k]

    return result


def start_single_instance(config, instance_name):
    pass


def get_pid(pidfile):
    if not os.path.exists(pidfile):
        return None

    pid = None
    with open(pidfile, 'r') as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, 0)
    except Exception:
        return None

    return pid


# Detecting stale pids is important if our process has crashed and
# didn't clean up pid files after itself. Then another process could
# have taken the same pid and we shouldn't be fooled that it's
# tarantool.
def is_pidfile_stale(pidfile):
    pid = get_pid(pidfile)

    if pid is None:
        return True

    process_etime = get_start_time(pid)

    if process_etime is None:
        return True

    pid_mtime = os.path.getmtime(pidfile)

    if math.ceil(pid_mtime) < math.floor(process_etime):
        return True

    process_name = get_process_name(pid)

    if "tarantool" not in process_name:
        return True

    return False


def find_app_dir(config, instance_name):
    app, instance = instance_split(instance_name)
    app_dir = config_get_value(config, instance_name, 'app_dir')

    if app_dir is not None:
        return os.path.join(app_dir, app)

    init_lua = os.path.join(os.getcwd(), 'init.lua')
    rockspec = os.path.join(os.getcwd(), '%s-scm-1.rockspec' % app)

    if os.path.exists(init_lua) and os.path.exists(rockspec):
        return os.path.realpath(os.getcwd())

    return os.path.realpath(os.path.join(os.getcwd(), app))


def get_dirs(config, instance_name):
    data_dir = config_get_value(config, instance_name, 'data_dir')
    run_dir = config_get_value(config, instance_name, 'run_dir')
    log_dir = config_get_value(config, instance_name, 'log_dir')
    app_dir = find_app_dir(config, instance_name)

    if run_dir is None or log_dir is None or data_dir is None:
        work_dir = config_get_value(config, instance_name, 'work_dir')
        if work_dir is None:
            work_dir = os.path.join(os.getcwd(), 'tarantooldata')

        work_dir = os.path.realpath(work_dir)
        if not os.path.exists(work_dir):
            os.mkdir(work_dir)

    if run_dir is None:
        run_dir = os.path.join(work_dir, 'run')
        if not os.path.exists(run_dir):
            os.mkdir(run_dir)

    if data_dir is None:
        data_dir = os.path.join(work_dir, 'data')
        if not os.path.exists(data_dir):
            os.mkdir(data_dir)

    if log_dir is None:
        log_dir = os.path.join(work_dir, 'log')
        if not os.path.exists(log_dir):
            os.mkdir(log_dir)

    if not os.path.exists(run_dir):
        print("Unable to find run dir: %s" % run_dir)
        sys.exit(1)

    if not os.path.exists(data_dir):
        print("Unable to find data dir: %s" % data_dir)
        sys.exit(1)

    if not os.path.exists(log_dir):
        print("Unable to find log dir: %s" % log_dir)
        sys.exit(1)

    if not os.path.exists(app_dir):
        print("Unable to find app dir: %s" % app_dir)
        sys.exit(1)

    app_data_dir = os.path.join(data_dir, instance_name)

    if not os.path.exists(app_data_dir):
        os.mkdir(app_data_dir)

    return app_dir, log_dir, run_dir, app_data_dir



def stop_instance(config, instance_name):
    app_dir, log_dir, run_dir, data_dir = get_dirs(config, instance_name)

    pid_file = os.path.join(run_dir, instance_name + '.pid')
    pid_file = os.path.realpath(pid_file)

    if os.path.exists(pid_file) and is_pidfile_stale(pid_file):
        print("Removing stale pid file: %s" % pid_file)
        os.remove(pid_file)
        return

    pid = get_pid(pid_file)

    if pid is None:
        return

    print("Stopping %s" % instance_name)
    os.kill(pid, 15)



def start_instance(config, instance_name):
    app_dir, log_dir, run_dir, data_dir = get_dirs(config, instance_name)

    app, instance = instance_split(instance_name)

    app_dir = find_app_dir(config, instance_name)

    log_file = os.path.join(log_dir, instance_name + '.log')
    log_file = os.path.realpath(log_file)

    tarantool = os.path.join(app_dir, 'tarantool')

    if not os.path.exists(tarantool):
        tarantool = which('tarantool')

    if not tarantool:
        print("Unable to find tarantool binary for instance %s" %
              instance_name)
        sys.exit(1)

    tarantool = os.path.realpath(tarantool)

    init = os.path.join(app_dir, 'init.lua')
    if not os.path.exists(init):
        print("Unable to find init.lua for instance %s" % instance_name)
        sys.exit(1)

    init = os.path.realpath(init)

    pid_file = os.path.join(run_dir, instance_name + '.pid')
    pid_file = os.path.realpath(pid_file)

    control_file = os.path.join(run_dir, instance_name + '.control')
    control_file = os.path.realpath(control_file)

    if os.path.exists(pid_file) and is_pidfile_stale(pid_file):
        print("Removing stale pid file: %s" % pid_file)
        os.remove(pid_file)

    pid = get_pid(pid_file)

    if pid is not None:
        print("Already running: %s" % instance_name)
        return

    instance_config = config_merge(config, instance_name)
    env = config_to_env(instance_config)
    env['TARANTOOL_PID_FILE'] = pid_file
    env['TARANTOOL_INSTANCE_NAME'] = instance_name
    env['TARANTOOL_CONSOLE_SOCK'] = control_file
    env['TARANTOOL_LOG_FILE'] = log_file

    args = [tarantool, init]

    print("Starting: ", instance_name)

    # Fork, creating a new process for the child.
    try:
        process_id = os.fork()
    except OSError as e:
        print("Unable to fork, errno: {0}".format(e.errno))
        sys.exit(1)

    if process_id != 0:
        return
    # This is the child process. Continue.

    # detach from terminal
    process_id = os.setsid()
    if process_id == -1:
        sys.exit(1)

    devnull_fd = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull_fd, 0)
    os.dup2(devnull_fd, 1)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)

    os.chdir(data_dir)
    try:
        os.execve(tarantool, args, env)
    except Exception as ex:
        print(ex)
        sys.exit(1)


def get_instances(config, instance_name):
    result = []

    app, instance = instance_split(instance_name)

    if instance and instance_name in config:
        return [instance_name]
    else:
        for key in config:
            if key != 'default':
                candidate_app, candidate_instance = instance_split(key)

                if candidate_instance != '':
                    if instance != '':
                        if key == instance_name:
                            result.append(key)
                    elif app == '' or candidate_app == app:
                        result.append(key)

    return result


def start(config, instance_name):
    app, instance = instance_split(instance_name)

    if instance and instance_name in config:
        start_instance(config, instance_name)
    else:
        for key in config:
            if key != 'default':
                candidate_app, candidate_instance = instance_split(key)

                if candidate_instance != '':
                    if instance != '':
                        if key == instance_name:
                            start_instance(config, key)
                    elif app == '' or candidate_app == app:
                        start_instance(config, key)


def stop(config, instance_name):
    for instance in get_instances(config, instance_name):
        stop_instance(config, instance)



def attach(instance_name):
    pass


def read_config(filename='tarantool.ini'):
    if not os.path.exists(filename):
        Exception("Cluster config file doesn't exist: '%s'" % filename)

    parser = configparser.ConfigParser()
    parser.read(filename)

    cfg = {}

    for section in parser.sections():
        cfg[section] = {}
        for key in parser[section]:
            cfg[section][key] = parser[section][key].strip()

    return cfg


def find_config_file():
    home = os.path.expanduser('~')

    candidates = ['tarantool.ini',
                  '.tarantool.ini',
                  os.path.join(home, '.config/tarantool/tarantool.ini'),
                  '/etc/tarantool/tarantool.ini']

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return 'tarantool.ini'



def main():
    parser = argparse.ArgumentParser()

    config = find_config_file()

    parser.add_argument('-c', '--config',
                        help="Configuration file", default=config)

    subparsers = parser.add_subparsers(dest='command')
    subparsers.required = True

    start_parser = subparsers.add_parser("start", help="Start instances")
    start_parser.add_argument('-a', '--attach', help="Attach to instances",
                              action="store_true", default=False)
    start_parser.add_argument('instance_name', help="Instance name",
                              default='', nargs='?')

    stop_parser = subparsers.add_parser("stop", help="Stop instances")
    stop_parser.add_argument('instance_name', help="Instance name",
                             default='', nargs='?')

    args = parser.parse_args()

    if not os.path.exists(args.config):
        print("Can't find config file: %s" % args.config)

    cfg = read_config(args.config)

    if args.command == 'start':
        start(cfg, args.instance_name)
    elif args.command == 'stop':
        stop(cfg, args.instance_name)

    if getattr(args, 'attach', False):
        attach(args.instance_name)


if __name__ == "__main__":
    main()
