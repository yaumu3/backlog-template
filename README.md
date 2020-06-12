# backlog-template

Python CLI tool to post routine issues to Backlog project.

![demo](demo.gif)

## Prerequisites

- Python 3.8 or later
- Poetry 1.0.0 or later (dependency manager)

## Installation

Use [Poetry](https://python-poetry.org) to install dependent packages.

```sh
poetry install
```

## How to use

After [configured](#management-of-api-keys), let the tool eat a [template file](#template) written in [TOML](https://github.com/toml-lang/toml) with `post` subcommand.

```sh
python backlog_template.py post templates/template.toml
```

### Management of API keys

Store API key by `managekey` subcommand. API will be stored to macOS Keychain, Windows Credential Locker... by [keyring](https://github.com/jaraco/keyring) module.

```sh
python backlog_template.py managekey your_space.backlog.com
```

### Check the validity of API key

You can check the validity of API key by `doctor` subcommand.

```sh
python backlog_template.py doctor your_space.backlog.com
```

## Template

This tool parses a TOML file that describes issues then post issues to the designated project. The TOML file is consisted of following tables.

### Target (Required)

In `[target]` table, you need to specify the target project with following keys.

- `SPACE_DOMAIN`: The domain of backlog project (ex. `your_project.backlog.com`)
- `PROJECT_KEY`

### Config

In `[config]` table, you can define following constants.

#### Base date time

When you want to express some date and time (i.e. dueDate) by [Time-delta table](#time-delta-table), set reference date and time formatted in [RFC 3339](https://tools.ietf.org/html/rfc3339) as `basedate` in `[config]`.

#### Replacable strings

Strings in curly braces will be replaced upon the post by the table `[config.repl]`.

### Issues

Enumerate follwing keys in table `[[issues]]`. The table can be followed by multiple child issues as `[[issues.children]]` tables.

#### Mandatory keys

- summary
- issueType
- priority

#### Optional keys

- description
- milestone
- version
- dueDate ([RFC 3339](https://tools.ietf.org/html/rfc3339) or [Time-delta table](#time-delta-table))
- assignee

#### Time-delta table

Date and time can be expressed as difference from [`basedate`](#base-date-time). Keys are as same as [timedelta](https://docs.python.org/3/library/datetime.html#datetime.timedelta) Object's keyword arguments are. So, these keys are accepted.

- weeks
- days
- hours
- minutes
- seconds
- milliseconds
- microseconds

3 days *before* the `basedate` is expressed as follows. Note that, it is a minus value saying *before*.

```toml
dueDate = {days = -3}
```

### Example of template

```toml
[target]
SPACE_DOMAIN = "your_space.backlog.com"
PROJECT_KEY = "YOUR_PROJECT"

[config]
basedate = 2020-01-01T00:00:00Z

[config.repl]
SUMMARY1 = "a issue"
SUMMARY2 = "another issue"
GOAL = "a goal"

[[issues]]
summary = "{SUMMARY1}"
issueType = "Bug"
description = "## TL;DR\n\nThis task must be done to achiveve {GOAL}."
milestone = "1.0.0"
priority = "High"
dueDate = 2020-02-02T00:00:00Z
assignee = "John Smith"

[[issues.children]]
summary = "a child issue of {SUMMARY1}"
issueType = "Task"
description = "## a child issue of {SUMMAR1}\nThis issue is essential to achieve {GOAL}."
version = "1.0.0"
milestone = "1.0.0"
priority = "High"
dueDate = {days = -3}
assignee = "John Smith"

[[issues.children]]
summary = "another child issue of {SUMMARY1}"
issueType = "Task"
description = "## another child issue of {SUMMARY1}\nThis issue is really important to achieve {GOAL}."
priority = "Low"
dueDate = 2020-02-02T00:00:00Z

[[issues]]
summary = "{SUMMARY2}"
issueType = "Bug"
description = "## TL;DR\n\nThis task must be done to achiveve {GOAL}."
milestone = "1.0.0"
priority = "High"
assignee = "John Smith"

[[issues.children]]
summary = "a child issue of {SUMMARY2}"
issueType = "Task"
description = "## a child issue of {SUMMARY2}\nThis issue is essential to achieve {GOAL}."
version = "1.0.0"
milestone = "1.0.0"
priority = "High"
dueDate = {weeks = -1}
assignee = "John Smith"
```
