#!/usr/bin/env IndigoPluginHost -x
#
# Indigraphs - David Newhall II - December 2016 - v1.0.0
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
import time
import re


# Set all of these.
DBNAME = 'indigo_history'
DBUSER = 'administrator'
DBPASS = ''
DBHOST = 'localhost'
TBNAME = 'indigo_history'
GRAPHITE_SERVER = 'localhost'
# Setting this to something non-true will make this script useless.
USE_GRAPHITE = True

# If you make any custom tables in this database, add them here to skip them.
SKIP_TABLES = {'already_processed', 'eventlog_history'}


#
# Good ol' psycopg2. Such a love-hate relationship here.
# Took me a while to figure out the UPDATE syntax below. uhg.
#
def getDBconnection():
    try:
        conn = psycopg2.connect("""dbname='{0}' user='{1}' host='{2}' password='{3}'"""
                                .format(DBNAME, DBUSER, DBHOST, DBPASS))
    except:
        print "DB connection failure."
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


#
# Get devices from indigo; create dev_id->name and dev_id->type mappings.
#
def getIndigoData():
    myIndigoData = {'device': {}, 'type': {}, 'variable': {}}
    # Map IDs and Types to Device Names.
    for dev in indigo.devices:
        # This is ugly, but this is my ability. Please fix me?
        dev_type = str(dev.__class__).split("'")[1].split('.')[1]
        myIndigoData['type'][dev.id] = dev_type
        # This is easy. Why can't type be this easy?
        myIndigoData['device'][dev.id] = dev.name
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
             WHERE table_schema = 'public' and table_catalog='{0}'""".format(TBNAME)
    cursor.execute(sql)
    return cursor.fetchall()


#
# Loop the very list retreived above; run SELECT * on each table.
#
def getDataFromTables(cursor, tables, last_imported_ids):
    items_by_list = []
    # Process each table.
    for row in tables:
        tname = row['table_name']
        # Skip these.
        if tname in SKIP_TABLES:
            continue
        last_id = last_imported_ids.setdefault(tname, 0)
        print "-> Processing '{0}' - Skipping to ID {1}.".format(tname, last_id)
        sql = "SELECT * FROM {0} WHERE id > {1}".format(tname, last_id)
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
# Take a dict of metrics, a location, a name and a timestamp. Send2graphite!
#
def processGraphiteMetric(graphite, metricRow, location, name, seconds):
    for col, val in metricRow.iteritems():
        try:
            # Only process columns that are numeric.
            float(val)
            # Replace anything that is not 0-9, A-Z, a-z, -, _, / or . with _
            name = re.sub('[^0-9a-zA-Z_\-\.\/]+', '_', name)
            metric_name = "home.{0}.{1}.{2}".format(location, name, col)
            graphite.send(metric_name, val, seconds)
            print "Sent {0}={1} ({2})".format(metric_name, val, seconds)
        except:
            # Wasn't numeric or graphite.send failed, keep on going...
            next


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
    dbconn = getDBconnection()
    cursor = dbconn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    createProcessedTable(cursor)
    # This is a list of tables to query. Indigo dynamically creates
    # (and deletes) tables; difficult to know what to expect.
    indigo_tables = getOurTableList(cursor)
    # This is a list of the last ID processed per table; avoid re-processing.
    last_imported_ids = getRecentIDs(cursor)
    # This allows us to map device and variables IDs to names and types.
    myIndigoData = getIndigoData()
    # Open a connection to graphite now before going into loops.
    if USE_GRAPHITE:
        graphite = graphitesend.init(graphite_server=GRAPHITE_SERVER,
                                     prefix='', system_name='')
    # SELECT * on every table to pull all the data into a list of dicts.
    items_by_list = getDataFromTables(cursor, indigo_tables, last_imported_ids)
    # Process one row (metric line) at a time.
    for data in items_by_list:
        # Pull these out since they're a bit useless as metrics.
        table_name = data.pop('table_name')
        table_type = data.pop('table_type')
        indigo_id = data.pop('indigo_id')
        timestamp = data.pop('ts')
        sql_id = data.pop('id')
        # Find our Max ID for this table so it can be updated/recorded..
        if table_name not in max_id or max_id[table_name] < sql_id:
            max_id[table_name] = sql_id
        # Device (or variable) type. Used as part of the metric name.
        if table_type == 'variable':
            item_type = 'variable'
        else:
            item_type = myIndigoData['type'][indigo_id]
        item_name = myIndigoData[table_type][indigo_id]
        # Time since epoch of this metric.
        seconds = int(time.mktime(timestamp.timetuple()))
        if USE_GRAPHITE:
            # You could do something else with the Metric here, but what? :)
            processGraphiteMetric(graphite, data, item_type, item_name, seconds)
    # Store the last ID(s) processed in the db; avoid processing them again.
    updateLastIDinSQL(cursor, last_imported_ids, max_id)
    # Done with the database
    cursor.close()
    dbconn.commit()
    dbconn.close()


run()
