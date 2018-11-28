#!/usr/bin/env python3

import subprocess
import argparse
import configparser
import os
import sys
import fcntl

config_defaults = {
    'run_dir': './run',
    'work_dir': './data',
    'log_dir': './log',
    'app_dir': './app'
}


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
    pid = None
    with open(pidfile, 'r') as f:
        pid = int(f.read().strip())

    # check that we can access this pid
    os.kill(pid, 0)

    return pid


def stop_instance(config, instance_name):
    run_dir = config_get_value(config, instance_name, 'run_dir')
    if not os.path.exists(run_dir):
        print("Unable to find run dir: %s" % run_dir)
        sys.exit(1)

    pid_file = os.path.join(run_dir, instance_name + '.pid')

    pid = get_pid(pid_file)

    print("Stopping %s" % instance_name)
    os.kill(pid, 15)



def start_instance(config, instance_name):
    print("Starting: ", instance_name)
    work_dir = config_get_value(config, instance_name, 'work_dir')
    app_work_dir = os.path.join(work_dir, instance_name)
    run_dir = config_get_value(config, instance_name, 'run_dir')
    app_dir = config_get_value(config, instance_name, 'app_dir')
    log_dir = config_get_value(config, instance_name, 'log_dir')

    app, instance = instance_split(instance_name)

    app_dir = os.path.join(app_dir, app)


    if not os.path.exists(work_dir):
        print("Unable to find work dir: %s" % work_dir)
        sys.exit(1)

    if not os.path.exists(app_work_dir):
        os.mkdir(app_work_dir)

    if not os.path.exists(app_dir):
        print("Unable to find app dir: %s" % app_dir)
        sys.exit(1)

    if not os.path.exists(run_dir):
        print("Unable to find run dir: %s" % run_dir)
        sys.exit(1)

    if not os.path.exists(log_dir):
        print("Unable to find log dir: %s" % log_dir)
        sys.exit(1)


    log_file = os.path.join(log_dir, instance_name + '.log')

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

    instance_config = config_merge(config, instance_name)
    env = config_to_env(instance_config)
    env['TARANTOOL_PID_FILE'] = pid_file

    args = [tarantool, init]

    print("work_dir: ", work_dir)
    print("pid_file: ", pid_file)
    print("tarantool: ", tarantool)
    print("args: ", args)
    print("env: ", env)

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

    log_file_f = open(log_file, 'a')

    print("starting tarantool")

    devnull_fd = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull_fd, 0)
    os.dup2(log_file_f.fileno(), 1)
    os.dup2(log_file_f.fileno(), 2)
    os.close(devnull_fd)
    log_file_f.close()

    os.chdir(app_work_dir)
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


def read_config(filename='cluster.cfg'):
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


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('-c', '--config',
        help="Configuration file", default='cluster.cfg')

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

    cfg = read_config(args.config)

    if args.command == 'start':
        start(cfg, args.instance_name)
    elif args.command == 'stop':
        stop(cfg, args.instance_name)

    if getattr(args, 'attach', False):
        attach(args.instance_name)


if __name__ == "__main__":
    main()
