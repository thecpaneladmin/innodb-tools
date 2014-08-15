# InnoDB Exporter/Importer

Python script for exporting and importing InnoDB tables.

Vendor Websites: 

* The cPanel Admin/TCA Server Solutions, LLC <http://thecpaneladmin.com>
* InMotion Hosting, Inc <http://inmotionhosting.com>

Author: Vanessa Vasile <vanessa@thecpaneladmin.com>

This script does a mass export and import of InnoDB tables for MySQL.  Doing 
this can resolve a number of InnoDB-related MySQL issues, including:

* InnoDB log sequence mismatches
* Converting to innodb_file_per_table, and shrinking the shared ibdata1 file
* Restoring from InnoDB recovery mode where MySQL/InnoDB will not start without
  recovery being enabled

Usage Scenario Example:

* http://www.thecpaneladmin.com/how-to-convert-innodb-to-innodb_file_per_table-and-shrink-ibdata1/

DISCLAIMER:

As usual, before you make any drastic changes to MySQL data, you should make a
backup. We are not responsible for any damage done to your system resulting
from failure to back up data or follow instructions. While this script has been
repeatedly tested and used in production environments, we must reiterate that
you use this script at your own risk.


## PREREQUISITES

### A.  Running MySQL instance

MySQL must be running for this script to be able to export tables properly.
If You are having trouble starting MySQL, check the MySQL error log for 
anything obvious.  If the issue is related to corrupted InnoDB data:

1) Open /etc/my.cnf in a text editor
2) Add the following line:

    innodb_force_recovery = 1

3) Attempt to start MySQL

If MySQL still does not start, keep increasing the recovery level up to 6
until it does. If MySQL still refuses to start, your issues are likely 
outside the scope of what this script would be able to do for you, and you
should consult a professional.

More information:
http://dev.mysql.com/doc/refman/5.6/en/forcing-innodb-recovery.html

If you recently upgraded from 5.5 to 5.6, also try downgrading back to 5.5,
using this script to re-import all tables, then upgrading again.

Note: A lot of InnoDB problems can be resolved simply by starting InnoDB in
recovery mode (1-4), restarting MySQL, then restarting again without
recovery mode.


### B.  Backups

Make sure you have a backup of your MySQL data.  Since you may be dealing with 
corrupted data, we'd recommend stopping MySQL and making a copy of your MySQL
data directory (i.e. /var/lib/mysql).  Again, MySQL should be stopped when you
do this.  This allows you to easily restore MySQL to the a previous state if
needed.

If you prefer to use dumps for backups, you can use mysqldump:

http://webcheatsheet.com/sql/mysql_backup_restore.php


### C.  Miscellaneous

The following is also needed:

* MySQL 5.0 or higher with client packages installed
* Python 2.6 or 2.7 with standard modules includes, plus MySQLDB
* Enough free disk space on the partition this script will dump to
  (typically the size of your MySQL data folder)
* Root MySQL access
* Write permissions to the folder this script is dumping data to

Most standard systems already meet the above requirements.  This script also
works with MySQL running on cPanel servers.


## USAGE

### Exporting tables

The script will only export InnoDB tables, and does so by iterating through
all databases and dumping only the ones listed as having InnoDB as their
engine.

Export syntax:

    ./innodb_import_export.py --export [--dir=DIR] [--config=CONFIG]

Where:

    --dir = The folder where you would like the dumps to be stored.  By default
        this is /home/innodb_data.  A child folder will becreated within this
        directory for each session, denoted in these examples as $SESSION
    --config = The client configuration file for MySQL.  By default, this is
        /root/.my.cnf, but you can create your own

More information:
http://dev.mysql.com/doc/refman/5.6/en/option-files.html

Export format:

    /$DIR/$SESSION/$DATABASE_NAME/$TABLE_NAME.sql

Log file:

    /$DIR/$SESSION/innodb_export.log


### Importing tables

Before you import, you may need to do the following:

* If innodb_recovery_mode > 0, disable it and restart MySQL
* If you had corruption or are switching to innodb_file_per_table, move the
  ibdata1 and ib_logfile* files out of the MySQL data folder and restart MySQL.
  MySQL will automatically recreate these files at default sizes

When you exported, the script provided the name of the export location:

    /$DIR/$SESSION

ie: /home/innodb_data/201407281740/

This is the location we are restoring from.

Import syntax:

    ./innodb_export_import.py --import --dir=DIR [--skip-working] [--config=CONFIG]

Where:

    --dir = The directory containing the exports taken, as discussed above
    --skip-working = Use this option if you do not want to import tables that
      are working.  This does not check data integrity, but rather whether
      MySQL recognizes that the table exists.  You would want to use this
      option when resuming from a previous restoration
    --config = The client configuration file for MySQL.  By default, this is
      /root/.my.cnf, but you can create your own

More information:

http://dev.mysql.com/doc/refman/5.6/en/option-files.html


#### Notes:

* When restoring, the .ibd files for each table are moved into the respective
  table's export folder.  This is to clear up tablespace for corrupted tables
  that would otherwise prevent an import from occurring.

* If you want to STOP an import, you should avoid using CTRL+C. Instead, touch
  a stop file in the import folder and the script will stop importing after the
  current table is done.

  Example:

    touch /$DIR/$SESSION/stop

  Make sure to remove this file before resuming, and consider using
  --skip-working as to prevent re-importing tables that were already
  imported.

* If you deleted the ibdata1 and ib_logfile* files, it may be necessary to also
  remove the .frm files for each table, since ibdata1 will no longer reference
  them.  You'll know this is necessary if you are not able to import due to
  MySQL claiming the table could not be dropped or created because it already
  exists. A quick way to do this is to dump the below lines into a file and run:

  Note: You should stop MySQL before doing this.

```
    #!/bin/bash
    DIR='/home/innodb_data/$SESSION/' # PUT THE DIR NAME HERE, ie /$DIR/$SESSION/
    for file in $(find /var/lib/mysql -name *.frm)
    do
        DB=$(dirname $file | xargs basename)
        TABLE=$(basename $file .frm)
        /bin/mv -f /var/lib/mysql/$DB/$TABLE.frm $DIR/$DB/
    done
```

  This is not coded into the script as doing this may be irreversible and
  dangerous.  Again, make sure you have a backup.
   
   
### Checking tables

This script can automate post-import sanity checks against InnoDB tables

Check syntax:

    ./innodb_export_import.py --verify

A summary and location of the log file will be given when the script run is
completed.  The log file will log failures at an ERROR level for review.

One thing to keep in mind here is that this script (and rather any script of
of this nature, is incapable of verifying the integrity of data within the
table itself. This script specifically checks that MySQL can access the 
table, even if it means the table contains partial or no data.  If MySQL can at
least access the table, it means that 1) data can be imported, and 2) The
InnoDB engine will not be halted on startup due to the table being corrupted.

If you were running innodb_file_per_table prior to running this script and
notice that the .ibd files are smaller than they were before, this does not
mean you lost data, it may mean that unused space within the tablespace file
was removed, resulting in a smaller file.

