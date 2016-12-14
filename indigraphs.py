#!/usr/bin/env IndigoPluginHost -x
#
# Indigraphs - David Newhall II - December 2016 - v0.0.1
#
# Use this script to pull data from a database and send it to graphite.
# It's specifically designed for the SQL Logger plugin in Indigo 6 & 7,
# but can be easily modified to sniff numeric values from any database.
# Written to be as generic as possible so you can attach other input or
# output mechanisms easily. For directions on how to graph your Indigo
# data in graphite and Grafana please visit ->
#
# http://github.com/davidnewhall/indigraphs
#
# License: GPLv2 - see accompanying LICENSE file.


import psycopg2
import psycopg2.extras
import indigo
import graphitesend

# Set all of these.
DBNAME = 'indigo_history'
DBUSER = 'administrator'
DBPASS = ''
DBHOST = 'localhost'
GRAPHITE_SERVER = 'localhost'
# Setting this to something non-true will make this script useless.
USE_GRAPHITE = True
# If you make any custom tables in this database, add them here to skip them.
SKIP_TABLES = {'already_processed', 'eventlog_history'}
DEBUG_LOG = False
#DEBUG_LOG = '/tmp/indigraphs.log'



def log(msg):
    if not DEBUG_LOG:
        return
    time = str(indigo.server.getTime()).split('.')[0]
    debuglog.write("[{0}] indigraphs: {1}\n".format(time, msg))

#
# Good ol' psycopg2. Such a love-hate relationship here.
# Took me a while to figure out the UPDATE syntax below. uhg.
#
def getDBconnection():
    try:
        conn = psycopg2.connect("""dbname='{0}' user='{1}' host='{2}' password='{3}'"""
                                .format(DBNAME, DBUSER, DBHOST, DBPASS))
    except:
        indigo.server.log("[Indigraphs] ERROR: DB connection failure.")
    return conn


#
# Create a table to keep track of processed rows.
#
def createProcessedTable(cursor):
    sql = """SELECT EXISTS(SELECT 1 FROM information_schema.tables
              WHERE table_catalog='{0}' AND
                    table_schema='public' AND
                    table_name='already_processed');""".format(DBNAME)
    cursor.execute(sql)
    if not cursor.fetchone()[0]:
        sql = "CREATE TABLE already_processed (table_name VARCHAR, last_id INT);"
        cursor.execute(sql)
    # This is a good place to retreive and return the timezone. We use it later.
    sql = "SHOW TIMEZONE;"
    cursor.execute(sql)
    return cursor.fetchone()[0]


#
# Get device data from indigo.
# Create dev_id->name, dev_id->folder and dev_id->type maps.
#
def getIndigoData():
    myIndigoData = {'device': {}, 'type': {}, 'folder': {}, 'variable': {}}
    # Map IDs and Types to Device Names.
    for dev in indigo.devices:
        # This is ugly, but this is my ability. Please fix me?
        dev_type = str(dev.__class__).split("'")[1].split('.')[1]
        if dev.folderId != 0:
            dev_folder = indigo.devices.folders[dev.folderId].name
        else:
            dev_folder = 'NoFolder'
        myIndigoData['type'][dev.id] = dev_type
        # This is easy. Why can't type be this easy?
        myIndigoData['device'][dev.id] = dev.name
        myIndigoData['folder'][dev.id] = dev_folder
    # Map IDs to Variable Names.
    for var in indigo.variables:
        myIndigoData['variable'][var.id] = var.name
    return myIndigoData


#
# Retreive data from a table full of table->id mappings.
# Only retreive IDs newer than those listed within.
#
def getRecentIDs(cursor):
    last_imported_ids = {}
    # Get the last IDs processed, to avoid re-processing data.
    sql = "SELECT table_name,last_id FROM already_processed"
    cursor.execute(sql)
    for row in cursor.fetchall():
        last_imported_ids[row['table_name']] = row['last_id']
    return last_imported_ids


#
# Retrieve the - rather dynamic - list of tables indigo has created.
#
def getOurTableList(cursor):
    # Get list of tables to process.
    sql = """SELECT table_name FROM information_schema.tables
             WHERE table_schema = 'public' and table_catalog='{0}'""".format(DBNAME)
    cursor.execute(sql)
    return cursor.fetchall()


#
# Loop the very list retreived above; run SELECT * on each table.
#
def getDataFromTables(cursor, tables, last_imported_ids, timezone):
    items_by_list = []
    # Process each table.
    for row in tables:
        tname = row['table_name']
        # Skip these.
        if tname in SKIP_TABLES:
            continue
        last_id = last_imported_ids.setdefault(tname, 0)
        log("-> Processing '{0}' - Skipping to ID {1}.".format(tname, last_id))
        sql = """SELECT EXTRACT(EPOCH FROM ts AT time zone '{0}') as seconds,*
                 FROM {1} WHERE id > {2}""".format(timezone, tname, last_id)
        cursor.execute(sql)
        # Each table has different columns; save their names too.
        columns = [i[0] for i in cursor.description]
        items = cursor.fetchall()
        # This is just to normalize the data format.
        for row in items:
            i = 0
            myDict = {'table_name': tname, 'indigo_id': int(tname.split('_')[2]),
                      'table_type': tname.split('_')[0]}
            for val in row:
                myDict[columns[i]] = val
                i = 1 + i
            items_by_list.append(myDict)
    return items_by_list


#
# Take a dict of metrics, a location, a type, a name and a timestamp.
#
def processGraphiteMetric(metricRow, location, type, name, seconds):
    metrics = []
    for col, val in metricRow.iteritems():
        try:
            # Only process columns that are numeric.
            float(val)
            metric_name = "indigraph.{0}.{1}.{2}.{3}".format(location, name, type, col)
            log("Sent: {0}={1} ({2})".format(metric_name, val, seconds))
            #print "Sent: {0}={1} ({2})".format(metric_name, val, seconds)
            metrics.append((metric_name, val, seconds))
        except:
            log("Skip: {0}.{1}.{2}.{3}={4}".format(location, name, type, col, val))
            # Wasn't numeric or graphite.send failed, keep on going...
            next
    return metrics

#
# Update indemic database table already_processed with our freshly recorded data.
#
def updateLastIDinSQL(cursor, last_imported_ids, max_id):
    updates = []
    inserts = []
    # Loop the IDs that were just processed.
    for table_name, table_id in max_id.iteritems():
        if table_name in last_imported_ids and last_imported_ids[table_name] != 0:
            # This is a new table, so do an INSERT.
            updates.append((table_name, table_id))
        else:
            inserts.append((table_name, table_id))
    if len(updates) > 0:
        # This is how to avoid sql injections with pyscopg2. Interesting, right?
        rlt = ','.join(['%s'] * len(updates))
        usql = """UPDATE already_processed AS ap SET last_id = c.last_id
                  FROM (VALUES {0}) AS c(table_name, last_id)
                  WHERE c.table_name = ap.table_name;""".format(rlt)
        # Could probably wrap some try/except logic here, but I'm lazy. Make it work.
        cursor.execute(usql, updates)
    if len(inserts) > 0:
        rlt = ','.join(['%s'] * len(inserts))
        isql = "INSERT INTO already_processed (table_name, last_id) VALUES {0};".format(rlt)
        cursor.execute(isql, inserts)


#
# This is where all the fun begins.
#
def run():
    max_id = {}
    graphite_metrics = []
    dbconn = getDBconnection()
    cursor = dbconn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    timezone = createProcessedTable(cursor)
    # This is a list of tables to query. Indigo dynamically creates
    # (and deletes) tables; difficult to know what to expect.
    indigo_tables = getOurTableList(cursor)
    # This is a list of the last ID processed per table; avoid re-processing.
    last_imported_ids = getRecentIDs(cursor)
    # This allows us to map device and variables IDs to names and types.
    myIndigoData = getIndigoData()
    # SELECT * on every table to pull all the data into a list of dicts.
    items_by_list = getDataFromTables(cursor, indigo_tables, last_imported_ids, timezone)
    # Process one row (metric line) at a time.
    sendcount = 0
    skipcount = 0
    for data in items_by_list:
        # Pull these out since they're a bit useless as metrics.
        table_name = data.pop('table_name')
        table_type = data.pop('table_type')
        indigo_id = data.pop('indigo_id')
        timestamp = data.pop('ts')
        # Time since epoch of this metric.
        seconds = int(data.pop('seconds'))
        sql_id = data.pop('id')
        # Find our Max ID for this table so it can be updated/recorded..
        if table_name not in max_id or max_id[table_name] < sql_id:
            max_id[table_name] = sql_id
        # Device (or variable) type. Used as part of the metric name.
        if table_type == 'variable':
            item_type = 'variable'
            folder = 'variables'
        else:
            item_type = myIndigoData['type'][indigo_id]
            folder = myIndigoData['folder'][indigo_id]
        item_name = myIndigoData[table_type][indigo_id]
        if USE_GRAPHITE:
            # You could do something else with the Metric here, but what? :)
            metrics = processGraphiteMetric(data, folder,
                                           item_type, item_name, seconds)
            sendcount += len(metrics)
            skipcount += (len(data) - len(metrics))
            graphite_metrics += metrics
    if USE_GRAPHITE:
        graphite = graphitesend.init(graphite_server=GRAPHITE_SERVER,
                                     prefix='', system_name='')
        graphite.send_list(graphite_metrics)
    # Store the last ID(s) processed in the db;, to avoid processing them again.
    updateLastIDinSQL(cursor, last_imported_ids, max_id)
    # Throw some data into the Indigo Log.
    indigo.server.log("[Indigraphs] Metrics Updated: {0}, Rows Skipped: {1}, Tables Scanned: {2}"
                      .format(sendcount, skipcount, len(indigo_tables)))
    # Done with the database
    cursor.close()
    dbconn.commit()
    dbconn.close()


if DEBUG_LOG:
    debuglog = open(DEBUG_LOG, 'a')
run()
if DEBUG_LOG:
    debuglog.close()
