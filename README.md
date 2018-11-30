# Tarantool instance manager

This Python module allows you to start multiple instances of tarantool
apps, daemonize them and control either as a group or individually.
You can use it either from command line when you don't want to use
systemd, or from integration test harness to test clustered apps.

*NB*: This is prototype-quality software, expect bugs and frequent API changes.

## Requirements

- Python 2.7+ or 3.0+
- tarantool either installed in system, or statically built and shipped inside app dir

## Installation

First, install the instance manager from pip

```sh
sudo pip install tarantoolup
```

This will add `tarantoolup` binary to your `$PATH`

## Managing one project for development purposes

This is helpful if you want to start multiple instances of a tarantool
app you develop. `tarantoolup` detects if current directory contains a
tarantool app and allows a simple way to start it in multiple copies.

First, make sure that you have `init.lua` and `myapp-scm-1.rockspec`
in current directory.

Then create configuration file called `tarantool.ini` in the current
dir:

```ini
[myapp.instance_1]
option1 = value1

[myapp.instance_2]
option2 = value2
```

Note that `myapp` in `myapp.instance_1` should be the same name used
in rockspec file.

To start your app, do this:

```sh
tarantoolup start myapp
```

to stop all instances of `myapp`, do:

```sh
tarantoolup stop myapp
```

to start/stop instances individually, do something like:

```sh
tarantoolup start/stop myapp.instance_1
```


## Managing multiple projects

If you'd like to manage multiple projects, you'd need to create
`tarantool.ini` in `~/.config/tarantool` and have it look like this:

```ini
[default]
work_dir = /my/work/dir
app_dir = /my/app/dir

[myapp.instance_1]
option1 = value1

[myapp.instance_2]
option2 = value2
```

Note the addition of `[default]` section as compared to single-app
method. `work_dir` is where data files, sockets and logs will go.
`app_dir` is where `tarantoolup` will look for applications.

In order to perform `tarantoolup start myapp`, it will look for
`myapp` subdir in `/my/app/dir` and `init.lua` in this subdir.

Other than that, the rest is exactly like in case with single app:

```sh
tarantoolup start myapp
```
