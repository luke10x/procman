# Procman

Procman is a lightweight Procfile process manager for running, logging, and controlling local development services through a detachable daemon.

## Features

- Runs commands from a Heroku-style `Procfile`
- Starts all or selected processes in the background
- Streams combined logs with process-name prefixes
- Starts, stops, and lists individual processes
- Supports PTY attach for interactive processes
- Stores daemon state and logs under `~/.procman`

### How Procman differs from Foreman/Honcho

Procman is a PTY-aware process supervisor for Procfiles: like Foreman/Honcho in CLI usage, but it allocates pseudo-terminals per process (so you can detach them with Ctrl‑P/Ctrl‑Q), runs them as a daemon, and includes a no-TTY mode that behaves like the plain Foreman/Honcho.

CLI usage mirrors Docker Compose; think of Procman as a Docker Compose that runs processes instead of containers.

## Requirements

- Python 3
- macOS or Linux

## Quick Start

Create a `Procfile`:

```Procfile
web: python3 -m http.server 8000
worker: python3 worker.py
```

Start every process:

```sh
./proc up
```

Start every process in the background:

```sh
./proc up -d
```

List processes:

```sh
./proc ps
```

Follow logs:

```sh
./proc log -f
```

Stop everything:

```sh
./proc down
```

## Commands

```sh
./proc up [-d] [PROC ...]
```

Starts all processes from the `Procfile`, or only the named processes. Without `-d`, Procman attaches to logs after startup.

```sh
./proc ps
```

Shows each managed process, status, PID, uptime, and command.

```sh
./proc log [-f] [PROC ...]
./proc logs [-f] [PROC ...]
```

Prints recent logs for all or selected processes. Use `-f` to follow new log output.

```sh
./proc start PROC
./proc stop PROC
```

Starts or stops a single process by name.

```sh
./proc attach PROC
```

Attaches your terminal to a process PTY. Detach with `Ctrl-P Ctrl-Q`.

```sh
./proc down
```

Stops all managed processes and shuts down the daemon.

## Using Another Procfile

By default, Procman looks for `./Procfile`. Pass `-f` to use a different file:

```sh
./proc -f path/to/Procfile up -d
```

## State and Logs

Procman stores state in:

```text
~/.procman/<hash-of-procfile-path>
```

Each project gets a separate state directory based on the absolute Procfile path. Process logs are written inside that directory under `logs/`.
