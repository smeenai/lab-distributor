# Lab file distribution

A script to distribute lab files to SVN. Developed for CS 233, though it
could be used elsewhere.


## Installation

The script requires Python 2.7+. On EWS, you can get Python 2.7 using

```sh
module load python
```

or preferably, get Python 3 by using

```sh
module load python3
```

No libraries are required.


## Usage

Run

```sh
./distribute_lab.py -h
```

to get all the juicy details, including the format of the `__init__.py`
files (ab)used by the script to hold distribution information.

One thing to note is that the script requires the repository to be
checked out. If you're concerned about disk usage and/or checkout time,
a sparse checkout will work just fine (GIYF), as long as the `_rosters`
directory is fully checked out, unless you want to use the `--missing`
distribution mode. It's probably easiest to just check out the entire
repository; it shouldn't exceed a couple of gigabytes if you're doing
things right, and it doesn't take too long to update as long as you keep
doing so incrementally.
