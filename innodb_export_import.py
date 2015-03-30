#!/usr/bin/env python
"""InnoDB Import/Export Script"""

from glob import glob
import logging
import os
import subprocess
import sys
from datetime import datetime
from optparse import OptionParser

try:
    import MySQLdb
except ImportError:
    print 'MySQLdb module not found. To install, run: easy_install MySQL-python'
    sys.exit(1)


def init_logging(log_file):
    """Initializes logger"""

    inc = datetime.now().strftime('%M%S')

    if os.path.exists(log_file):
        rename_to = os.path.join(log_file, inc)
        print 'Moving existing log file to %s' % rename_to

        try:
            os.rename(log_file, rename_to)
        except OSError:
            pass

    open(log_file, 'w').close()
    logging.basicConfig(format='%(levelname)s: %(message)s',
                        filename=log_file, level=logging.INFO)

    return True


def stop(data_dir):
    """Checks for a stop file and exits gracefully"""

    # Check for a stop file
    if os.path.exists(os.path.join(data_dir, 'stop')):
        msg = 'Stop file detected...stopping'
        print color_me(msg, 'red')
        logging.info(msg)
        return True

    return False


def color_me(string, color):
    """Makes pretty colors if you want 'em"""

    options = opts()[0]

    if not options.do_color:
        return string

    pretty_colors = {
        'red': '\033[91m',
        'orange': '\033[93m',
        'green': '\033[92m',
        'blue': '\033[36m',
        'normal': '\033[0m'
    }

    return '%s %s %s' % (pretty_colors[color],
                         string, pretty_colors['normal'])


def display_stats(stats):
    """Displays summary of what this script actually did"""

    summary = {}

    print '\nSUMMARY:\n'
    for key, value in stats.items():
        name = key.replace('_', ' ').title()
        summary[key] = value
        print '%s: %s' % (name, value)

    return summary


def mysql_connect(config, dbname=None):
    """Establishes a MySQL connection"""

    try:
        conn = MySQLdb.connect(
            db=dbname,
            read_default_file=config
            )

        dbconn = conn.cursor()

    except MySQLdb.Error, err:
        print 'MySQL Error %d: %s' % (err.args[0], err.args[1])
        return None

    return dbconn


def get_recovery_level(config):
    """Checks InnoDB recovery level"""

    dbname = ''
    dbconn = mysql_connect(config, dbname)

    if not dbconn:
        return False

    try:
        dbconn.execute("SHOW VARIABLES LIKE 'innodb_force_recovery'")
    except (MySQLdb.Error, TypeError), err:
        print 'MySQL Error %d: %s' % (err.args[0], err.args[1])
        sys.exit(1)

    result = dbconn.fetchone()[1]

    return result


def get_mysql_version(config):
    """Gets MySQL Server Version"""

    dbname = ''
    dbconn = mysql_connect(config, dbname)

    if not dbconn:
        return False

    try:
        dbconn.execute("SHOW VARIABLES LIKE 'version'")
    except (MySQLdb.Error, TypeError), err:
        print 'MySQL Error %d: %s' % (err.args[0], err.args[1])
        sys.exit(1)

    result = ('').join(dbconn.fetchone()[1].split('-')[0].split('.')[:2])

    return int(result)


def database_exists(config, dbname):
    """Checks if a database exists"""

    dbconn = mysql_connect(config, dbname)

    if not dbconn:
        return False

    print 'Checking %s...' % dbname
    try:
        dbconn.execute("SHOW TABLES")
    except (MySQLdb.Error, TypeError):
        return False

    return True


def check_table(config, dbname, table):
    """Checks an InnoDB table"""
    # Really what we're doing is making sure the tablespace is intact.
    # This is usually as simply as trying to access the table

    dbconn = mysql_connect(config, dbname)

    if not dbconn:
        return False

    print 'Checking %s.%s...' % (dbname, table)
    try:
        dbconn.execute("EXPLAIN %s" % (table,))
    except (MySQLdb.Error, TypeError), err:
        print err
        return False

    return True


def get_dbs_with_innodb(config):
    """Gets a list of databases that contain InnoDB tables"""

    dbname = 'INFORMATION_SCHEMA'
    dbconn = mysql_connect(config, dbname)

    if not dbconn:
        return False

    data = {}

    # This is a little 'eh'.  You can poll for all InnoDB tables via
    # INFORMATION_SCHEMA, but on very large servers this query can time
    # out or hang the server. Therefore, we're going to pull a list of
    # databases and query INFORMATION_SCHEMA individually for all InnoDB
    # tables within each database.

    # Format: dict = { 'db': ['table_1', 'table_2' ... ]

    print 'Getting a list of databases...'
    try:
        dbconn.execute("SHOW DATABASES")
    except (MySQLdb.Error, TypeError), err:
        print 'MySQL Error %d: %s' % (err.args[0], err.args[1])
        return False

    databases = [ d[0] for d in dbconn.fetchall() ]
    for exclude_db in [ 'mysql', 'information_schema' ]:
        databases.remove(exclude_db)

    print 'Checking for InnoDB tables...'

    for database in databases:

        print('Database %s...' % database),
        try:
            dbconn.execute(
                "SELECT table_name FROM INFORMATION_SCHEMA.TABLES"
                " WHERE table_schema='%s' and engine='innodb';" % database
            )
        except (MySQLdb.Error, TypeError), err:
            print 'MySQL Error %d: %s' % (err.args[0], err.args[1])
            continue

        tables_raw = dbconn.fetchall()
        if tables_raw:
            tables = [item[0] for item in tables_raw]

            print 'Detected %s InnoDB tables' % len(tables_raw)
            data[database] = tables
        else:
            print 'No InnoDB tables'

    return data


def dump_table(dbname, table, mysql_version, data_dir, config):
    """Dumps a table"""

    dump_opts = ''
    if mysql_version >= 56:
        dump_opts = '--add-drop-trigger' # Only supported in mysqldump for 5.6

    dump_path = os.path.join(data_dir, dbname)
    if not os.path.exists(dump_path):
        os.makedirs(dump_path)

    dump_file = os.path.join(dump_path, '%s.sql' % table)
    fhandle = open(dump_file, 'w+')

    try:
        process = subprocess.Popen(
            "mysqldump --defaults-extra-file=%s --add-drop-table %s %s %s" % (
                config, dump_opts, dbname, table
            ),
            stdout=fhandle, stderr=subprocess.PIPE, shell=True)
        fhandle.close()
        output = process.stderr.read()

        if output == '':
            return True
        else:
            return False

    except subprocess.CalledProcessError:
        return False


def import_table(dbname, table, data_dir, config):
    """Imports a table"""

    dump_file = os.path.join(data_dir, dbname, '%s.sql'  % table)

    try:
        process = subprocess.Popen(
            "mysql --defaults-file=%s %s < %s" % (
                config, dbname, dump_file

            ),
            stderr=subprocess.PIPE, shell=True)
        output = process.stderr.read()

        if output == '':
            return True
        else:
            return False

    except subprocess.CalledProcessError:
        return False


def main():
    """Default function"""

    options = opts()[0]
    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    config = options.config

    if options.do_export and options.do_import:
        print 'Please specify either --import or --export'
        sys.exit(1)
    elif (not options.do_export
          and not options.do_import
          and not options.do_verify):
        print 'Please specify either --import, --export, or --verify'
        sys.exit(1)

    mysql_version = get_mysql_version(config)
    if not mysql_version:
        print 'Unable to determine MySQL version'
        sys.exit(1)
    elif mysql_version < 50:
        print 'This script requires MySQL 5.0 or higher'
        sys.exit(1)

    if options.do_export:
        do_export(options, config, timestamp, mysql_version)

    if options.do_import:
        do_import(options, config)

    if options.do_verify:
        do_verify(options, config, timestamp)


def do_export(options, config, timestamp, mysql_version):
    """Handles table exports"""

    # We only want a default dir for exports
    if not options.data_dir:
        options.data_dir = '/home/innodb_data'

    data_dir = os.path.join(options.data_dir, timestamp) # Change dir
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    log_file = os.path.join(data_dir, 'innodb_export.log')

    init_logging(log_file)

    databases = get_dbs_with_innodb(config)

    stats = {
        'databases_total': len(databases),
        'tables_total': 0,
        'tables_exported': 0,
        'tables_failed': 0,
    }

    if databases:
        print 'Dumping tables...'
    else:
        print 'No databases detected, or none contain InnoDB data.'

    # Keep a ghetto counter with the number of tables, so we can check progress
    num_tables = 0
    for dbname, tables in databases.items():
        num_tables += len(tables)

    for dbname, tables in databases.items():
        for table in tables:
            stats['tables_total'] += 1

            if stop(data_dir):
                sys.exit(0)

            if dump_table(dbname, table, mysql_version, data_dir, config):
                msg = 'Dumped table %s.%s (%s / %s)' % (dbname, table, stats['tables_total'], num_tables)
                print color_me(msg, 'green')
                logging.info(msg)
                stats['tables_exported'] += 1
            else:
                msg = 'Error dumping table %s.%s' % (dbname, table)
                print color_me(msg, 'red')
                logging.error(msg)
                stats['tables_failed'] += 1

    summary = display_stats(stats)
    logging.info(summary)

    print "\nLog file: %s " % log_file
    print "Tables were dumped to: %s" % data_dir


def do_import(options, config):
    """Handles table imports"""

    # We can't do this if we're in recovery mode
    if int(get_recovery_level(config)) > 0:
        print('MySQL is running with innodb_recovery_mode > 0. '
              'Please disable before continuing.')
        sys.exit(1)
    if options.data_dir:
        data_dir = options.data_dir.rstrip("/")
    else:
        print('An import requires a directory containing InnoDB dumps. '
              ' Please pass --dir with a valid directory name')
        sys.exit(1)

    if not os.path.exists(data_dir):
        print 'Data directory "%s" does not exist' % data_dir
        sys.exit(1)

    log_file = os.path.join(data_dir, 'innodb_import.log')
    init_logging(log_file)

    if not os.path.exists(data_dir):
        print 'Import directory %s does not exist' % data_dir
        sys.exit(1)

    # Loop through the import folder
    try:
        databases = os.walk(data_dir).next()[1]
    except StopIteration:
        print 'No databases to restore'
        sys.exit(0)

    stats = {
        'databases_total': len(databases),
        'tables_total': 0,
        'tables_imported': 0,
        'tables_failed': 0,
        'tables_skipped': 0
    }

    for dbname in databases:
        # Make sure this is a valid database
        if database_exists(config, dbname):
            if dbname == 'mysql':
                continue

            # Get tables
            table_files = glob(os.path.join(data_dir, dbname, '*.sql'))
            for dump in table_files:
                table = os.path.splitext(os.path.basename(dump))[0]

                if stop(data_dir):
                    summary = display_stats(stats)
                    logging.info(summary)
                    sys.exit(0)

                stats['tables_total'] += 1

                if options.skip_working:
                    # Skip tables that are already working, if we said to
                    if check_table(config, dbname, table):
                        msg = 'Skipping table %s.%s' % (dbname, table)
                        print color_me(msg, 'blue')
                        logging.info(msg)
                        stats['tables_skipped'] += 1

                # Import the table
                else:
                    original = os.path.join(
                        '/var/lib/mysql/', dbname, '%s.ibd' % table
                    )
                    new = os.path.join(data_dir, dbname, '%s.ibd' % table)
                    print original
                    try:
                        os.rename(original, new)
                        print color_me('Backed up %s' % original, 'blue')

                    except OSError:
                        pass

                    # Import the table
                    if import_table(dbname, table, data_dir, config):
                        msg = 'Imported table %s.%s' % (dbname, table)
                        print color_me(msg, 'green')
                        logging.info(msg)
                        stats['tables_imported'] += 1
                    else:
                        msg = 'Error importing table %s.%s' % (dbname, table)
                        print color_me(msg, 'red')
                        logging.error(msg)
                        stats['tables_failed'] += 1


    summary = display_stats(stats)
    logging.info(summary)

    print "\nLog file: %s " % log_file


def do_verify(options, config, timestamp):
    """Handles table sanity checks"""

    # We only want a default dir for exports
    if not options.data_dir:
        options.data_dir = '/home/innodb_data'

    data_dir = os.path.join(options.data_dir, timestamp)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    log_file = os.path.join(data_dir, 'innodb_check.log')

    init_logging(log_file)

    if not os.path.exists(data_dir):
        print 'Import directory %s does not exist' % data_dir
        sys.exit(1)

    databases = get_dbs_with_innodb(config)

    stats = {
        'databases_total': len(databases),
        'tables_total': 0,
        'tables_checked': 0,
        'tables_ok': 0,
        'tables_bad': 0,
    }

    if databases:
        print 'Checking tables...'
    else:
        print 'No databases detected!'

    for dbname, tables in databases.items():
        for table in tables:
            if stop(data_dir):
                summary = display_stats(stats)
                logging.info(summary)
                sys.exit(0)

            stats['tables_total'] += 1
            stats['tables_checked'] += 1

            if check_table(config, dbname, table):
                msg = 'Table %s.%s is OK' % (dbname, table)
                print color_me(msg, 'green')
                logging.info(msg)
                stats['tables_ok'] += 1
            else:
                msg = 'Table %s.%s has errors' % (dbname, table)
                print color_me(msg, 'red')
                logging.error(msg)
                stats['tables_bad'] += 1

    summary = display_stats(stats)
    logging.info(summary)

    print "\nLog file: %s " % log_file


def opts():
    """Defines valid command line options"""

    parser = OptionParser(
        usage='usage: %prog [options]',
        version='%prog 1.0'
    )
    parser.add_option(
        '-e', '--export',
        help='Export InnoDB tables',
        action='store_true', dest='do_export', default=False
        )
    parser.add_option(
        '-i', '--import',
        help="Import InnoDB data",
        action='store_true', dest='do_import', default=False
        )
    parser.add_option(
        '-v', '--verify',
        help="Verify InnoDB tables",
        action='store_true', dest='do_verify', default=False
        )
    parser.add_option(
        '-d', '--dir',
        help="Location of InnoDB data (default: /home/innodb_data)",
        action='store', type='string', dest='data_dir'
    )
    parser.add_option(
        '-s', '--skip-working',
        help="Skip import of tables that are a already working",
        action='store_true', dest='skip_working', default=False
    )
    parser.add_option(
        '-c', '--config',
        help="Local user config file (default: /root/.my.cnf)",
        action='store', type='string', dest='config', default='/root/.my.cnf'
    )
    parser.add_option(
        '-p', '--colors',
        help="Color output; Makes failures more visible.",
        action='store_true', dest='do_color', default=False
    )

    (options, args) = parser.parse_args()

    return options, args


if __name__ == '__main__':
    main()

