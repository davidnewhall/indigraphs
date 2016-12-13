# Indigraphs
Graphs for Indigo Data.

Here you will find detailed instructions for how to graph every piece of data Indigo creates using free software: [PostgreSQL](http://postgresapp.com "PostgresAPP for OS X"), [Graphite](http://graphite.readthedocs.io/en/latest/ "Graphite Docs") and [Grafana](http://grafana.org "Grafana Homepage"). Also provided is a custom script you can schedule in Indigo. It copies your SQL data into graphite.

## Step 1 - Get your data into SQL.

#### Download PostgresAPP from [http://postgresapp.com](http://postgresapp.com)
- It doesn't require much configuration. 
- Set it to turn on at login so it's always available.

#### Setup the Indigo SQL Logger Plugin.
- There are directions on [Indigo's Wiki](http://wiki.indigodomo.com/doku.php?id=plugins:sql_logger#configuring_sql_logger_with_postgresql)
- Leave the database name as `indigo_history` to make things easy.
- Event log entries are ignored, so turn them on if *you* need them.

## Step 2 - Get Graphite running

#### Getting graphite running on your Mac is easy, but it does have a number of dependencies. SInce you're running Indigo, and you are reading a github entry, I'm going to assume you either know how to get graphite running (go google) or you are ready to throw down and get these dependencies in order.

- Install [Homebrew](http://brew.sh):
 - `/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"`
- I'm not going to repeat the directions I followed. I'll just link to them and explain what I may have done differently.
- I followed this pretty much exactly. [Follow these steps to install graphite on OS X Mavericks.](https://gist.github.com/relaxdiego/7539911)
- If you don't have pip: `sudo easy_install pip`

#### You probably want carbon and graphite to auto-run on startup, right?

more to come.
