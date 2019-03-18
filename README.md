# Deprecated
I'm using [Grafana Home Dashboard](https://www.indigodomo.com/pluginstore/167/) now. - 2019

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

#### Getting graphite running on your Mac is easy, but it does have a number of dependencies. Since you're running Indigo, and you are reading a github entry, I'm going to assume you either know how to get graphite running (go google) or you are ready to throw down and get these dependencies in order.

- Install [Homebrew](http://brew.sh):
 - `/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"`
- I'm not going to repeat the directions I followed. I'll just link to them and explain what I may have done differently.
- I followed this pretty much exactly. [Follow these steps to install graphite on OS X Mavericks.](https://gist.github.com/relaxdiego/7539911)
- If you don't have pip: `sudo easy_install pip`

#### You probably want carbon and graphite to auto-run on startup, right?

- For GrahiteWeb (Django instance), I created a LaunchAgent plist to make OS X start it up. Copy these contents to `/Library/LaunchAgents/pro.sleepers.graphite_launcher.plist`
- You also need to do `mkdir /opt/graphite/log`
- Be sure to correct the UserName key! I recommend the same username as where you run Indigo, keep it simple.
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>pro.sleepers.graphite_launcher</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StartInterval</key>
    <integer>600</integer>
    <key>StandardOutPath</key>
    <string>/opt/graphite/log/launchctl-carbon.stdout</string>
    <key>StandardErrorPath</key>
    <string>/opt/graphite/log/launchctl-carbon.stderr</string>
    <key>UserName</key>
    <string>administrator</string>
    <key>GroupName</key>
    <string>staff</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/django-admin.py</string>
        <string>runserver</string>
        <string>--pythonpath</string>
        <string>/opt/graphite/webapp</string>
        <string>--settings</string>
        <string>graphite.settings</string>
        <string>0.0.0.0:8088</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/opt/graphite</string>
  </dict>
</plist>
```
- Run this command to start it up: 
```bash
sudo launchctl load -w /Library/LaunchAgents/pro.sleepers.graphite_launcher.plist
```
- For Carbon, it has a start/stop/status script, so I just configure a schedule in Indigo to check it every 5 minutes. It is started if it happens to not be running. You could do considerably fancier things, like turn it into a virtual device you can turn on and off and graph and all that jazz, but meh. Just add the schedule like you see in these screen shots.
![Schedule for every 5 minutes.](http://www.sleepers.pro/wp-content/uploads/2016/12/five_min_schedule.jpg "Schedule for every 5 minutes.")

![Add a conditional script.](http://www.sleepers.pro/wp-content/uploads/2016/12/start_carbon_condition.jpg "Add a conditional script.")
- Here is the snippet of AppleScript you should copy into the Condition tab:
```applescript
set ReturnCode to do shell script "/opt/graphite/bin/carbon-cache.py status > /dev/null 2>&1 ; echo $?"
if ReturnCode is equal to "1" then
        log "Starting Carbon"
        return true
end if
return false
```

![Run the script in the Action.](http://www.sleepers.pro/wp-content/uploads/2016/12/start_carbon_actions.jpg "Run the script in the Action.")
- Command snippet: `/opt/graphite/bin/carbon-cache.py start`


## Step 3 - Install Grafana

 - `brew install grafana`
 - When it asks if you want to run it on startup, select `y`.
 - I think that's all I did. The rest of the configuration is done via UI. It runs HTTP on port 3000.


## Step 4 - Install Indigraphs

 - Well, you're here aren't you? On your Indigo server: 
```bash
mkdir -p ~/Documents/Indigo
cd ~/Documents/Indigo
git clone git@github.com:davidnewhall/indigraphs.git
````
 - You'll need to fix your PATH, like this:
 - `export PATH=$PATH:/usr/local/bin:/Applications/Postgres.app/Contents/Versions/latest/bin:/Library/Application\ Support/Perceptive\ Automation/Indigo\ 7/IndigoPluginHost.app/Contents/MacOS/`
 - I recommend putting this in your `.bashrc` or `.profile` - whatever works for you.
 - There is one dependency: `sudo easy_install graphitesend`
 - Test it: `./indigraphs.py`
 - No output? It worked. Look in your Indigo Log. You should see something like `Script [Indigraphs] Metrics Updated: 1342, Rows Skipped: 1272, Tables Scanned: 58`.
 - Now to make it run every 5 minutes to auto-collect new data. Add another 5 minute schedule to Indigo, like this:
![Schedule for every 5 minutes.](http://www.sleepers.pro/wp-content/uploads/2016/12/five_min_schedule.jpg "Schedule for every 5 minutes.")
 - Use "Execute Script" in the "Server Actions" like this:
![Execute Script.](http://www.sleepers.pro/wp-content/uploads/2016/12/update_graphite_actions.jpg "Execute Script")


## Step 5 - Setup Grafana and add graphs.
- Point your browser to port 3000 on whatever your host is that's running Indigo, possibly [http://localhost:3000/](http://localhost:3000/)
- Add the graphite data source. Click the Grafana-logo menu in the top left, select Data Sources and click Add Data Source. Make it look like this:

![Grafana Data Source](http://www.sleepers.pro/wp-content/uploads/2016/12/grafana-data-source.png "Grafana Data Source")

- Setup your graphs. Grafana is a little intimidating at first, but it's not that bad. There's many ways to customize graphs and make it perfect.
- Create a new Dashboard next. I named my House Report. In the dashboard, click Add Row and select Graph. Click on the name of the row (Panel Title) and then click Edit, like this:

![Grafana Edit Row](http://www.sleepers.pro/wp-content/uploads/2016/12/grafana-edit-row.png "Grafana Edit Row")

- From here, you can add metrics and customize the dashboard, like this:

![Grafana Add Metric](http://www.sleepers.pro/wp-content/uploads/2016/12/grafana-add-metric.png "Grafana Add Metric")

- Here's a partial screenshot of my system:

![Grafana](http://www.sleepers.pro/wp-content/uploads/2016/12/grafana_view-1.png "Grafana")
